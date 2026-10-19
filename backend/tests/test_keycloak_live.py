"""LIVE integration tests against a REAL Keycloak 26 (no mocks). Skipped unless KEYCLOAK_LIVE_URL is set.

Run (see docs/KEYCLOAK.md → "Live tests"):  . /opt/kc/kcenv.sh && KEYCLOAK_LIVE_URL=$KEYCLOAK_URL pytest -n 0 tests/test_keycloak_live.py
Requires the env from kcenv.sh (KEYCLOAK_URL, realm/client/admin/configurator secrets, OIDC_* pointing at the live realm).
Optional KEYCLOAK_LIVE_RESTART_CMD restarts Keycloak mid-session.
"""
import csv
import html
import io
import json
import os
import re
import subprocess
import time
import uuid
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from tests.conftest import auth

LIVE = os.environ.get("KEYCLOAK_LIVE_URL")
pytestmark = pytest.mark.skipif(not LIVE, reason="REAL Keycloak not available (set KEYCLOAK_LIVE_URL) – live tests skipped")
REALM = os.environ.get("KEYCLOAK_REALM", "ironvision-demo")
STATE: dict = {}


@pytest.fixture(scope="module", autouse=True)
def live_env(tmp_path_factory):
    old = {k: os.environ.get(k) for k in ("AUTH_PROVIDERS", "FRONTEND_URL", "CREDENTIALS_DIR")}
    os.environ["AUTH_PROVIDERS"] = "dev_password,oidc"
    os.environ["FRONTEND_URL"] = "http://spa.test"
    STATE["dir"] = tmp_path_factory.mktemp("kc")
    from app.security import oidc
    oidc._discovery.clear()
    oidc._jwks.clear()
    k = kc()  # disposable test Keycloak: start every run from an empty user list in the app realm
    if k.realm(REALM):
        for u in k.get(f"/{REALM}/users", params={"max": 1000}) or []:
            k.delete(f"/{REALM}/users/{u['id']}")
    yield
    for k, v in old.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def browser() -> httpx.Client:
    """Scripted browser; Keycloak marks cookies Secure, the test Keycloak is plain http://localhost, so drop the flag client-side."""
    b = httpx.Client()

    def insecure(_):
        for c in b.cookies.jar:
            c.secure = False
    b.event_hooks["response"] = [insecure]
    return b


def kc():
    from app.services.keycloak_admin import KeycloakAdmin
    return KeycloakAdmin().login()


def run_cli(*args) -> tuple[int, str]:
    from app import cli
    buf = io.StringIO()
    with redirect_stdout(buf):
        try:
            rc = cli.main(list(args))
        except SystemExit as e:  # refusals raise SystemExit(message)
            print(e.code)
            rc = 99
    return rc, buf.getvalue()


def run_cfg(*args) -> tuple[int, str]:
    from app.tools import keycloak_config
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = keycloak_config.main(list(args))
    return rc, buf.getvalue()


def _form(page: str) -> tuple[str, dict] | None:
    m = re.search(r"<form[^>]*\baction=\"([^\"]+)\"", page)
    if m is None and ("Access denied" in page or "access denied" in page.lower()):
        return None  # Keycloak "Access denied" page (deny-access authenticator)
    assert m, re.sub(r"\s+", " ", re.sub(r"<(script|style|head)[^>]*>.*?</\1>|<[^>]+>", " ", page, flags=re.S))[:600]
    hidden = dict(re.findall(r"<input[^>]*type=\"hidden\"[^>]*name=\"([^\"]+)\"[^>]*value=\"([^\"]*)\"", page))
    return html.unescape(m.group(1)), {k: html.unescape(v) for k, v in hidden.items()}


def browser_login(client, b: httpx.Client, username: str, password: str, totp=None) -> httpx.Response:
    """Scripted browser: app /oidc/login → Keycloak forms (password, OTP enrolment/OTP) → app callback. Returns the callback response."""
    r = b.get(client.get("/api/v1/auth/oidc/login", follow_redirects=False).headers["location"])
    for _ in range(6):
        if r.status_code in (302, 303):
            loc = r.headers["location"]
            if loc.startswith("http://testserver/"):
                return client.get(loc.replace("http://testserver", ""), follow_redirects=False)
            r = b.get(loc)
            continue
        page = r.text
        f = _form(page)
        if f is None:
            return r
        action, data = f
        if 'name="password"' in page:
            payload = {**data, "password": password, "credentialId": ""}
            if 'name="username"' in page:
                payload["username"] = username
            r = b.post(action, data=payload)
            if r.status_code == 200 and 'name="password"' in r.text:
                return r  # Keycloak re-rendered the password form: bad credentials
        elif 'name="username"' in page:  # two-step realm flow: username first (demo-launcher users are denied here)
            r = b.post(action, data={**data, "username": username})
            if r.status_code == 200 and 'name="username"' in r.text:
                return r
        elif 'name="totpSecret"' in page:
            import base64
            secret = base64.b32encode(data["totpSecret"].encode()).decode().rstrip("=")  # Keycloak posts the raw key; apps use base32
            STATE.setdefault("totp", {})[username] = secret
            r = b.post(action, data={**data, "totp": totp(secret), "userLabel": "pytest"})
        elif 'name="otp"' in page:
            r = b.post(action, data={**data, "otp": totp(STATE["totp"][username])})
        else:
            raise AssertionError(f"unexpected Keycloak page: {page[:400]}")
    raise AssertionError("login did not finish")


