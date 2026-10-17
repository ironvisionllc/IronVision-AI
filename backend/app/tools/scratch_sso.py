"""Isolated rehearsal SSO stack: a throw-away Keycloak (own scratch DB + role in the rehearsal Postgres, never the production
keycloak DB, no published ports) configured by the SAME code as production (keycloak_config.py), ephemeral identities, cleanup.

    python -m app.tools.scratch_sso prepare  --ts TS
    python -m app.tools.scratch_sso setup    --ts TS --kc-url URL --app-url URL
    python -m app.tools.scratch_sso cleanup-users  --ts TS --kc-url URL
    python -m app.tools.scratch_sso cleanup-finish --ts TS --container-rc N
    python -m app.tools.scratch_sso prod-oidc-check --issuer URL     (anonymous discovery + JWKS only; separate from the e2e)

Production Keycloak is never contacted by prepare/setup/cleanup (they only talk to --kc-url = the scratch instance). No
existing account is used: the e2e user `rehearsal-e2e-<random>` and the demo-launcher account are created in the scratch realm
with random in-memory passwords. Secrets live only in RDIR/scratch-sso-TS/ (0700, files 0600) and RDIR/.e2e-credentials (read
once by the probe and deleted); every file is removed by cleanup-finish. Nothing secret is printed or written to a report."""
import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.tools import recovery as rv

REALM = "ironvision-demo"
SOURCE = "rehearsal-scratch-sso"
BACKEND_DIR = Path(__file__).resolve().parents[2]


def sdir(ts: str) -> Path:
    return rv.RDIR / f"scratch-sso-{ts}"


def res_path(ts: str) -> Path:
    return rv.RDIR / f"scratch-sso-{ts}.json"


def _pw() -> str:
    return secrets.token_urlsafe(24)


def _write(p: Path, s: str) -> None:
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as fh:
        fh.write(s)


def _env_file(p: Path, d: dict) -> None:
    if any("\n" in str(v) or "\r" in str(v) for v in d.values()):
        raise rv.RecoveryError("scratch value contains a newline")
    _write(p, "".join(f"{k}={v}\n" for k, v in d.items()))  # plain KEY=VALUE, read by recover.sh load_kv (never sourced)


def _read_env(p: Path) -> dict:
    out = {}
    for ln in p.read_text().splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            out[k] = v
    return out


def _results(ts: str) -> dict:
    p = res_path(ts)
    return json.loads(p.read_text()) if p.is_file() else {"ts": ts, "steps": {}, "cleanup": {}}


def _save(ts: str, r: dict) -> None:
    res_path(ts).write_text(json.dumps(r, indent=1, default=str))


def _redact(s: str, secret_values: list[str]) -> str:
    for v in secret_values:
        if v:
            s = s.replace(v, "***")
    return rv.redact(s)


def kc_db_name(ts: str) -> str:
    n = f"rec_kc_{ts}"
    if not rv.SCRATCH.match(n):
        raise rv.RecoveryError(f"refusing non-scratch Keycloak DB name {n}")
    return n


def _raw():
    eng = create_engine(rv.admin_url(), isolation_level="AUTOCOMMIT")
    return eng, eng.raw_connection()


def cmd_prepare(a) -> int:
    """Scratch DB + login role for the scratch Keycloak; bootstrap-admin secret. Writes scratch-sso-TS/kc.env (0600)."""
    from psycopg import sql
    d = sdir(a.ts)
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    name, kpw, boot = kc_db_name(a.ts), _pw(), _pw()
    eng, raw = _raw()
    try:
        cur = raw.cursor()
        cur.execute(sql.SQL("create role {} login password {}").format(sql.Identifier(name), sql.Literal(kpw)))
        cur.execute(sql.SQL("grant {} to current_user").format(sql.Identifier(name)))  # PG16 CREATEROLE: needed to set it as DB owner
        cur.execute(sql.SQL("create database {} owner {}").format(sql.Identifier(name), sql.Identifier(name)))
    finally:
        raw.close()
        eng.dispose()
    u = make_url(rv.admin_url())
    _env_file(d / "kc.env", {"KC_DB": "postgres", "KC_DB_URL": f"jdbc:postgresql://{u.host}:{u.port or 5432}/{name}", "KC_DB_USERNAME": name,
                             "KC_DB_PASSWORD": kpw, "KC_BOOTSTRAP_ADMIN_USERNAME": "rehearsal-bootstrap", "KC_BOOTSTRAP_ADMIN_PASSWORD": boot})
    r = _results(a.ts)
    r["kc_db"] = {"database": name, "role": name, "server": f"{u.host}:{u.port or 5432}", "note": "scratch – never the production keycloak DB"}
    r["steps"]["prepare"] = True
    _save(a.ts, r)
    print(f"[scratch-sso] scratch Keycloak DB {name} + role {name} created on {u.host}")
    return 0


