import io
import os
import uuid
import zipfile

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import AuditEvent, Organization, RoleAssignment, System, User
from tests.conftest import PASSWORD, auth


def _ltp(db):
    return db.scalar(select(System).where(System.acronym == "LTP"))


def test_security_headers_and_health(client):
    r = client.get("/api/v1/health/live")
    for h in ("x-content-type-options", "x-frame-options", "referrer-policy", "permissions-policy", "content-security-policy"):
        assert h in r.headers, h
    assert r.headers["x-frame-options"] == "DENY" and "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert "strict-transport-security" not in r.headers
    assert "strict-transport-security" in client.get("/api/v1/health/live", headers={"x-forwarded-proto": "https"}).headers
    assert client.get("/api/v1/ready").json()["ready"] is True
    m = client.get("/api/v1/metrics").text
    assert "aegis_http_request_duration_seconds" in m and "aegis_jobs_total" in m and "aegis_emass_queue" in m


def test_rate_limit_auth(client, monkeypatch):
    from app.security import web
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setitem(web.RULES, "auth", (3, 60))
    web.reset_rate_limits()
    codes = [client.post("/api/v1/auth/login", json={"email": "ratelimit@x.demo", "password": "nope"}).status_code for _ in range(5)]
    web.reset_rate_limits()
    assert codes[:3] == [401, 401, 401] and codes[3:] == [429, 429]


def test_lockout_after_failures(client):
    email = "isso@aegisrmf.demo"
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": email.upper(), "password": "wrong-password"})
    r = client.post("/api/v1/auth/login", json={"email": email.upper(), "password": PASSWORD})
    assert r.status_code in (423, 429, 401) and r.status_code != 200
    with SessionLocal() as db:
        from app.models import LoginAttempt
        db.query(LoginAttempt).delete()
        db.commit()


def test_session_refresh_rotation_and_logout_revocation(client):
    r = client.post("/api/v1/auth/login", json={"email": "sca@aegisrmf.demo", "password": PASSWORD}).json()
    at, rt = r["access_token"], r["refresh_token"]
    assert r["idle_timeout_minutes"] and client.get("/api/v1/auth/me", headers=auth(at)).status_code == 200
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": rt})
    assert r2.status_code == 200 and r2.json()["refresh_token"] != rt
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": rt}).status_code == 401  # rotated – old one dead
    at2 = r2.json()["access_token"]
    assert client.post("/api/v1/auth/logout", headers=auth(at2)).status_code in (200, 204)
    assert client.get("/api/v1/auth/me", headers=auth(at2)).status_code == 401  # server-side revocation
    assert client.get("/api/v1/auth/me", headers=auth(at)).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refresh_token": r2.json()["refresh_token"]}).status_code == 401