def exchange(client, cb: httpx.Response) -> dict:
    assert cb.status_code in (302, 307), cb.text[:300]
    code = parse_qs(urlparse(cb.headers["location"]).query)["oidc_code"][0]
    r = client.post("/api/v1/auth/oidc/exchange", json={"code": code})
    assert r.status_code == 200, r.text
    return r.json()


def fresh_otp(secret: str) -> str:
    import pyotp
    t = pyotp.TOTP(secret)
    last = STATE.get("last_otp", 0)
    while int(time.time()) // 30 <= last:  # Keycloak rejects code reuse inside a window
        time.sleep(1)
    STATE["last_otp"] = int(time.time()) // 30
    return t.now()


def _users():
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import RoleAssignment, User
    with SessionLocal() as db:
        active = list(db.scalars(select(User).where(User.is_active.is_(True)).order_by(User.email)))
        admin = db.scalar(select(User).join(RoleAssignment, RoleAssignment.user_id == User.id)
                          .where(RoleAssignment.role == "platform_admin", User.is_active.is_(True)))
        return [u.email for u in active], admin.email if admin else None


def test_01_configurator_apply_is_idempotent():
    rc, out = run_cfg("apply", "--yes")
    assert rc == 0, out
    rc, out = run_cfg("plan")
    assert rc == 0 and "no changes (in sync)" in out, out
    r = kc().realm(REALM)
    assert r["bruteForceProtected"] and r["registrationAllowed"] == (os.environ.get("KEYCLOAK_ALLOW_REGISTRATION") == "true") and not r["resetPasswordAllowed"] and r["accessTokenLifespan"] == 300
    c = kc().client(REALM, os.environ["OIDC_CLIENT_ID"])
    assert not c["publicClient"] and not c["directAccessGrantsEnabled"] and not c["implicitFlowEnabled"]
    assert c["attributes"]["pkce.code.challenge.method"] == "S256"
    boot = kc().users_by("master", username=os.environ["KC_BOOTSTRAP_ADMIN_USERNAME"])
    assert boot and boot[0]["enabled"] is False, "bootstrap admin must be disabled after first apply"
    assert kc().realm("master")["browserFlow"] == "browser-otp-required"


def test_02_drift_is_planned_then_fixed(monkeypatch):
    monkeypatch.setenv("SESSION_IDLE_MINUTES", "45")
    rc, out = run_cfg("plan")
    assert "ssoSessionIdleTimeout: 1800 -> 2700" in out, out
    assert run_cfg("apply", "--yes")[0] == 0 and kc().realm(REALM)["ssoSessionIdleTimeout"] == 2700
    monkeypatch.setenv("SESSION_IDLE_MINUTES", "30")
    assert run_cfg("apply", "--yes")[0] == 0 and "no changes" in run_cfg("plan")[1]


def test_03_migration_dry_run_conflicts_and_apply(tmp_path):
    emails, admin = _users()
    STATE["admin"] = admin
    others = [e for e in emails if e not in ("isso@aegisrmf.demo", admin)]
    taken, mismatch, owner = others[0], others[1], others[2]
    k = kc()
    from app.db import SessionLocal
    from app.models import User
    from app.services import identity_map
    from app.services.keycloak_admin import created_id
    x = created_id(k.post(f"/{REALM}/users", {"username": taken, "email": taken, "enabled": True}))
    if os.environ.get("KEYCLOAK_DEMO_USERNAME"):  # demo deployment (launcher configured): app.seed always creates the demo account
        from app.seed import ensure_demo_launcher_sandbox
        os.environ.setdefault("SAMPLES_DIR", str(Path(__file__).resolve().parents[2] / "samples"))
        with SessionLocal() as db:
            ensure_demo_launcher_sandbox(db)
    with SessionLocal() as db:  # Keycloak user for `taken` is already mapped to a different app user
        identity_map.map_identity(db, user=db.query(User).filter(User.email == owner).one(), issuer=os.environ["OIDC_ISSUER"], sub=x,
                                  reason="pytest conflict setup", actor="pytest")
        db.commit()
    k.post(f"/{REALM}/users", {"username": mismatch, "email": f"other-{uuid.uuid4().hex[:6]}@example.org", "enabled": True})
    report = tmp_path / "plan.json"
    rc, out = run_cli("keycloak-migrate", "--report", str(report))
    assert rc == 0 and "DRY RUN" in out
    plan = json.loads(report.read_text())
    rows = {r["email"]: r for r in plan["users"]}
    assert rows[taken]["action"] == "CONFLICT" and "already mapped to another app user" in rows[taken]["reason"]
    assert rows[mismatch]["action"] == "CONFLICT" and "email differs" in rows[mismatch]["reason"]
    assert rows["isso@aegisrmf.demo"]["action"] == "create"
    assert oct(report.stat().st_mode & 0o777) == "0o600"
    h = plan["plan_hash"]
    creds = tmp_path / "secrets"
    common = ["keycloak-migrate", "--apply", "--yes", "--create-identities", "--link", "--credentials-dir", str(creds), "--report", str(tmp_path / "r2.json")]
    rc, out = run_cli(*common, "--plan-hash", h)
    assert rc == 3  # CONFLICT rows block apply without --allow-conflicts
    rc, out = run_cli(*common, "--allow-conflicts", "--plan-hash", "deadbeefdeadbeef")
    assert rc == 3  # stale / wrong plan hash
    rc, out = run_cli(*common, "--allow-conflicts", "--plan-hash", h)
    assert rc == 99 and "--backup-ref" in out  # no backup → refuse
    bk = tmp_path / "backup"
    bk.mkdir()
    (bk / "manifest.json").write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat()}))
    rc, out = run_cli(*common, "--allow-conflicts", "--plan-hash", h, "--backup-ref", str(bk))
    assert rc == 0, out
    files = list(creds.glob("demo-credentials-*.csv"))
    assert len(files) == 1 and oct(files[0].stat().st_mode & 0o777) == "0o600"
    rows_csv = list(csv.DictReader(files[0].open()))
    pws = [r["password"] for r in rows_csv]
    assert len(set(pws)) == len(pws) and all(len(p) >= 20 for p in pws)  # individual, unique
    STATE["pw"] = {r["email"]: r["password"] for r in rows_csv}
    rc, out = run_cli("keycloak-migrate", "--report", str(tmp_path / "r3.json"))
    again = {r["email"]: r for r in json.loads((tmp_path / "r3.json").read_text())["users"]}
    assert again["isso@aegisrmf.demo"]["action"] == "ok"  # idempotent re-run
    from app.db import SessionLocal
    from app.models import AuditEvent
    with SessionLocal() as db:
        ev = db.query(AuditEvent).filter(AuditEvent.action == "keycloak.migrate.apply").order_by(AuditEvent.seq.desc()).first()
        assert ev and "password" not in json.dumps(ev.details).lower().replace("credentials_file", "")


