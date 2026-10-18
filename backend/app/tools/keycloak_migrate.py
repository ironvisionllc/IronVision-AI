"""Keycloak user migration + credential management (operator CLI; see docs/KEYCLOAK.md).

keycloak-migrate: DEFAULT dry run (read-only) → table + JSON report + plan hash. Apply needs --apply and either an interactive
APPLY confirmation or --yes --plan-hash <hash from the dry run>. Creating/linking needs --create-identities / --link; inactive users
are only reactivated when listed in --reactivate. bcrypt hashes are NOT migrated: created users get an individual generated password
written once to a root-only CSV. Never deletes app users, orgs, role assignments or data.
"""
import csv
import getpass
import hashlib
import json
import os
import re
import secrets
import string
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuthIdentity, Organization, RoleAssignment, User
from app.services import audit, identity_map
from app.services.keycloak_admin import KeycloakAdmin, KeycloakError, created_id

BACKUP_MAX_AGE = timedelta(hours=6)


def _issuer() -> str:
    return os.environ["OIDC_ISSUER"].rstrip("/")


def _realm() -> str:
    return os.environ.get("KEYCLOAK_REALM", "ironvision-demo")


def gen_password(n: int = 20) -> str:
    alpha = string.ascii_letters + string.digits + "-_.!@#%"
    while True:
        p = "".join(secrets.choice(alpha) for _ in range(n))
        if all(any(c in s for c in p) for s in (string.ascii_lowercase, string.ascii_uppercase, string.digits)):
            return p


def _kc_candidates(kc: KeycloakAdmin, email: str) -> list[dict]:
    found = {u["id"]: u for u in kc.users_by(_realm(), email=email) + kc.users_by(_realm(), username=email)}
    return list(found.values())


_NAME_BAD = re.compile(r"[<>&\"'$%!#?§;*~/\\|^=\[\]{}()@:\x00-\x1f]")


def _person_name(name: str | None) -> str:
    """Keycloak's person-name validator rejects these characters."""
    return " ".join(_NAME_BAD.sub(" ", name or "").split())


def build_plan(db, kc: KeycloakAdmin, reactivate: set[str]) -> list[dict]:
    issuer = _issuer()
    from app.services.sandbox import DEMO_EMAIL
    demo_handle = (os.environ.get("KEYCLOAK_DEMO_USERNAME") or "").lower()
    users = list(db.scalars(select(User).order_by(User.email)))
    dup = Counter(u.email.lower() for u in users)
    all_orgs = list(db.scalars(select(Organization)))
    orgs = {o.id: o.name for o in all_orgs}
    sandboxes = {o.id for o in all_orgs if o.is_sandbox}
    rows = []
    for u in users:
        email = u.email.lower()
        roles = [f"{r.role}@{r.scope_type}:{r.scope_id}" for r in db.scalars(select(RoleAssignment).where(RoleAssignment.user_id == u.id))]
        idents = [f"{i.provider}:{i.subject}" for i in db.scalars(select(AuthIdentity).where(AuthIdentity.user_id == u.id))]
        mine = identity_map.identity_for(db, u.id, issuer)
        is_demo = email == DEMO_EMAIL and bool(demo_handle)
        # the shared demo account maps to the launcher user, found by its unpublished handle (its e-mail is deliberately different)
        cands = kc.users_by(_realm(), username=demo_handle) if is_demo else _kc_candidates(kc, email)
        kc_id = cands[0]["id"] if len(cands) == 1 else None
        if u.persona_role and u.org_id in sandboxes and not is_demo:
            action, why = "skip", "demo-sandbox persona (reached via the role switcher, never logs in; no identity is linked)"
        elif dup[email] > 1:
            action, why = "CONFLICT", "duplicate email among app users"
        elif not u.is_active and email not in reactivate:
            action, why = "skip", "inactive (reactivate only with --reactivate)"
        elif len(cands) > 1:
            action, why = "CONFLICT", f"{len(cands)} Keycloak users match this email/username"
        elif mine is not None:
            mapped = mine.subject.rsplit("|", 1)[-1]
            if kc_id == mapped:
                action, why = "ok", "already linked"
            else:
                action, why = "CONFLICT", f"mapped to Keycloak user {mapped} which {'differs from ' + kc_id if kc_id else 'no longer exists'}"
        elif is_demo and not kc_id:
            action, why = "skip", "demo launcher user is created by keycloak_config (run scripts/keycloak.sh apply first)"
        elif kc_id:
            other = identity_map.by_subject(db, issuer, kc_id)
            if other is not None:
                action, why = "CONFLICT", "Keycloak user already mapped to another app user"
            elif not is_demo and (cands[0].get("email") or "").lower() != email:
                action, why = "CONFLICT", "Keycloak username matches but its email differs"
            else:
                action, why = "link", "demo launcher user (by handle)" if is_demo else "Keycloak user with this email exists"
        else:
            action, why = "create", "no Keycloak user yet"
        if action in ("create", "link") and not u.is_active:
            action = f"reactivate+{action}"
        rows.append({"email": email, "name": u.display_name, "org": orgs.get(u.org_id, ""), "user_id": str(u.id), "active": u.is_active,
                     "roles": roles, "identities": idents, "keycloak_user_id": kc_id, "action": action, "reason": why})
    return rows


