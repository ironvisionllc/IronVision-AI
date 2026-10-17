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
import re
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

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
    # scratch-only app secret for every app-code command of the scratch stack (never the production JWT_SECRET; deleted at cleanup)
    _env_file(d / "app.env", {"JWT_SECRET": secrets.token_urlsafe(48)})
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


def _netloc(u: str) -> str:
    return urlparse(u if "://" in u else f"http://{u}").netloc.lower().replace("localhost", "127.0.0.1")


def _prod_kc_netlocs() -> set[str]:
    """Production Keycloak / app hosts as seen by THIS process (recovery container or recover.sh env)."""
    vals = [os.environ.get(k, "") for k in ("KEYCLOAK_URL", "OIDC_ISSUER", "KEYCLOAK_LIVE_URL")]
    vals += (os.environ.get("REHEARSAL_FORBIDDEN_HOSTS") or "").split(",")
    return {_netloc(v.strip()) for v in vals if v.strip()}


def assert_scratch_targets(cmd: str, db_url: str | None = None, kc: str | None = None) -> None:
    """Refuse unless DATABASE_URL is a scratch rehearsal DB (never the production DB) and the Keycloak base URL is not a
    production Keycloak/app host. Logs target NAMES only (no credentials)."""
    out = []
    if db_url is not None:
        u, live = make_url(db_url), make_url(rv.live_url()).database
        if not rv.SCRATCH.match(u.database or "") or u.database == live:
            raise rv.RecoveryError(f"{cmd}: refusing DATABASE_URL database {u.database!r} – not a scratch rehearsal DB "
                                   f"(production DB is {live!r})")
        out.append(f"DB {u.database} on {u.host}:{u.port or 5432}")
    if kc is not None:
        n = _netloc(kc)
        bad = sorted(p for p in _prod_kc_netlocs() if n == p or (":" not in p and n.split(":")[0] == p))
        if not n or bad:
            raise rv.RecoveryError(f"{cmd}: refusing Keycloak {n!r} – production Keycloak/app host {bad} (scratch Keycloak only)")
        out.append(f"Keycloak {n}")
    print(f"[scratch-sso] {cmd} targets: {', '.join(out)}")


def _scratch_app_env(d: Path, target_url: str, kc_env: dict) -> dict:
    """COMPLETE env for app-code commands of the scratch stack (keycloak_config, keycloak-migrate link): every required
    app.config setting with a scratch value – scratch DB, per-run JWT_SECRET from scratch-sso-TS/app.env (0600), local storage
    in the scratch dir – plus the scratch Keycloak/OIDC values. backend/.env is NOT loaded (IRONVISION_DOTENV=0) and nothing
    is copied from production, so a missing setting fails here exactly as on the Droplet. Validation is unchanged."""
    return {**_base_env(), "IRONVISION_DOTENV": "0", "APP_ENV": "production", "DATABASE_URL": target_url,
            "JWT_SECRET": _read_env(d / "app.env")["JWT_SECRET"], "STORAGE_DRIVER": "local", "STORAGE_LOCAL_ROOT": str(d / "storage"),
            "CORS_ORIGINS": kc_env["FRONTEND_URL"], "AUTH_PROVIDERS": "oidc", **kc_env}


def _fault() -> str:
    """Test-only fault injection for the failure-path tests; honoured ONLY in local/test mode (RECOVER_LOCAL=1)."""
    return os.environ.get("RECOVER_SCRATCH_FAULT", "") if os.environ.get("RECOVER_LOCAL") == "1" else ""