def test_04_oidc_login_success_and_role_enforcement(client):
    b = browser()
    tr = exchange(client, browser_login(client, b, "isso@aegisrmf.demo", STATE["pw"]["isso@aegisrmf.demo"]))
    assert tr["user"]["email"] == "isso@aegisrmf.demo" and tr["user"]["auth_provider"] == "oidc"
    STATE["isso_token"], STATE["isso_browser"] = tr["access_token"], b
    assert client.get("/api/v1/admin/identity-mappings", headers=auth(tr["access_token"])).status_code == 403
    if STATE.get("admin") in STATE["pw"]:
        at = exchange(client, browser_login(client, browser(), STATE["admin"], STATE["pw"][STATE["admin"]]))["access_token"]
        maps = client.get("/api/v1/admin/identity-mappings", headers=auth(at)).json()
        assert any(m["email"] == "isso@aegisrmf.demo" and m["mapped_by"].startswith("cli:") and m["reason"] for m in maps)


def test_05_invalid_credentials_rejected_by_keycloak(client):
    r = browser_login(client, browser(), "isso@aegisrmf.demo", "definitely-wrong-password")
    assert r.status_code == 200 and ("Invalid password" in r.text or "Invalid username or password" in r.text)  # two-step flow wording


def test_06_unmapped_identity_is_403_and_audited(client):
    k = kc()
    email = f"unmapped-{uuid.uuid4().hex[:6]}@example.org"
    from app.services.keycloak_admin import created_id
    uid = created_id(k.post(f"/{REALM}/users", {"username": email, "email": email, "emailVerified": True, "firstName": "U", "lastName": "M",
                                                "enabled": True}))
    k.set_password(REALM, uid, "Unmapped-Pass-123456", False)
    cb = browser_login(client, browser(), email, "Unmapped-Pass-123456")
    assert cb.status_code == 403 and "not mapped" in cb.text
    from app.db import SessionLocal
    from app.models import AuditEvent
    with SessionLocal() as db:
        ev = db.query(AuditEvent).filter(AuditEvent.action == "auth.login", AuditEvent.outcome == "denied").order_by(AuditEvent.seq.desc()).first()
        assert ev.details["reason"] == "identity_not_mapped" and uid in ev.details["subject"]


def test_07_otp_enrolment_then_totp_login(client):
    rc, out = run_cli("keycloak-user", "reset-mfa", "isso@aegisrmf.demo")
    assert rc == 0, out
    pw = STATE["pw"]["isso@aegisrmf.demo"]
    tr = exchange(client, browser_login(client, browser(), "isso@aegisrmf.demo", pw, totp=fresh_otp))
    assert "isso@aegisrmf.demo" in STATE["totp"]
    assert tr["user"]["email"] == "isso@aegisrmf.demo"
    b = browser()
    tr = exchange(client, browser_login(client, b, "isso@aegisrmf.demo", pw, totp=fresh_otp))  # now OTP form (configured)
    STATE["isso_token"], STATE["isso_browser"] = tr["access_token"], b
    rc, out = run_cli("keycloak-user", "list")
    assert re.search(r"isso@aegisrmf\.demo\s+true\s+yes", out), out


def test_08_logout_ends_keycloak_session(client):
    b, tok = STATE["isso_browser"], STATE["isso_token"]
    sso = b.get(client.get("/api/v1/auth/oidc/login", follow_redirects=False).headers["location"])
    assert sso.status_code == 302 and sso.headers["location"].startswith("http://testserver/")  # SSO active: no form
    out = client.post("/api/v1/auth/logout", headers=auth(tok))
    assert out.status_code == 200 and "id_token_hint=" in out.json()["end_session_url"]
    r = b.get(out.json()["end_session_url"])
    assert r.status_code == 302 and r.headers["location"] == os.environ["OIDC_POST_LOGOUT_REDIRECT_URI"]
    assert client.get("/api/v1/auth/me", headers=auth(tok)).status_code == 401  # app session revoked
    again = b.get(client.get("/api/v1/auth/oidc/login", follow_redirects=False).headers["location"])
    assert again.status_code == 200 and 'name="username"' in again.text  # Keycloak session ended → login form again