def _wait(kc: str, timeout: int = 300) -> None:
    end = time.time() + timeout
    while time.time() < end:
        try:
            if httpx.get(f"{kc}/realms/master", timeout=5).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise rv.RecoveryError(f"scratch Keycloak {kc} not ready after {timeout}s")


def _admin(kc: str, cid: str, secret: str) -> dict:
    r = httpx.post(f"{kc}/realms/master/protocol/openid-connect/token", timeout=20,
                   data={"grant_type": "client_credentials", "client_id": cid, "client_secret": secret})
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def restored_fingerprint(db: str, exclude_org: str | None) -> dict:
    """Users (+ roles + identity mappings) of the restored/copied data, excluding the scratch probe org, the demo-launcher
    target (which the scratch link maps) and demo SANDBOX orgs (personas the demo login/role switch legitimately touch).
    Compared before/after the scratch SSO run."""
    eng = create_engine(rv.db_url(db))
    q = ("select u.id, u.email, u.is_active, u.org_id, u.display_name, u.updated_at, "
         " coalesce((select string_agg(ra.role || ':' || ra.scope_id, ',' order by ra.role, ra.scope_id) from role_assignments ra where ra.user_id = u.id), ''), "
         " coalesce((select string_agg(ai.subject, ',' order by ai.subject) from auth_identities ai where ai.user_id = u.id), '') "
         "from users u where (cast(:o as uuid) is null or u.org_id <> cast(:o as uuid)) and u.email not like '%@rehearsal.invalid' "
         " and u.email <> :demo and u.org_id not in (select id from organizations where is_sandbox) order by u.email")
    with eng.connect() as c:
        rows = [tuple(map(str, r)) for r in c.execute(text(q), {"o": exclude_org, "demo": "demo@ironvision.ai"})]
    eng.dispose()
    return {"users": len(rows), "sha256": hashlib.sha256(json.dumps(rows).encode()).hexdigest(),
            "rows": {r[1]: hashlib.sha256(json.dumps(r).encode()).hexdigest()[:16] for r in rows}}


def _base_env() -> dict:
    """Controlled env: NOTHING from the production Keycloak/OIDC configuration of this container leaks into scratch tooling."""
    return {k: os.environ[k] for k in ("PATH", "HOME", "LANG", "PYTHONPATH") if k in os.environ}