def cmd_setup(a) -> int:
    d, kc, app = sdir(a.ts), a.kc_url.rstrip("/"), a.app_url.rstrip("/")
    target = f"rec_target_{a.ts}"
    if not rv.SCRATCH.match(target):
        raise rv.RecoveryError("non-scratch target DB")
    k = _read_env(d / "kc.env")
    r = _results(a.ts)
    s = {"KEYCLOAK_CONFIGURATOR_CLIENT_SECRET": _pw(), "KEYCLOAK_ADMIN_PASSWORD": _pw(), "OIDC_CLIENT_SECRET": _pw(),
         "KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET": _pw(), "KEYCLOAK_BACKEND_CLIENT_SECRET": _pw(), "KEYCLOAK_DEMO_PASSWORD": _pw()}
    demo_user = f"rehearsal-demo-launcher-{secrets.token_hex(4)}"
    issuer = f"{kc}/realms/{REALM}"
    kc_env = {**s, "KEYCLOAK_URL": kc, "KEYCLOAK_REALM": REALM, "OIDC_ISSUER": issuer, "OIDC_CLIENT_ID": "ironvision-app",
              "OIDC_REDIRECT_URI": f"{app}/api/v1/auth/oidc/callback", "OIDC_POST_LOGOUT_REDIRECT_URI": f"{app}/login", "FRONTEND_URL": app,
              "KEYCLOAK_CONFIGURATOR_CLIENT_ID": "ironvision-configurator", "KEYCLOAK_ADMIN_USERNAME": "rehearsal-admin",
              "KC_BOOTSTRAP_ADMIN_USERNAME": k["KC_BOOTSTRAP_ADMIN_USERNAME"], "KC_BOOTSTRAP_ADMIN_PASSWORD": k["KC_BOOTSTRAP_ADMIN_PASSWORD"],
              "KEYCLOAK_DEMO_USERNAME": demo_user, "KEYCLOAK_DEMO_LAUNCHER_CLIENT_ID": "ironvision-demo-launcher",
              "KEYCLOAK_BACKEND_CLIENT_ID": "ironvision-backend", "DEPLOYMENT_KIND": "demo", "KEYCLOAK_ALLOW_REGISTRATION": "false"}
    env = _scratch_app_env(d, rv.db_url(target), kc_env)
    assert_scratch_targets("setup", env["DATABASE_URL"], kc)
    assert_scratch_targets("setup (OIDC issuer)", kc=issuer)
    hide = [*s.values(), k["KC_BOOTSTRAP_ADMIN_PASSWORD"], k["KC_DB_PASSWORD"], env["JWT_SECRET"]]
    # admin.env FIRST – before any scratch Keycloak user can exist – so cleanup can always delete them (Droplet 20261017t214603:
    # users existed, admin.env was only written at the very end of setup, migrate failed in between → FileNotFoundError)
    _env_file(d / "admin.env", {"CID": env["KEYCLOAK_CONFIGURATOR_CLIENT_ID"], "SECRET": s["KEYCLOAK_CONFIGURATOR_CLIENT_SECRET"]})
    r["kc_users"] = {"demo_launcher": {"username": demo_user, "id": None}}
    r["restored_before"] = restored_fingerprint(target, None)
    _save(a.ts, r)
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
    r["kc_users"]["e2e"] = {"username": uname, "id": None}
    _save(a.ts, r)
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
    lenv = {k2: v for k2, v in env.items() if not (k2 == "JWT_SECRET" and _fault() == "migrate")}  # test: Droplet failure
    link = rv.kc_link_scratch(env["DATABASE_URL"], a.ts, env=lenv)
    r["demo_launcher_link"] = {k2: v for k2, v in link.items() if k2 != "output"} | {"output_tail": _redact(link.get("output", "")[-800:], hide)}
    if link["rc"]:
        _save(a.ts, r)
        raise rv.RecoveryError("keycloak-migrate (demo-launcher link) into the scratch DB failed (see scratch-sso json)")
    _env_file(d / "backend.env", {"SCRATCH_KC_URL": kc, "SCRATCH_OIDC_ISSUER": issuer, "SCRATCH_OIDC_CLIENT_SECRET": s["OIDC_CLIENT_SECRET"],
                                  "SCRATCH_APP_URL": app, "SCRATCH_DEMO_USERNAME": demo_user, "SCRATCH_DEMO_PASSWORD": s["KEYCLOAK_DEMO_PASSWORD"],
                                  "SCRATCH_DEMO_LAUNCHER_CLIENT_SECRET": s["KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET"],
                                  "SCRATCH_BACKEND_CLIENT_SECRET": s["KEYCLOAK_BACKEND_CLIENT_SECRET"]})
    _write(rv.RDIR / ".e2e-credentials", f"{uname}\n{upw + 'x' if _fault() == 'login' else upw}\n")
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


OK_STATUSES = ("done", "already-gone", "moot")
S_USERS, S_CONT, S_DB, S_APP, S_REST, S_SECRETS = ("1 scratch Keycloak users deleted", "2 scratch Keycloak container removed",
                                                   "3 scratch Keycloak DB + role dropped", "4 scratch app records deleted",
                                                   "5 restored users unchanged (before == after)", "6 secret files + dir deleted (LAST)")


def _step(r: dict, name: str, status: str, detail: str = "") -> None:
    r.setdefault("cleanup_steps", {})[name] = {"status": status, "detail": detail}