def test_09_session_idle_expiry(client):
    tr = exchange(client, browser_login(client, browser(), "isso@aegisrmf.demo", STATE["pw"]["isso@aegisrmf.demo"], totp=fresh_otp))
    import jwt as pyjwt

    from app.db import SessionLocal
    from app.models import AuthSession
    sid = pyjwt.decode(tr["access_token"], options={"verify_signature": False})["sid"]
    assert client.get("/api/v1/auth/me", headers=auth(tr["access_token"])).status_code == 200
    with SessionLocal() as db:
        db.get(AuthSession, uuid.UUID(sid)).idle_expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    assert client.get("/api/v1/auth/me", headers=auth(tr["access_token"])).status_code == 401


def test_10_cross_tenant_denial(client):
    from app.db import SessionLocal
    from app.models import Organization, User
    from app.services import identity_map
    from app.services.keycloak_admin import created_id
    email = f"tenant-b-{uuid.uuid4().hex[:6]}@example.org"
    with SessionLocal() as db:
        org = Organization(name=f"Tenant B {email}", slug=email.split("@")[0], is_synthetic=False, source="pytest")
        db.add(org)
        db.flush()
        u = User(org_id=org.id, email=email, display_name="Tenant B", source="pytest")
        db.add(u)
        db.flush()
        k = kc()
        uid = created_id(k.post(f"/{REALM}/users", {"username": email, "email": email, "emailVerified": True, "firstName": "T", "lastName": "B",
                                                    "enabled": True}))
        k.set_password(REALM, uid, "Tenant-B-Pass-123456", False)
        identity_map.map_identity(db, user=u, issuer=os.environ["OIDC_ISSUER"], sub=uid, reason="pytest tenant B", actor="pytest")
        db.commit()
    at = exchange(client, browser_login(client, browser(), email, "Tenant-B-Pass-123456"))["access_token"]
    isso = exchange(client, browser_login(client, browser(), "isso@aegisrmf.demo", STATE["pw"]["isso@aegisrmf.demo"], totp=fresh_otp))
    theirs = client.get("/api/v1/systems", headers=auth(isso["access_token"])).json()
    assert theirs, "ISSO should see demo-org systems"
    assert client.get("/api/v1/systems", headers=auth(at)).json() == []
    assert client.get(f"/api/v1/systems/{theirs[0]['id']}", headers=auth(at)).status_code in (403, 404)


@pytest.mark.skipif(not os.environ.get("KEYCLOAK_LIVE_RESTART_CMD"), reason="set KEYCLOAK_LIVE_RESTART_CMD to test a Keycloak restart")
def test_11_restart_keycloak_and_backend_mid_session(client):
    b = browser()
    tr = exchange(client, browser_login(client, b, "isso@aegisrmf.demo", STATE["pw"]["isso@aegisrmf.demo"], totp=fresh_otp))
    pending = client.get("/api/v1/auth/oidc/login", follow_redirects=False).headers["location"]  # state stored in DB
    subprocess.run(os.environ["KEYCLOAK_LIVE_RESTART_CMD"], shell=True, check=True, timeout=240)
    from app.security import oidc
    oidc._discovery.clear()
    oidc._jwks.clear()  # simulate a backend restart: caches gone, pending state lives in Postgres
    assert client.get("/api/v1/auth/me", headers=auth(tr["access_token"])).status_code == 200  # app session independent of IdP uptime
    r = b.get(pending)  # Keycloak user sessions are persistent in 26.x → SSO survives the restart
    assert r.status_code == 302 and r.headers["location"].startswith("http://testserver/")
    cb = client.get(r.headers["location"].replace("http://testserver", ""), follow_redirects=False)
    assert exchange(client, cb)["user"]["email"] == "isso@aegisrmf.demo"


ADMIN_TOTP_FILE = Path(os.environ.get("KEYCLOAK_LIVE_ADMIN_TOTP_FILE", "/tmp/kc-live-admin-totp"))  # survives re-runs of this module