def demo_link_problem(rows: list[dict]) -> str | None:
    """Demo launcher configured (KEYCLOAK_DEMO_USERNAME) but no row maps/keeps it on demo@ironvision.ai → Explore Demo would 403."""
    from app.services.sandbox import DEMO_EMAIL
    if not os.environ.get("KEYCLOAK_DEMO_USERNAME"):
        return None
    d = [r for r in rows if r["email"] == DEMO_EMAIL]
    if any(r["action"] in ("ok", "link", "reactivate+link") for r in d):
        return None
    why = f"{d[0]['action']}: {d[0]['reason']}" if d else (f"no app user {DEMO_EMAIL} in this database – create it with the demo "
                                                           "account step (app.seed / recover.sh cutover step demo_account)")
    return f"the demo launcher is configured (KEYCLOAK_DEMO_USERNAME) but --link would map 0 accounts to it, Explore Demo would return 403 ({why})"


def plan_hash(rows: list[dict]) -> str:
    canon = json.dumps([[r["email"], r["action"], r["keycloak_user_id"]] for r in rows], sort_keys=True)
    return hashlib.sha256(canon.encode()).hexdigest()[:16]


def print_table(rows: list[dict]) -> None:
    print(f"{'EMAIL':38} {'ORG':22} {'ACTIVE':6} {'ROLES':5} {'KC USER':10} {'ACTION':18} REASON")
    for r in rows:
        print(f"{r['email'][:38]:38} {r['org'][:22]:22} {'yes' if r['active'] else 'no':6} {len(r['roles']):<5} "
              f"{(r['keycloak_user_id'] or '-')[:10]:10} {r['action']:18} {r['reason']}")
    c = Counter(r["action"] for r in rows)
    print("summary: " + ", ".join(f"{k}={v}" for k, v in sorted(c.items())))


def check_backup(ref: str | None) -> str:
    if not ref:
        raise SystemExit("refusing to apply: --backup-ref <backup dir> is required (scripts/keycloak_migrate.sh runs the backup for you)")
    m = Path(ref) / "manifest.json"
    if not m.is_file():
        raise SystemExit(f"refusing to apply: {m} not found – backup missing or failed")
    created = datetime.fromisoformat(json.loads(m.read_text())["created_at"])
    if datetime.now(timezone.utc) - created > BACKUP_MAX_AGE:
        raise SystemExit(f"refusing to apply: backup {ref} is older than {BACKUP_MAX_AGE}")
    return str(m)


def _open_secret_file(cred_dir: str, prefix: str):
    d = Path(cred_dir)
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    p = d / f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.csv"
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    return p, os.fdopen(fd, "w", newline="")


def apply_plan(db, kc: KeycloakAdmin, rows: list[dict], *, create: bool, link: bool, temporary: bool, cred_dir: str, actor: str) -> dict:
    issuer, realm = _issuer(), _realm()
    todo = [r for r in rows if r["action"].split("+")[-1] in (("create",) if create else ()) + (("link",) if link else ())]
    done = Counter()
    path, fh = (None, None)
    if any(r["action"].endswith("create") for r in todo):
        path, fh = _open_secret_file(cred_dir, "demo-credentials")
        w = csv.writer(fh)
        w.writerow(["email", "keycloak_username", "password", "temporary"])
    try:
        for r in todo:
            user = db.get(User, r["user_id"])
            if r["action"].startswith("reactivate+"):
                user.is_active = True
                audit.record(db, action="user.reactivated", actor_email=actor, entity_type="user", entity_id=str(user.id),
                             details={"email": user.email, "reason": "keycloak-migrate --reactivate"})
                done["reactivated"] += 1
            if r["action"].endswith("create"):
                first, _, last = _person_name(user.display_name).partition(" ")
                kc_id = created_id(kc.post(f"/{realm}/users", {"username": r["email"], "email": r["email"], "emailVerified": True,
                                                               "firstName": first or r["email"], "lastName": last or "-", "enabled": True,
                                                               "attributes": {"ironvision_user_id": [str(user.id)]}}))
                pw = gen_password()
                kc.set_password(realm, kc_id, pw, temporary)
                w.writerow([r["email"], r["email"], pw, str(temporary).lower()])
                done["created"] += 1
            else:
                kc_id = r["keycloak_user_id"]
                done["linked"] += 1
            identity_map.map_identity(db, user=user, issuer=issuer, sub=kc_id, reason="keycloak-migrate", actor=actor, username=r["email"])
            db.commit()
    finally:
        if fh:
            fh.close()
    audit.record(db, action="keycloak.migrate.apply", actor_email=actor, entity_type="realm", entity_id=realm,
                 details={**done, "plan_hash": plan_hash(rows), "credentials_file": str(path) if path else None})
    db.commit()
    return {**done, "credentials_file": str(path) if path else None}