def cmd_cleanup_users(a) -> int:
    """Step 1 – needs scratch-sso-TS/admin.env (written by setup BEFORE any user exists) and the running scratch Keycloak."""
    r, d, kc = _results(a.ts), sdir(a.ts), (a.kc_url or "").rstrip("/")
    users = {k: v for k, v in (r.get("kc_users") or {}).items() if v.get("username")}
    if not users:
        _step(r, S_USERS, "already-gone", "no scratch Keycloak user was ever created")
        _save(a.ts, r)
        return 0
    try:
        assert_scratch_targets("cleanup-users", kc=kc)
        if not (d / "admin.env").is_file():
            raise rv.RecoveryError(f"{d.name}/admin.env missing – scratch admin credentials gone")
        ad = _read_env(d / "admin.env")
        h, done = _admin(kc, ad["CID"], ad["SECRET"]), []
        for v in users.values():
            uid = v.get("id") or ((httpx.get(f"{kc}/admin/realms/{REALM}/users", headers=h, timeout=20,
                                             params={"username": v["username"], "exact": "true"}).json() or [{}])[0].get("id"))
            if not uid:
                done.append(f"{v['username']}: already gone")
                continue
            st = httpx.delete(f"{kc}/admin/realms/{REALM}/users/{uid}", headers=h, timeout=20).status_code
            if st not in (204, 404):
                raise rv.RecoveryError(f"delete {v['username']} → HTTP {st}")
            done.append(f"{v['username']}: {'deleted' if st == 204 else 'already gone'}")
        _step(r, S_USERS, "done", "; ".join(done))
    except Exception as exc:  # noqa: BLE001 – recorded; resolved to `moot` only if the whole scratch Keycloak + DB are gone
        _step(r, S_USERS, "failed", rv.redact(f"{type(exc).__name__}: {exc}")[:240])
    _save(a.ts, r)
    return 0


def _exists(cur, kind: str, name: str) -> bool:
    q = "select 1 from pg_database where datname = %s" if kind == "db" else "select 1 from pg_roles where rolname = %s"
    cur.execute(q, (name,))
    return cur.fetchone() is not None


def cmd_cleanup_finish(a) -> int:
    """Steps 2–6 after cleanup-users (pass, fail or abort), every step idempotent (already gone = success): container status
    (from recover.sh) → scratch Keycloak DB + role → scratch app records → restored-users check → secret files LAST. Records each
    step in scratch-sso-TS.json and the rehearsal report; any incomplete required step fails the rehearsal."""
    from psycopg import sql
    r = _results(a.ts)
    _step(r, S_CONT, "done" if a.container_rc == 0 else "failed", f"rc={a.container_rc}")
    name, target = kc_db_name(a.ts), f"rec_target_{a.ts}"
    try:
        eng, raw = _raw()
        cur = raw.cursor()
        had = [k for k in ("db", "role") if _exists(cur, k, name)]
        cur.execute(sql.SQL("drop database if exists {} with (force)").format(sql.Identifier(name)))
        cur.execute(sql.SQL("drop role if exists {}").format(sql.Identifier(name)))
        left = [k for k in ("db", "role") if _exists(cur, k, name)]
        target_exists = _exists(cur, "db", target)
        raw.close()
        eng.dispose()
        _step(r, S_DB, "failed" if left else ("done" if had else "already-gone"), f"{name}: dropped {had or 'nothing (already gone)'}"
              + (f", STILL PRESENT {left}" if left else ""))
    except Exception as exc:  # noqa: BLE001
        target_exists = None
        _step(r, S_DB, "failed", rv.redact(f"{type(exc).__name__}: {exc}")[:240])
    try:
        if not r.get("scratch_org_id"):
            _step(r, S_APP, "already-gone", "no scratch org/user was created")
        elif target_exists is False:
            _step(r, S_APP, "already-gone", f"scratch target DB {target} already dropped (records went with it)")
        else:
            assert_scratch_targets("cleanup-finish", db_url=rv.db_url(target))
            eng = create_engine(rv.db_url(target))
            with eng.begin() as cx:
                o = {"o": r["scratch_org_id"]}
                cx.execute(text("delete from auth_identities where user_id in (select id from users where org_id = :o)"), o)
                cx.execute(text("delete from role_assignments where user_id in (select id from users where org_id = :o)"), o)
                cx.execute(text("delete from audit_events where org_id = :o"), o) if _has_col(cx, "audit_events", "org_id") else None
                n = cx.execute(text("delete from users where org_id = :o"), o).rowcount
                n += cx.execute(text("delete from organizations where id = :o"), o).rowcount
            eng.dispose()
            _step(r, S_APP, "done" if n else "already-gone", f"{n} scratch org/user rows deleted from {target}")
    except Exception as exc:  # noqa: BLE001
        _step(r, S_APP, "failed", rv.redact(f"{type(exc).__name__}: {exc}")[:240])
    try:
        if r.get("restored_before") and target_exists is not False:
            r["restored_after"] = restored_fingerprint(target, r.get("scratch_org_id"))
            b, f = r["restored_before"], r["restored_after"]
            r["restored_changed"] = sorted(e for e in {*b["rows"], *f["rows"]} if b["rows"].get(e) != f["rows"].get(e))
            _step(r, S_REST, "done" if b["sha256"] == f["sha256"] else "failed",
                  f"{f['users']} restored users (8 + admin) compared; changed: {r['restored_changed'] or 'none'}")
        else:
            _step(r, S_REST, "already-gone", "nothing to compare (setup never fingerprinted, or the scratch target DB is gone)")
    except Exception as exc:  # noqa: BLE001
        _step(r, S_REST, "failed", rv.redact(f"{type(exc).__name__}: {exc}")[:240])
    st = r["cleanup_steps"]
    if st.get(S_USERS, {}).get("status") == "failed" and st[S_CONT]["status"] in OK_STATUSES and st[S_DB]["status"] in OK_STATUSES:
        st[S_USERS] = {"status": "moot", "detail": st[S_USERS]["detail"] + " → NOT a leftover: the scratch Keycloak container and its "
                       f"database {name} were removed, so these users no longer exist anywhere"}
    had_files = sdir(a.ts).exists() or (rv.RDIR / ".e2e-credentials").exists()
    shutil.rmtree(sdir(a.ts), ignore_errors=True)
    (rv.RDIR / ".e2e-credentials").unlink(missing_ok=True)
    gone = not sdir(a.ts).exists() and not (rv.RDIR / ".e2e-credentials").exists()
    _step(r, S_SECRETS, ("done" if had_files else "already-gone") if gone else "failed", f"{sdir(a.ts).name}/ + .e2e-credentials")
    ok = all(v["status"] in OK_STATUSES for v in st.values())
    r["cleanup"] = {k: v["status"] in OK_STATUSES for k, v in st.items()}
    r["cleanup_ok"] = ok
    _save(a.ts, r)
    fs = sorted(rv.RDIR.glob(f"rehearsal-{a.ts}.json"))
    if fs:
        body = json.loads(fs[-1].read_text())
        body["scratch_sso"] = dict(r)
        body["failures"] = [f for f in body["failures"] if not f.startswith("scratch SSO ")]
        if not ok:
            body["failures"].append("scratch SSO cleanup incomplete: " + ", ".join(f"{k} [{v['status']}: {v['detail']}]" for k, v in st.items()
                                                                                 if v["status"] not in OK_STATUSES) + " (production untouched)")
        if not r.get("steps", {}).get("setup"):
            body["failures"].append("scratch SSO stack setup failed – SSO e2e could not run (see scratch_sso in the report)")
        body["passed"] = not body["failures"]
        rv.write_report("rehearsal", a.ts, body)
    print(f"[scratch-sso] cleanup {'OK' if ok else 'INCOMPLETE'} ({a.ts}): " + json.dumps({k: v["status"] for k, v in st.items()}))
    return 0 if ok else 1