def _admin_console_login(b: httpx.Client, password: str, otp=None) -> httpx.Response:
    """Browser login to the master realm as the admin console (public client security-admin-console, PKCE). Returns the last
    response: a 302 to the console with ?code=… once every required step is done, else the Keycloak page that blocks."""
    import base64
    import hashlib
    import secrets as _s
    verifier = _s.token_urlsafe(48)
    STATE["admin_verifier"] = verifier
    base = os.environ["KEYCLOAK_URL"].rstrip("/")
    STATE["admin_redirect"] = f"{base}/admin/master/console/"
    r = b.get(f"{base}/realms/master/protocol/openid-connect/auth", params={
        "client_id": "security-admin-console", "redirect_uri": STATE["admin_redirect"], "response_type": "code", "scope": "openid",
        "state": _s.token_urlsafe(8), "code_challenge_method": "S256",
        "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()})
    for _ in range(8):
        if r.status_code in (302, 303):
            if r.headers["location"].startswith(STATE["admin_redirect"]):
                return r  # back at the console with ?code=…
            r = b.get(r.headers["location"])  # Keycloak-internal hop (e.g. required action)
            continue
        page = r.text
        action, data = _form(page)
        if 'name="password"' in page:
            r = b.post(action, data={**data, "username": os.environ["KEYCLOAK_ADMIN_USERNAME"], "password": password, "credentialId": ""})
            if r.status_code == 200 and 'name="password"' in r.text:
                return r
        elif 'name="totpSecret"' in page or 'name="otp"' in page:
            if otp is None:
                return r  # blocked by MFA: exactly what a password-only login must see
            if 'name="totpSecret"' in page:
                secret = base64.b32encode(data["totpSecret"].encode()).decode().rstrip("=")
                ADMIN_TOTP_FILE.write_text(secret)
                r = b.post(action, data={**data, "totp": otp(secret), "userLabel": "pytest-admin"})
            else:
                r = b.post(action, data={**data, "otp": otp(ADMIN_TOTP_FILE.read_text().strip())})
        else:
            raise AssertionError(f"unexpected admin login page: {page[:300]}")
    raise AssertionError("admin login did not finish")


def test_12_master_admin_requires_otp():
    pw = os.environ["KEYCLOAK_ADMIN_PASSWORD"]
    base = os.environ["KEYCLOAK_URL"].rstrip("/")
    if not ADMIN_TOTP_FILE.exists():
        assert kc().users_by("master", username=os.environ["KEYCLOAK_ADMIN_USERNAME"]), "named admin missing"
    # 1) password only → Keycloak stops at TOTP enrolment (first time) or the OTP form; no code, no token
    r = _admin_console_login(browser(), pw)
    assert r.status_code == 200 and ('name="totpSecret"' in r.text or 'name="otp"' in r.text), r.text[:300]
    assert "code=" not in r.headers.get("location", "")
    # 2) wrong password never reaches the OTP step
    r = _admin_console_login(browser(), pw + "-wrong")
    assert r.status_code == 200 and 'name="password"' in r.text and "Invalid username or password" in r.text
    # 3) password + TOTP → authorization code → admin access token that works on the Admin API
    r = _admin_console_login(browser(), pw, otp=fresh_otp)
    assert r.status_code == 302 and r.headers["location"].startswith(STATE["admin_redirect"]), r.text[:300]
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
    tok = httpx.post(f"{base}/realms/master/protocol/openid-connect/token", data={
        "grant_type": "authorization_code", "client_id": "security-admin-console", "code": code,
        "redirect_uri": STATE["admin_redirect"], "code_verifier": STATE["admin_verifier"]})
    assert tok.status_code == 200, tok.text
    at = tok.json()["access_token"]
    import jwt as pyjwt
    claims = pyjwt.decode(tok.json()["id_token"], options={"verify_signature": False})  # console uses lightweight access tokens
    admin_id = kc().users_by("master", username=os.environ["KEYCLOAK_ADMIN_USERNAME"])[0]["id"]
    assert claims["sub"] == admin_id and claims["azp"] == "security-admin-console"
    assert httpx.get(f"{base}/admin/realms/master/users", params={"max": 1}, headers={"Authorization": f"Bearer {at}"}).status_code == 200
    # 4) with OTP configured, the password grant (admin-cli, no TOTP) is refused too
    pg = httpx.post(f"{base}/realms/master/protocol/openid-connect/token", data={
        "grant_type": "password", "client_id": "admin-cli", "username": os.environ["KEYCLOAK_ADMIN_USERNAME"], "password": pw})
    # Keycloak answers "missing OTP" exactly like a wrong password (400 invalid_grant), so prove OTP is the blocker with a control:
    assert pg.status_code == 400 and pg.json() == {"error": "invalid_grant", "error_description": "Invalid user credentials"}, pg.text
    ok = httpx.post(f"{base}/realms/master/protocol/openid-connect/token", data={
        "grant_type": "password", "client_id": "admin-cli", "username": os.environ["KEYCLOAK_ADMIN_USERNAME"], "password": pw,
        "totp": fresh_otp(ADMIN_TOTP_FILE.read_text().strip())})
    assert ok.status_code == 200 and ok.json()["access_token"], ok.text  # same password + TOTP → token: OTP is what blocked it
    # 5) next browser login (OTP enrolled) shows the OTP form after the password, never a direct code
    r = _admin_console_login(browser(), pw)
    assert r.status_code == 200 and 'name="otp"' in r.text


def _launcher_grant(username: str, password: str) -> httpx.Response:
    """Test-side grant; ends the Keycloak session right away like the backend does (so session assertions stay meaningful)."""
    base = os.environ["KEYCLOAK_URL"].rstrip("/")
    a = (os.environ["KEYCLOAK_DEMO_LAUNCHER_CLIENT_ID"], os.environ["KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET"])
    r = _grant(base, username, password)
    if r.status_code == 200:
        httpx.post(f"{base}/realms/{REALM}/protocol/openid-connect/logout", auth=a, data={"refresh_token": r.json()["refresh_token"]})
    return r


def _grant(base: str, username: str, password: str) -> httpx.Response:
    return httpx.post(f"{base}/realms/{REALM}/protocol/openid-connect/token", data={
        "grant_type": "password", "username": username, "password": password, "scope": "openid"},
        auth=(os.environ["KEYCLOAK_DEMO_LAUNCHER_CLIENT_ID"], os.environ["KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET"]))


def _demo_kc_user() -> dict:
    return kc().users_by(REALM, username=os.environ["KEYCLOAK_DEMO_USERNAME"])[0]


def test_13_launcher_client_is_restricted_to_the_demo_user_by_keycloak():
    assert run_cfg("apply", "--yes")[0] == 0 and "no changes" in run_cfg("plan")[1]
    c = kc().client(REALM, os.environ["KEYCLOAK_DEMO_LAUNCHER_CLIENT_ID"])
    assert c["directAccessGrantsEnabled"] and not c["standardFlowEnabled"] and not c["implicitFlowEnabled"]
    assert not c["serviceAccountsEnabled"] and not c["publicClient"] and c["redirectUris"] == []
    assert c["attributes"].get("standard.token.exchange.enabled") == "false" and c["authenticationFlowBindingOverrides"]["direct_grant"]
    ok = _launcher_grant(os.environ["KEYCLOAK_DEMO_USERNAME"], os.environ["KEYCLOAK_DEMO_PASSWORD"])
    assert ok.status_code == 200 and ok.json()["id_token"]
    other = _launcher_grant("isso@aegisrmf.demo", STATE["pw"]["isso@aegisrmf.demo"])  # CORRECT password, wrong user
    assert other.status_code == 401 and "access_token" not in other.text  # Keycloak deny-access (HTML error), not a password error
    app_client = httpx.post(f"{os.environ['KEYCLOAK_URL']}/realms/{REALM}/protocol/openid-connect/token", data={
        "grant_type": "password", "username": os.environ["KEYCLOAK_DEMO_USERNAME"], "password": os.environ["KEYCLOAK_DEMO_PASSWORD"]},
        auth=(os.environ["OIDC_CLIENT_ID"], os.environ["OIDC_CLIENT_SECRET"]))
    assert app_client.status_code in (400, 401)  # the app client never allows password grants
    u = _demo_kc_user()
    assert not any(r["name"].startswith("default-roles-") for r in kc().get(f"/{REALM}/users/{u['id']}/role-mappings/realm"))


def test_14_demo_username_denied_on_browser_flow_and_cannot_be_locked(client):
    u = _demo_kc_user()
    path = f"/{REALM}/attack-detection/brute-force/users/{u['id']}"
    assert u["email"].endswith("@demo-launcher.invalid") and u["username"] != "demo@ironvision.ai"
    for _ in range(7):  # visitors only know the PUBLIC demo e-mail: it does not resolve to the launcher user → nothing to lock
        r = browser_login(client, browser(), "demo@ironvision.ai", "visitor-guess-wrong")
        assert r.status_code in (200, 302) and not r.headers.get("location", "").startswith("http://testserver/")
    bf = kc().get(path)
    assert bf["numFailures"] == 0 and bf["disabled"] is False, bf
    assert _launcher_grant(os.environ["KEYCLOAK_DEMO_USERNAME"], os.environ["KEYCLOAK_DEMO_PASSWORD"]).status_code == 200
    # even with the unpublished handle AND the right password the browser flow denies before any password step (no session)
    r = browser_login(client, browser(), os.environ["KEYCLOAK_DEMO_USERNAME"], os.environ["KEYCLOAK_DEMO_PASSWORD"])
    assert 'name="password"' not in r.text and not r.headers.get("location", "").startswith("http://testserver/")
    assert kc().get(f"/{REALM}/users/{u['id']}/sessions") == []
    kc().delete(path)  # Keycloak still counts that denial as a failure – documented: the handle must stay unpublished


def test_15_backend_demo_login_via_launcher(client, monkeypatch, tmp_path):
    from sqlalchemy import select

    from app.config import get_settings
    from app.db import SessionLocal
    from app.models import AuditEvent, Organization, System, User
    from app.services import sandbox as sbx
    with SessionLocal() as db:
        sbx.seed_demo_account(db, "Seed-Only-Password-123!")
        db.commit()
        from sqlalchemy import text as _t  # start unmapped (test_03 may have linked it, as a demo deployment does)
        db.execute(_t("delete from auth_identities where provider = 'oidc' and user_id = (select id from users where email = :e)"),
                   {"e": sbx.DEMO_EMAIL})
        db.commit()
        org = db.get(Organization, db.scalar(select(User.org_id).where(User.email == sbx.DEMO_EMAIL)))
        if org.sandbox_status != "ready":
            sbx.provision(db, org.id)
        other_system = db.scalar(select(System.id).where(System.org_id != org.id))
    for k, v in {"AUTH_PROVIDERS": "oidc", "ALLOW_DEMO_LOGIN": "true", "DEMO_LOGIN_RATE_LIMIT": "100/3600",
                 "DEMO_LOGIN_GLOBAL_RATE_LIMIT": "100/3600"}.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    try:
        assert client.get("/api/v1/auth/provider").json()["demo_login_enabled"] is True
        r = client.post("/api/v1/auth/demo-login")
        assert r.status_code == 403 and "not mapped" in r.text  # explicit mapping required, same rules as OIDC
        report = tmp_path / "d.json"
        run_cli("keycloak-migrate", "--report", str(report))
        plan = json.loads(report.read_text())
        assert {u["email"]: u for u in plan["users"]}[sbx.DEMO_EMAIL]["action"] == "link"
        bk = tmp_path / "bk"
        bk.mkdir()
        (bk / "manifest.json").write_text(json.dumps({"created_at": datetime.now(timezone.utc).isoformat()}))
        rc, out = run_cli("keycloak-migrate", "--apply", "--yes", "--link", "--allow-conflicts", "--plan-hash", plan["plan_hash"],
                          "--backup-ref", str(bk), "--credentials-dir", str(tmp_path / "s"), "--report", str(tmp_path / "d2.json"))
        assert rc == 0, out
        r = client.post("/api/v1/auth/demo-login")
        assert r.status_code == 200, r.text
        tr = r.json()
        assert tr["user"]["auth_provider"] == "oidc-demo" and tr["user"]["is_sandbox"] and tr["user"]["persona_role"] == "isso"
        assert "id_token" not in r.text and "eyJ" not in r.text.replace(tr["access_token"], "")  # no Keycloak token reaches the browser
        h = auth(tr["access_token"])
        assert client.get(f"/api/v1/systems/{other_system}", headers=h).status_code in (403, 404)  # other tenants invisible
        assert client.post("/api/v1/sandbox/act-as", json={"role": "sca"}, headers=h).status_code == 200
        assert kc().get(f"/{REALM}/users/{_demo_kc_user()['id']}/sessions") == []  # Keycloak session already ended
        with SessionLocal() as db:
            ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "auth.demo_login", AuditEvent.outcome == "success")
                           .order_by(AuditEvent.seq.desc()))
            assert ev.ip and ev.details["mode"] == "keycloak" and ev.details["client_ip"]
        out = client.post("/api/v1/auth/logout", headers=h)
        assert out.status_code == 200 and out.json()["end_session_url"] is None
        assert client.get("/api/v1/auth/me", headers=h).status_code == 401
        monkeypatch.setenv("DEMO_LOGIN_RATE_LIMIT", "1/3600")
        assert client.post("/api/v1/auth/demo-login").status_code == 429  # per IP
        monkeypatch.setenv("DEMO_LOGIN_RATE_LIMIT", "100/3600")
        monkeypatch.setenv("DEMO_LOGIN_GLOBAL_RATE_LIMIT", "1/3600")
        g = client.post("/api/v1/auth/demo-login")
        assert g.status_code == 429 and "all visitors" in g.text  # global cap
        monkeypatch.setenv("DEMO_LOGIN_GLOBAL_RATE_LIMIT", "100/3600")
        monkeypatch.setenv("KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET", "wrong-secret-" + "x" * 30)
        assert client.post("/api/v1/auth/demo-login").status_code == 503  # Keycloak refuses → no fallback/bypass
        monkeypatch.setenv("ALLOW_DEMO_LOGIN", "false")
        get_settings.cache_clear()
        assert client.post("/api/v1/auth/demo-login").status_code == 404
    finally:
        monkeypatch.undo()
        get_settings.cache_clear()