def migrate(a) -> int:
    reactivate = {e.strip().lower() for e in (a.reactivate or "").split(",") if e.strip()}
    kc = KeycloakAdmin().login()
    with SessionLocal() as db:
        rows = build_plan(db, kc, reactivate)
        h = plan_hash(rows)
        print_table(rows)
        report = Path(a.report or f"keycloak-migrate-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json")
        report.write_text(json.dumps({"plan_hash": h, "realm": _realm(), "issuer": _issuer(), "users": rows}, indent=1))
        os.chmod(report, 0o600)
        print(f"plan hash: {h}\nreport: {report}")
        demo_problem = demo_link_problem(rows)
        if demo_problem:
            print(f"WARNING: {demo_problem}", file=sys.stderr)
        if not a.apply:
            print("DRY RUN – nothing changed. To apply: --apply --create-identities --link [--reactivate a@x,b@y] "
                  f"--backup-ref <dir> --yes --plan-hash {h}")
            return 0
        if any(r["action"] == "CONFLICT" for r in rows) and not a.allow_conflicts:
            print("refusing to apply: resolve CONFLICT rows first (or --allow-conflicts to skip them)", file=sys.stderr)
            return 3
        if not (a.create_identities or a.link):
            print("nothing to apply: pass --create-identities and/or --link", file=sys.stderr)
            return 2
        if a.link and demo_problem:
            print(f"refusing to apply: {demo_problem}", file=sys.stderr)
            return 4
        if a.yes:
            if a.plan_hash != h:
                print(f"refusing to apply: --plan-hash {a.plan_hash!r} != current plan {h} (state changed since review)", file=sys.stderr)
                return 3
        elif input(f"Apply plan {h}? type APPLY: ").strip() != "APPLY":
            print("aborted")
            return 1
        check_backup(a.backup_ref)
        Path(a.credentials_dir).mkdir(mode=0o700, parents=True, exist_ok=True)
        if not os.access(a.credentials_dir, os.W_OK):
            print(f"refusing to apply: {a.credentials_dir} not writable", file=sys.stderr)
            return 2
        res = apply_plan(db, kc, rows, create=a.create_identities, link=a.link, temporary=a.temporary, cred_dir=a.credentials_dir,
                         actor=a.actor)
        print(f"applied: {json.dumps(res)}")
        if res.get("credentials_file"):
            print(f"individual credentials written ONCE to {res['credentials_file']} (mode 600). Hand them out securely, then delete the file.")
    return 0


# ------------------------------------------------------------------ keycloak-user
def _kc_user_id(db, kc: KeycloakAdmin, email: str) -> str:
    u = db.scalar(select(User).where(User.email == email.lower()))
    ident = identity_map.identity_for(db, u.id, _issuer()) if u else None
    if ident:
        return ident.subject.rsplit("|", 1)[-1]
    c = _kc_candidates(kc, email.lower())
    if len(c) != 1:
        raise SystemExit(f"no unique Keycloak user for {email}")
    return c[0]["id"]