def test_idle_timeout_enforced(client):
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import update

    from app.models import AuthSession
    r = client.post("/api/v1/auth/login", json={"email": "ao@aegisrmf.demo", "password": PASSWORD}).json()
    with SessionLocal() as db:
        import jwt
        sid = jwt.decode(r["access_token"], options={"verify_signature": False})["sid"]
        db.execute(update(AuthSession).where(AuthSession.id == uuid.UUID(sid)).values(idle_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.commit()
    assert client.get("/api/v1/auth/me", headers=auth(r["access_token"])).status_code == 401


def test_dev_password_can_be_disabled(client, monkeypatch):
    monkeypatch.setenv("AUTH_PROVIDERS", "oidc")
    from app.security.providers.base import get_auth_provider
    get_auth_provider.cache_clear()
    try:
        info = client.get("/api/v1/auth/provider").json()
        assert info["dev_password_enabled"] is False and info["dev_accounts"] == [] and info["oidc_enabled"] is True
        assert client.post("/api/v1/auth/login", json={"email": "isso@aegisrmf.demo", "password": PASSWORD}).status_code == 404
        assert client.post("/api/v1/auth/mtls/login").status_code == 404
    finally:
        monkeypatch.setenv("AUTH_PROVIDERS", "dev_password")
        get_auth_provider.cache_clear()


def test_mtls_header_only_from_trusted_proxy(monkeypatch):
    from app.security.oidc import mtls_principal
    monkeypatch.setenv("MTLS_TRUSTED_PROXIES", "10.0.0.5")
    h = {"x-ssl-client-verify": "SUCCESS", "x-ssl-client-s-dn": "CN=DOE.JANE.1234567890", "x-client-edipi": "1234567890"}
    assert mtls_principal(h, "10.0.0.5")["subject"] == "edipi:1234567890"
    for host, hdr in (("203.0.113.9", h), ("10.0.0.5", {**h, "x-ssl-client-verify": "FAILED"})):
        try:
            mtls_principal(hdr, host)
            raise AssertionError("should reject")
        except ValueError:
            pass


def test_upload_security(client, token):
    from app.services.ingest.parsers import ParseError, parse_ckl
    from app.services.upload_security import UploadRejected, validate_upload
    isso = auth(token("isso@aegisrmf.demo"))
    with SessionLocal() as db:
        sid = str(_ltp(db).id)
    # extension + magic bytes
    for name, data in (("evil.exe", b"MZ\x90"), ("fake.pdf", b"not a pdf"), ("scan.nessus", b"\x00\x01binary")):
        try:
            validate_upload(name, data, "scan" if name.endswith(".nessus") else "policy")
            raise AssertionError(name)
        except UploadRejected:
            pass
    # zip bomb
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("a.json", b"0" * (50 * 1024 * 1024))
    try:
        validate_upload("bomb.cklb", buf.getvalue(), "scan")
        raise AssertionError("zip bomb accepted")
    except UploadRejected as exc:
        assert "zip bomb" in str(exc)
    # XXE
    xxe = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><CHECKLIST>&e;</CHECKLIST>'
    try:
        parse_ckl(xxe)
        raise AssertionError("XXE parsed")
    except ParseError as exc:
        assert "Unsafe XML" in str(exc) or "DTD" in str(exc)
    r = client.post("/api/v1/policies", files={"file": ("p.pdf", b"plain text pretending", "application/pdf")}, data={"title": "X", "system_ids": sid}, headers=isso)
    assert r.status_code == 415


def test_tenant_isolation(client, token):
    """A user in tenant B cannot read tenant A records (systems, POA&Ms, findings, search, audit)."""
    with SessionLocal() as db:
        a = _ltp(db)
        org_b = db.scalar(select(Organization).where(Organization.slug == "tenant-b-test"))
        if org_b is None:
            org_b = Organization(name="Tenant B (SYNTHETIC test)", slug="tenant-b-test")
            db.add(org_b)
            db.flush()
            sb = System(org_id=org_b.id, name="Tenant B System", acronym="TBS")
            ub = User(org_id=org_b.id, email="isso.b@tenantb.demo", display_name="ISSO Tenant B", is_active=True)
            db.add_all([sb, ub])
            db.flush()
            db.add(RoleAssignment(user_id=ub.id, role="isso", scope_type="org", scope_id=org_b.id))
            from app.security.passwords import hash_password
            from app.models import AuthIdentity
            db.add(AuthIdentity(user_id=ub.id, provider="dev_password", subject=ub.email, secret_hash=hash_password(PASSWORD)))
            db.commit()
        a_id = str(a.id)
        from app.models import Finding, Poam
        f_a = str(db.scalar(select(Finding.id).where(Finding.system_id == a.id).limit(1)))
        p_a = str(db.scalar(select(Poam.id).where(Poam.system_id == a.id).limit(1)))
    b = auth(token("isso.b@tenantb.demo"))
    systems = client.get("/api/v1/systems", headers=b).json()
    names = [s["acronym"] for s in (systems.get("items", systems) if isinstance(systems, dict) else systems)]
    assert names == ["TBS"]
    assert client.get(f"/api/v1/systems/{a_id}", headers=b).status_code in (403, 404)
    assert client.get(f"/api/v1/findings/{f_a}", headers=b).status_code in (403, 404)
    assert client.get(f"/api/v1/poams/{p_a}", headers=b).status_code in (403, 404)
    assert client.get("/api/v1/poams", params={"system_id": a_id}, headers=b).status_code in (403, 404)
    assert client.get(f"/api/v1/systems/{a_id}/inheritance", headers=b).status_code in (403, 404)
    assert all(r.get("system_id") in (None,) or r.get("system_id") != a_id for r in client.get("/api/v1/search", params={"q": "LTP"}, headers=b).json())
    assert client.post(f"/api/v1/systems/{a_id}/oscal/poam", headers=b).status_code in (403, 404)


def test_retention_never_deletes_audit(client):
    from app.models import RetentionPolicy
    from app.services.retention import purge
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(AuditEvent))
        res = purge(db)
        db.commit()
        assert res["audit_events"] == {"skipped": "never purged"}
        for p in db.scalars(select(RetentionPolicy)):
            p.enabled = True
        db.commit()
        res = purge(db, force_dry_run=True)
        db.commit()
        assert all(v.get("dry_run") for k, v in res.items() if k != "audit_events")
        assert db.scalar(select(func.count()).select_from(AuditEvent)) >= before
        for p in db.scalars(select(RetentionPolicy)):
            p.enabled = False
        db.commit()


def test_secret_store_backends(monkeypatch):
    from cryptography.fernet import Fernet

    from app.services.secrets import EnvKeySecretStore, SecretStore
    monkeypatch.setenv("SECRET_STORE_BACKEND", "env_key")
    monkeypatch.setenv("SECRET_STORE_KEY", Fernet.generate_key().decode())
    s = SecretStore()
    assert isinstance(s, EnvKeySecretStore) and s.decrypt(s.encrypt("x")) == "x"
    monkeypatch.setenv("SECRET_STORE_BACKEND", "aws_sm")
    try:
        SecretStore()
        raise AssertionError
    except RuntimeError:
        pass
    _ = (os, uuid)


def test_oidc_code_pkce_flow_with_mocked_idp(client, monkeypatch):
    """OIDC Authorization Code + PKCE against a mocked IdP: signed ID token accepted, state replay and bad nonce rejected."""
    import time
    from urllib.parse import parse_qs, urlparse

    import jwt as pyjwt
    from cryptography.hazmat.primitives.asymmetric import rsa

    from app.security import oidc
    from app.security.providers.base import get_auth_provider
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    iss = "https://idp.example.test/realms/aegis"
    for k, v in {"AUTH_PROVIDERS": "dev_password,oidc", "OIDC_ISSUER": iss, "OIDC_CLIENT_ID": "aegisrmf",
                 "OIDC_REDIRECT_URI": "http://testserver/api/v1/auth/oidc/callback", "FRONTEND_URL": "http://spa.test"}.items():
        monkeypatch.setenv(k, v)
    get_auth_provider.cache_clear()
    monkeypatch.setattr(oidc, "discovery", lambda i: {"issuer": iss, "authorization_endpoint": f"{iss}/auth",
                                                      "token_endpoint": f"{iss}/token", "jwks_uri": f"{iss}/certs"})
    sent = {}

    class Resp:
        def __init__(self, d): self.d = d
        def raise_for_status(self): return self
        def json(self): return self.d

    def fake_post(url, data=None, auth=None, timeout=None):
        sent.update(data)
        return Resp({"id_token": sent["_id_token"]})

    class FakeJWK:
        def __init__(self, uri): pass
        def get_signing_key_from_jwt(self, t): return type("K", (), {"key": key.public_key()})()

    monkeypatch.setattr(oidc.httpx, "post", lambda url, **kw: fake_post(url, **kw))
    monkeypatch.setattr(oidc.jwt, "PyJWKClient", FakeJWK)

    def start(nonce_override=None):
        r = client.get("/api/v1/auth/oidc/login", follow_redirects=False)
        assert r.status_code in (302, 307)
        q = parse_qs(urlparse(r.headers["location"]).query)
        assert q["code_challenge_method"] == ["S256"] and q["code_challenge"][0] and q["client_id"] == ["aegisrmf"]
        state = q["state"][0]
        now = int(time.time())
        sent["_id_token"] = pyjwt.encode({"iss": iss, "aud": "aegisrmf", "sub": "kc-isso-1", "iat": now, "exp": now + 300,
                                          "nonce": nonce_override or oidc._pending[state]["nonce"], "email": "isso@aegisrmf.demo",
                                          "name": "Demo ISSO"}, key, algorithm="RS256")
        return state

    try:
        state = start()
        r = client.get(f"/api/v1/auth/oidc/callback?code=abc&state={state}", follow_redirects=False)
        assert r.status_code in (302, 307) and r.headers["location"].startswith("http://spa.test/login#access_token=")
        assert sent["code_verifier"] and len(sent["code_verifier"]) >= 43
        tok = parse_qs(urlparse(r.headers["location"]).fragment)["access_token"][0]
        me = client.get("/api/v1/auth/me", headers=auth(tok)).json()
        assert me["email"] == "isso@aegisrmf.demo"
        assert client.get(f"/api/v1/auth/oidc/callback?code=abc&state={state}", follow_redirects=False).status_code == 401  # replay
        state = start(nonce_override="attacker-nonce")
        assert client.get(f"/api/v1/auth/oidc/callback?code=abc&state={state}", follow_redirects=False).status_code == 401
    finally:
        get_auth_provider.cache_clear()


def test_vault_secret_store_with_mocked_client(monkeypatch):
    import hvac

    from app.services.secrets import SecretStore, VaultSecretStore
    store: dict = {}

    class KV:
        def create_or_update_secret(self, path, secret, mount_point): store[(mount_point, path)] = secret
        def read_secret_version(self, path, mount_point, raise_on_deleted_version): return {"data": {"data": store[(mount_point, path)]}}

    class FakeClient:
        def __init__(self, url, token=None, namespace=None):
            assert url == "https://vault.test:8200"
            self.secrets = type("S", (), {"kv": type("K", (), {"v2": KV()})()})()

    monkeypatch.setattr(hvac, "Client", FakeClient)
    monkeypatch.setenv("SECRET_STORE_BACKEND", "vault")
    monkeypatch.setenv("VAULT_ADDR", "https://vault.test:8200")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")
    s = SecretStore()
    ref = s.encrypt("emass-api-key-value")
    assert isinstance(s, VaultSecretStore) and ref.startswith("vault:aegisrmf/") and "emass-api-key-value" not in ref
    assert s.decrypt(ref) == "emass-api-key-value"