# ---------------- self-registration (DEMO deployment) ----------------
REG_PW = "Reg-Visitor-Pass-2026!"


def _text(html: str) -> str:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))


def _dup_rejected(page) -> bool:
    t = _text(page.text).lower()
    return page.status_code == 200 and any(x in t for x in ("already exists", "already associated", "already taken", "already in use"))


def browser_register(client, b: httpx.Client, username: str, email: str, password: str = REG_PW) -> httpx.Response:
    """Scripted browser: app /oidc/register → Keycloak registration form → app callback. Returns callback or Keycloak page."""
    r = b.get(client.get("/api/v1/auth/oidc/register", follow_redirects=False).headers["location"])
    action, data = _form(r.text)
    r = b.post(action, data={**data, "username": username, "email": email, "firstName": "Reg", "lastName": "Visitor",
                             "password": password, "password-confirm": password})
    for _ in range(4):
        if r.status_code not in (302, 303):
            return r
        loc = r.headers["location"]
        if loc.startswith("http://testserver/"):
            return client.get(loc.replace("http://testserver", ""), follow_redirects=False)
        r = b.get(loc)
    raise AssertionError("registration did not finish")


def _exchange(client, cb) -> dict:
    loc = cb.headers.get("location", "")
    assert "oidc_code=" in loc, (cb.status_code, loc)
    r = client.post("/api/v1/auth/oidc/exchange", json={"code": parse_qs(urlparse(loc).query)["oidc_code"][0]})
    assert r.status_code == 200, r.text
    return r.json()