def user_cmd(a) -> int:
    kc, realm = KeycloakAdmin().login(), _realm()
    with SessionLocal() as db:
        if a.op == "list":
            mapped = {m["keycloak_user_id"]: m["email"] for m in identity_map.list_mappings(db)}
            print(f"{'USERNAME':38} {'ENABLED':7} {'OTP':4} {'REQUIRED ACTIONS':22} MAPPED APP USER")
            for u in kc.get(f"/{realm}/users", params={"max": 1000, "briefRepresentation": "false"}) or []:
                otp = any(c.get("type") == "otp" for c in kc.credentials(realm, u["id"]))
                print(f"{u['username'][:38]:38} {str(u.get('enabled')).lower():7} {'yes' if otp else 'no':4} "
                      f"{','.join(u.get('requiredActions') or [])[:22]:22} {mapped.get(u['id'], '-')}")
            return 0
        uid = _kc_user_id(db, kc, a.email)
        details = {"email": a.email.lower(), "keycloak_user_id": uid}
        if a.op == "set-password":
            pw = sys.stdin.readline().rstrip("\n") if not sys.stdin.isatty() else getpass.getpass("new password: ")
            if len(pw) < 12:
                print("password must be at least 12 characters", file=sys.stderr)
                return 2
            kc.set_password(realm, uid, pw, a.temporary)
            details["temporary"] = a.temporary
        elif a.op == "rotate":
            pw = gen_password()
            kc.set_password(realm, uid, pw, a.temporary)
            path, fh = _open_secret_file(a.credentials_dir, "rotated-credential")
            with fh:
                csv.writer(fh).writerows([["email", "password", "temporary"], [a.email.lower(), pw, str(a.temporary).lower()]])
            kc.logout_user(realm, uid)
            print(f"new password written once to {path} (mode 600); existing Keycloak sessions ended")
            details.update(temporary=a.temporary, credentials_file=str(path))
        elif a.op in ("disable", "enable"):
            kc.put(f"/{realm}/users/{uid}", {**kc.user(realm, uid), "enabled": a.op == "enable"})  # full rep (user profile)
            if a.op == "disable":
                kc.logout_user(realm, uid)
        elif a.op == "reset-mfa":
            n = 0
            for c in kc.credentials(realm, uid):
                if c.get("type") == "otp":
                    kc.delete(f"/{realm}/users/{uid}/credentials/{c['id']}")
                    n += 1
            u = kc.user(realm, uid)
            if (u.get("attributes") or {}).get("demo_launcher") == ["true"]:
                print("the demo launcher user never uses OTP (it cannot sign in through the browser)", file=sys.stderr)
                return 2
            kc.put(f"/{realm}/users/{uid}", {**u, "requiredActions": sorted(set(u.get("requiredActions") or []) | {"CONFIGURE_TOTP"})})
            kc.logout_user(realm, uid)
            details["otp_credentials_removed"] = n
        audit.record(db, action=f"keycloak.user.{a.op}", actor_email=a.actor, entity_type="keycloak_user", entity_id=uid, details=details)
        db.commit()
        print(f"{a.op}: done for {a.email}")
    return 0


def add_parsers(sub) -> None:
    actor = os.environ.get("SUDO_USER") or getpass.getuser()
    m = sub.add_parser("keycloak-migrate", help="dry-run (default) / apply app→Keycloak user migration")
    m.add_argument("--apply", action="store_true")
    m.add_argument("--yes", action="store_true")
    m.add_argument("--plan-hash")
    m.add_argument("--create-identities", action="store_true")
    m.add_argument("--link", action="store_true")
    m.add_argument("--reactivate", default="")
    m.add_argument("--temporary", action="store_true", help="generated passwords must be changed at first login")
    m.add_argument("--password-mode", choices=["generated"], default="generated")
    m.add_argument("--allow-conflicts", action="store_true")
    m.add_argument("--backup-ref")
    m.add_argument("--report")
    m.add_argument("--credentials-dir", default=os.environ.get("CREDENTIALS_DIR", "/srv/ironvision/secrets"))
    m.add_argument("--actor", default=f"cli:{actor}")
    m.set_defaults(func=migrate)
    u = sub.add_parser("keycloak-user", help="manage Keycloak credentials (audited; no automatic resets)")
    u.add_argument("op", choices=["list", "set-password", "rotate", "disable", "enable", "reset-mfa"])
    u.add_argument("email", nargs="?")
    u.add_argument("--temporary", action="store_true")
    u.add_argument("--credentials-dir", default=os.environ.get("CREDENTIALS_DIR", "/srv/ironvision/secrets"))
    u.add_argument("--actor", default=f"cli:{actor}")
    u.set_defaults(func=user_cmd)


def run(a) -> int:
    if a.cmd == "keycloak-user" and a.op != "list" and not a.email:
        print("email is required", file=sys.stderr)
        return 2
    try:
        return a.func(a)
    except KeycloakError as e:
        print(f"keycloak error: {e}", file=sys.stderr)
        return 1