def cmd_setup(a) -> int:
    d, kc, app = sdir(a.ts), a.kc_url.rstrip("/"), a.app_url.rstrip("/")
    target = f"rec_target_{a.ts}"
    if not rv.SCRATCH.match(target):
        raise rv.RecoveryError("non-scratch target DB")
    k = _read_env(d / "kc.env")
    r = _results(a.ts)
    r["restored_before"] = restored_fingerprint(target, None)
    s = {"KEYCLOAK_CONFIGURATOR_CLIENT_SECRET": _pw(), "KEYCLOAK_ADMIN_PASSWORD": _pw(), "OIDC_CLIENT_SECRET": _pw(),
         "KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET": _pw(), "KEYCLOAK_BACKEND_CLIENT_SECRET": _pw(), "KEYCLOAK_DEMO_PASSWORD": _pw()}
    demo_user = f"rehearsal-demo-launcher-{secrets.token_hex(4)}"
    issuer = f"{kc}/realms/{REALM}"
    env = {**_base_env(), **s, "KEYCLOAK_URL": kc, "KEYCLOAK_REALM": REALM, "OIDC_ISSUER": issuer, "OIDC_CLIENT_ID": "ironvision-app",
           "OIDC_REDIRECT_URI": f"{app}/api/v1/auth/oidc/callback", "OIDC_POST_LOGOUT_REDIRECT_URI": f"{app}/login", "FRONTEND_URL": app,
           "KEYCLOAK_CONFIGURATOR_CLIENT_ID": "ironvision-configurator", "KEYCLOAK_ADMIN_USERNAME": "rehearsal-admin",
           "KC_BOOTSTRAP_ADMIN_USERNAME": k["KC_BOOTSTRAP_ADMIN_USERNAME"], "KC_BOOTSTRAP_ADMIN_PASSWORD": k["KC_BOOTSTRAP_ADMIN_PASSWORD"],
           "KEYCLOAK_DEMO_USERNAME": demo_user, "KEYCLOAK_DEMO_LAUNCHER_CLIENT_ID": "ironvision-demo-launcher",
           "KEYCLOAK_BACKEND_CLIENT_ID": "ironvision-backend", "DEPLOYMENT_KIND": "demo", "KEYCLOAK_ALLOW_REGISTRATION": "false"}
    hide = [*s.values(), k["KC_BOOTSTRAP_ADMIN_PASSWORD"], k["KC_DB_PASSWORD"]]
    _wait(kc)
    p = subprocess.run([sys.executable, "-m", "app.tools.keycloak_config", "apply", "--yes"], env=env, cwd=BACKEND_DIR,
                       capture_output=True, text=True, check=False)
    r["keycloak_config"] = {"rc": p.returncode, "output_tail": _redact((p.stdout + p.stderr)[-1500:], hide),
                            "note": "same code as production (app.tools.keycloak_config apply) against the scratch Keycloak"}
    if p.returncode:
        _save(a.ts, r)
        raise rv.RecoveryError("keycloak_config apply against the scratch Keycloak failed (see scratch-sso json)")
    h = _admin(kc, env["KEYCLOAK_CONFIGURATOR_CLIENT_ID"], s["KEYCLOAK_CONFIGURATOR_CLIENT_SECRET"])
    uname, upw = f"rehearsal-e2e-{secrets.token_hex(5)}", _pw()
    base = f"{kc}/admin/realms/{REALM}/users"
    httpx.post(base, headers=h, timeout=20, json={
        "username": uname, "email": f"{uname}@rehearsal.invalid", "emailVerified": True, "enabled": True, "firstName": "Rehearsal",
        "lastName": "Probe", "credentials": [{"type": "password", "value": upw, "temporary": False}]}).raise_for_status()
    kid = httpx.get(base, headers=h, timeout=20, params={"username": uname, "exact": "true"}).json()[0]["id"]
    did = (httpx.get(base, headers=h, timeout=20, params={"username": demo_user, "exact": "true"}).json() or [{}])[0].get("id")
    r["kc_users"] = {"e2e": {"username": uname, "id": kid}, "demo_launcher": {"username": demo_user, "id": did}}
    _save(a.ts, r)
    org_id = _app_identity(target, uname, issuer, kid)
    r["scratch_org_id"] = str(org_id)
    _save(a.ts, r)
    link = rv.kc_link_scratch(rv.db_url(target), a.ts, env={**env, "DATABASE_URL": rv.db_url(target)})
    r["demo_launcher_link"] = {k2: v for k2, v in link.items() if k2 != "output"} | {"output_tail": _redact(link.get("output", "")[-800:], hide)}
    if link["rc"]:
        _save(a.ts, r)
        raise rv.RecoveryError("demo-launcher link into the scratch DB failed (see scratch-sso json)")
    _env_file(d / "backend.env", {"SCRATCH_KC_URL": kc, "SCRATCH_OIDC_ISSUER": issuer, "SCRATCH_OIDC_CLIENT_SECRET": s["OIDC_CLIENT_SECRET"],
                                  "SCRATCH_APP_URL": app, "SCRATCH_DEMO_USERNAME": demo_user, "SCRATCH_DEMO_PASSWORD": s["KEYCLOAK_DEMO_PASSWORD"],
                                  "SCRATCH_DEMO_LAUNCHER_CLIENT_SECRET": s["KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET"],
                                  "SCRATCH_BACKEND_CLIENT_SECRET": s["KEYCLOAK_BACKEND_CLIENT_SECRET"]})
    _env_file(d / "admin.env", {"CID": env["KEYCLOAK_CONFIGURATOR_CLIENT_ID"], "SECRET": s["KEYCLOAK_CONFIGURATOR_CLIENT_SECRET"]})
    _write(rv.RDIR / ".e2e-credentials", f"{uname}\n{upw}\n")
    r["steps"]["setup"] = True
    r["issuer"] = issuer
    _save(a.ts, r)
    print(f"[scratch-sso] scratch realm {REALM} at {issuer}: clients ironvision-app + ironvision-demo-launcher, e2e user {uname} "
          f"(leadership_viewer in scratch org {org_id}), demo launcher {demo_user}")
    return 0