def _kc_user(username: str) -> dict | None:
    rows = kc().users_by(REALM, username=username)
    return rows[0] if rows else None


@pytest.fixture()
def reg_env(monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("AUTH_PROVIDERS", "oidc")
    monkeypatch.setenv("SIGNUP_RATE_LIMIT", "100/3600")
    get_settings.cache_clear()
    assert run_cfg("apply", "--yes")[0] == 0 and "no changes" in run_cfg("plan")[1]
    yield monkeypatch
    monkeypatch.undo()
    get_settings.cache_clear()


def test_16_self_registration_creates_clean_tenant_with_persona_switch(client, reg_env):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import AuditEvent
    info = client.get("/api/v1/auth/provider").json()
    assert info["registration_enabled"] is True and info["oidc_enabled"] is True
    assert kc().realm(REALM)["registrationAllowed"] is True
    tok = _exchange(client, browser_register(client, browser(), "reg-alice", "alice.reg@example.org"))
    u = tok["user"]
    assert u["is_sandbox"] and u["persona_role"] == "isso" and u["auth_provider"] == "oidc"
    h = auth(tok["access_token"])
    assert client.get("/api/v1/systems", headers=h).json() == []  # clean workspace: zero systems
    st = client.get("/api/v1/sandbox/status", headers=h).json()
    assert st["workspace"] == "clean" and st["status"] == "ready" and st["reset_label"] == "Clear my workspace" and st["onboarding"]
    issm = client.post("/api/v1/sandbox/act-as", json={"role": "issm"}, headers=h)
    assert issm.status_code == 200 and issm.json()["user"]["persona_role"] == "issm"
    ku = _kc_user("reg-alice")
    assert (ku.get("attributes") or {}).get("self_registered") == ["true"]
    with SessionLocal() as db:
        ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "identity.mapped.jit").order_by(AuditEvent.seq.desc()))
        assert ev.details["reason"] == "self-registration" and ev.details["keycloak_user_id"] == ku["id"]
    sid = client.post("/api/v1/systems", json={"name": "Alice Private System", "acronym": "APS", "baseline_key": "low"}, headers=auth(issm.json()["access_token"]))
    assert sid.status_code == 201, sid.text
    STATE["alice"] = {"token": tok["access_token"], "system": sid.json()["id"], "kc": ku["id"]}
    out = client.post("/api/v1/auth/logout", headers=auth(issm.json()["access_token"]))
    assert out.status_code == 200 and "id_token_hint=" in (out.json()["end_session_url"] or "")  # persona session still ends the SSO session