def cmd_leftovers(a) -> int:
    """Timestamps of scratch SSO runs whose cleanup did not finish (dir present, json not cleanup_ok, rec_kc_* DB/role left)."""
    if a.ts:
        kc_db_name(a.ts)
        print(a.ts)
        return 0
    tss = set()
    for p in rv.RDIR.glob("scratch-sso-*"):
        m = re.fullmatch(r"scratch-sso-(\d{8}t\d{6})(\.json)?", p.name)
        if m and (p.is_dir() or not json.loads(p.read_text()).get("cleanup_ok")):
            tss.add(m.group(1))
    eng = create_engine(rv.admin_url())
    with eng.connect() as c:
        for (n,) in c.execute(text(r"select datname from pg_database where datname like 'rec\_kc\_%' "
                                   r"union select rolname from pg_roles where rolname like 'rec\_kc\_%'")):
            if rv.SCRATCH.match(n):
                tss.add(n.removeprefix("rec_kc_"))
    eng.dispose()
    for t in sorted(tss):
        print(t)
    return 0


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
    for n in ("prepare", "setup", "cleanup-users", "cleanup-finish", "leftovers"):
        p = sp.add_parser(n)
        p.add_argument("--ts", required=n != "leftovers", default="")
        if n in ("setup", "cleanup-users"):
            p.add_argument("--kc-url", required=n == "setup", default="")
        if n == "setup":
            p.add_argument("--app-url", required=True)
        if n == "cleanup-finish":
            p.add_argument("--container-rc", type=int, default=0)
    p = sp.add_parser("prod-oidc-check")
    p.add_argument("--issuer", required=True)
    a = ap.parse_args()
    fn = {"prepare": cmd_prepare, "setup": cmd_setup, "cleanup-users": cmd_cleanup_users, "cleanup-finish": cmd_cleanup_finish,
          "leftovers": cmd_leftovers, "prod-oidc-check": cmd_prod_oidc_check}[a.cmd]
    try:
        return fn(a)
    except rv.RecoveryError as exc:
        print(f"[scratch-sso] FAIL {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    _ = uuid
    sys.exit(main())