def _app_identity(target: str, uname: str, issuer: str, kid: str):
    from sqlalchemy.orm import Session

    from app.models import Organization, RoleAssignment, User
    from app.services.identity_map import map_identity
    eng = create_engine(rv.db_url(target))
    with Session(eng) as db:
        org = Organization(name=f"Rehearsal SSO probe {uname} (SCRATCH)", slug=uname, is_synthetic=True, source=SOURCE)
        db.add(org)
        db.flush()
        u = User(org_id=org.id, email=f"{uname}@rehearsal.invalid", display_name="Rehearsal e2e probe", source=SOURCE)
        db.add(u)
        db.flush()
        db.add(RoleAssignment(user_id=u.id, role="leadership_viewer", scope_type="org", scope_id=org.id, source=SOURCE))
        map_identity(db, user=u, issuer=issuer, sub=kid, reason="rehearsal scratch SSO probe", actor="recover.sh", username=uname)
        db.commit()
        oid = org.id
    eng.dispose()
    return oid


def cmd_cleanup_users(a) -> int:
    r, d, kc = _results(a.ts), sdir(a.ts), a.kc_url.rstrip("/")
    c = r.setdefault("cleanup", {})
    if not any(v.get("id") for v in (r.get("kc_users") or {}).values()):
        c["keycloak users deleted (none were created)"] = True
        _save(a.ts, r)
        return 0
    try:
        ad = _read_env(d / "admin.env")
        h = _admin(kc, ad["CID"], ad["SECRET"])
        for v in (r.get("kc_users") or {}).values():
            if v.get("id"):
                st = httpx.delete(f"{kc}/admin/realms/{REALM}/users/{v['id']}", headers=h, timeout=20).status_code
                c[f"keycloak user {v['username']} deleted"] = st in (204, 404)
    except Exception as exc:  # noqa: BLE001 – reported, never raised past cleanup
        c["keycloak users deleted"] = False
        c["keycloak users error"] = rv.redact(f"{type(exc).__name__}: {exc}")[:200]
    _save(a.ts, r)
    return 0


def cmd_cleanup_finish(a) -> int:
    """Always runs (pass or fail): scratch app rows, restored-users check, scratch Keycloak DB + role, secret files; then records
    the result in the rehearsal report. A failed cleanup is a rehearsal failure (production untouched either way)."""
    from psycopg import sql
    r = _results(a.ts)
    c = r.setdefault("cleanup", {})
    c["scratch Keycloak container removed"] = a.container_rc == 0
    target = f"rec_target_{a.ts}"
    try:
        if r.get("scratch_org_id"):
            eng = create_engine(rv.db_url(target))
            with eng.begin() as cx:
                o = {"o": r["scratch_org_id"]}
                cx.execute(text("delete from auth_identities where user_id in (select id from users where org_id = :o)"), o)
                cx.execute(text("delete from role_assignments where user_id in (select id from users where org_id = :o)"), o)
                cx.execute(text("delete from audit_events where org_id = :o"), o) if _has_col(cx, "audit_events", "org_id") else None
                cx.execute(text("delete from users where org_id = :o"), o)
                cx.execute(text("delete from organizations where id = :o"), o)
            eng.dispose()
            c["scratch org + e2e app user removed from the scratch DB"] = True
        if r.get("restored_before"):
            r["restored_after"] = restored_fingerprint(target, r.get("scratch_org_id"))
            b, f = r["restored_before"], r["restored_after"]
            r["restored_changed"] = sorted(e for e in {*b["rows"], *f["rows"]} if b["rows"].get(e) != f["rows"].get(e))
            c["restored users untouched (fingerprint before == after)"] = b["sha256"] == f["sha256"]
    except Exception as exc:  # noqa: BLE001
        c["scratch app rows removed"] = False
        c["scratch app rows error"] = rv.redact(str(exc))[:200]
    name = kc_db_name(a.ts)
    try:
        eng, raw = _raw()
        cur = raw.cursor()
        cur.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(name)))
        cur.execute(sql.SQL("drop role if exists {}").format(sql.Identifier(name)))
        raw.close()
        eng.dispose()
        c[f"scratch Keycloak DB + role {name} dropped"] = True
    except Exception as exc:  # noqa: BLE001
        c[f"scratch Keycloak DB + role {name} dropped"] = False
        c["drop error"] = rv.redact(str(exc))[:200]
    shutil.rmtree(sdir(a.ts), ignore_errors=True)
    (rv.RDIR / ".e2e-credentials").unlink(missing_ok=True)
    c["scratch secret files deleted"] = not sdir(a.ts).exists() and not (rv.RDIR / ".e2e-credentials").exists()
    ok = all(v for k, v in c.items() if isinstance(v, bool))
    r["cleanup_ok"] = ok
    _save(a.ts, r)
    fs = sorted(rv.RDIR.glob(f"rehearsal-{a.ts}.json"))
    if fs:
        body = json.loads(fs[-1].read_text())
        body["scratch_sso"] = {k: v for k, v in r.items()}
        if not ok:
            body["failures"].append("scratch SSO cleanup incomplete: " + ", ".join(k for k, v in c.items() if v is False) + " (production untouched)")
        if not r.get("steps", {}).get("setup"):
            body["failures"].append("scratch SSO stack setup failed – SSO e2e could not run (see scratch_sso in the report)")
        body["passed"] = not body["failures"]
        rv.write_report("rehearsal", a.ts, body)
    print(f"[scratch-sso] cleanup {'OK' if ok else 'INCOMPLETE'}: " + json.dumps({k: v for k, v in c.items() if isinstance(v, bool)}))
    return 0 if ok else 1