def test_17_registration_refusals_existing_and_reserved(client, reg_env):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import AuthIdentity, Organization, User
    page = browser_register(client, browser(), "reg-dup-ao", "ao@aegisrmf.demo")  # migrated account: Keycloak rejects on the page
    assert _dup_rejected(page), _text(page.text)[-400:]
    page = browser_register(client, browser(), os.environ["KEYCLOAK_DEMO_USERNAME"], "handle.squat@example.org")
    assert _dup_rejected(page) and "username" in _text(page.text).lower(), _text(page.text)[-400:]
    page = browser_register(client, browser(), "reg-demo-squat", "demo@ironvision.ai")  # disabled reserved placeholder
    assert _dup_rejected(page), _text(page.text)[-400:]
    with SessionLocal() as db:  # app account that is NOT in Keycloak yet (not migrated): refused after registration, never linked
        org = db.scalar(select(Organization).where(Organization.is_sandbox.is_(False)).limit(1))
        if not db.scalar(select(User).where(User.email == "legacy.only@example.org")):
            db.add(User(org_id=org.id, email="legacy.only@example.org", display_name="Legacy only", source="test"))
            db.commit()
    for username, email, code in (("reg-legacy", "legacy.only@example.org", "registration_email_exists"),
                                  ("reg-seed-squat", "newperson@aegisrmf.demo", "registration_reserved")):
        cb = browser_register(client, browser(), username, email)
        assert f"oidc_error={code}" in cb.headers.get("location", ""), cb.headers.get("location")
        assert _kc_user(username) is None  # refused registrant removed from Keycloak at once
    with SessionLocal() as db:
        legacy = db.scalar(select(User).where(User.email == "legacy.only@example.org"))
        assert db.scalar(select(AuthIdentity).where(AuthIdentity.user_id == legacy.id)) is None


def test_18_rate_limit_and_two_registrants_isolated(client, reg_env):
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models import AuditEvent
    bob = _exchange(client, browser_register(client, browser(), "reg-bob", "bob.reg@example.org"))
    hb = auth(bob["access_token"])
    assert bob["user"]["org_id"] != client.get("/api/v1/auth/me", headers=auth(STATE["alice"]["token"])).json()["org_id"]
    assert client.get("/api/v1/systems", headers=hb).json() == []
    assert client.get(f"/api/v1/systems/{STATE['alice']['system']}", headers=hb).status_code in (403, 404)
    STATE["bob"] = {"org": bob["user"]["org_id"], "kc": _kc_user("reg-bob")["id"]}
    with SessionLocal() as db:
        n = db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "auth.signup", AuditEvent.outcome == "success"))
    reg_env.setenv("SIGNUP_RATE_LIMIT", f"{n}/3600")
    cb = browser_register(client, browser(), "reg-carol", "carol.reg@example.org")
    assert "oidc_error=registration_rate_limited" in cb.headers.get("location", "") and _kc_user("reg-carol") is None


def test_19_purge_after_inactivity_deletes_tenant_and_keycloak_user(client, reg_env):
    import uuid as _uuid

    from app.db import SessionLocal
    from app.models import Organization
    from app.services import sandbox as sbx
    with SessionLocal() as db:
        org = db.get(Organization, _uuid.UUID(STATE["bob"]["org"]))
        org.last_activity_at = datetime.now(timezone.utc) - timedelta(days=sbx.inactivity_days() + 2)
        db.commit()
        assert sbx.run_expiry(db)["purged"] >= 1
        db.refresh(org)
        assert org.sandbox_status == "purged"
    assert kc().user(REALM, STATE["bob"]["kc"]) is None  # self-registered Keycloak user deleted on purge
    assert kc().user(REALM, STATE["alice"]["kc"]) is not None  # active registrant untouched


def test_20_demo_launcher_switch_to_issm_and_approve(client, reg_env):
    from app.config import get_settings
    reg_env.setenv("ALLOW_DEMO_LOGIN", "true")
    reg_env.setenv("DEMO_LOGIN_RATE_LIMIT", "1000/3600")
    reg_env.setenv("DEMO_LOGIN_GLOBAL_RATE_LIMIT", "1000/3600")
    get_settings.cache_clear()
    r = client.post("/api/v1/auth/demo-login")
    assert r.status_code == 200, r.text
    isso = auth(r.json()["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "Launcher Approve System", "acronym": "LAS", "baseline_key": "low"},
                      headers=auth(client.post("/api/v1/sandbox/act-as", json={"role": "issm"}, headers=isso).json()["access_token"])).json()["id"]
    p = client.post("/api/v1/poams", json={"system_id": sid, "weakness": "Launcher SoD weakness", "control_ids": ["ac-2"], "due_date": "2027-01-31"}, headers=isso)
    assert p.status_code == 201, p.text
    assert client.post(f"/api/v1/poams/{p.json()['id']}/request-extension", json={"justification": "Vendor patch delayed by a quarter",
                       "kind": "deadline_extension", "new_due_date": "2027-04-30"}, headers=isso).status_code == 201
    rid = next(x["id"] for x in client.get("/api/v1/reviews", headers=isso).json()["items"] if x.get("poam_id") == p.json()["id"])
    issm = auth(client.post("/api/v1/sandbox/act-as", json={"role": "issm"}, headers=isso).json()["access_token"])
    ok = client.post(f"/api/v1/reviews/{rid}/decisions", json={"action": "approve", "rationale": "Approved by ISSM persona"}, headers=issm)
    assert ok.status_code == 200, ok.text