def _has_col(cx, table: str, col: str) -> bool:
    return bool(cx.execute(text("select 1 from information_schema.columns where table_name=:t and column_name=:c"), {"t": table, "c": col}).first())


def cmd_prod_oidc_check(a) -> int:
    """SEPARATE from the SSO e2e: anonymous read-only GETs of the production issuer's discovery document + JWKS. No login."""
    out = {"issuer": a.issuer, "kind": "anonymous read-only (discovery + JWKS), no user login – separate from the scratch SSO e2e"}
    try:
        d = httpx.get(a.issuer.rstrip("/") + "/.well-known/openid-configuration", timeout=15)
        out["discovery_status"] = d.status_code
        doc = d.json() if d.status_code == 200 else {}
        out["issuer_matches"] = doc.get("issuer") == a.issuer.rstrip("/")
        if doc.get("jwks_uri"):
            j = httpx.get(doc["jwks_uri"], timeout=15)
            out["jwks_status"], out["jwks_keys"] = j.status_code, len(j.json().get("keys", [])) if j.status_code == 200 else 0
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"[:200]
    out["ok"] = out.get("discovery_status") == 200 and out.get("issuer_matches") and out.get("jwks_keys", 0) > 0
    fs = sorted(rv.RDIR.glob("rehearsal-*.json"))
    if fs:
        body = json.loads(fs[-1].read_text())
        body["production_keycloak_anonymous_check"] = out
        if not out["ok"]:
            body.setdefault("warnings", []).append(f"production Keycloak anonymous discovery/JWKS check failed: {json.dumps(out)[:300]}")
        rv.write_report("rehearsal", body["ts"], body)
    print(f"[prod-oidc-check] {'OK' if out['ok'] else 'WARN'} {json.dumps(out)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(prog="scratch_sso")
    sp = ap.add_subparsers(dest="cmd", required=True)
    for n in ("prepare", "setup", "cleanup-users", "cleanup-finish"):
        p = sp.add_parser(n)
        p.add_argument("--ts", required=True)
        if n in ("setup", "cleanup-users"):
            p.add_argument("--kc-url", required=True)
        if n == "setup":
            p.add_argument("--app-url", required=True)
        if n == "cleanup-finish":
            p.add_argument("--container-rc", type=int, default=0)
    p = sp.add_parser("prod-oidc-check")
    p.add_argument("--issuer", required=True)
    a = ap.parse_args()
    fn = {"prepare": cmd_prepare, "setup": cmd_setup, "cleanup-users": cmd_cleanup_users, "cleanup-finish": cmd_cleanup_finish,
          "prod-oidc-check": cmd_prod_oidc_check}[a.cmd]
    try:
        return fn(a)
    except rv.RecoveryError as exc:
        print(f"[scratch-sso] FAIL {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    _ = uuid
    sys.exit(main())
