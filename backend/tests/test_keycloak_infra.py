"""Keycloak deployment plumbing without Docker: compose overlay, edge auth block, TLS for two domains, env tooling, check_env,
demo-login gating, explicit identity mapping, one-time OIDC codes and RP logout (mocked IdP where noted)."""
import importlib.util
import os
import subprocess
from pathlib import Path

import pytest
import yaml

from tests.conftest import auth
from tests.test_tls_domain import _ensure, _log, tls  # noqa: F401  (fixture reuse: fake docker/openssl/getent/curl)

ROOT = Path(__file__).resolve().parents[2]
APP, AUTHD = "demo.ironvisionai.com", "auth.demo.ironvisionai.com"


@pytest.fixture(autouse=True)
def _fresh_settings():
    """Teardown runs after monkeypatch's undo, so no test leaves cached settings built from patched env behind."""
    yield
    from app.config import get_settings
    from app.security.providers.base import get_auth_provider
    get_settings.cache_clear()
    get_auth_provider.cache_clear()


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_compose_overlay_keycloak_service():
    c = yaml.safe_load((ROOT / "deploy/compose/keycloak.yml").read_text().replace("!reset", "").replace("!override", ""))
    kc = c["services"]["keycloak"]
    assert "26.8.1" in (ROOT / "deploy/keycloak/Dockerfile").read_text() and "kc.sh build" in (ROOT / "deploy/keycloak/Dockerfile").read_text()
    assert kc["command"] == ["start", "--optimized"]
    env = kc["environment"]
    assert env["KC_PROXY_HEADERS"] == "xforwarded" and env["KC_HTTP_ENABLED"] == "true" and env["KC_DB"] == "postgres"
    assert env["KC_HOSTNAME"].startswith("https://${AUTH_DOMAIN") and "/keycloak}" in env["KC_DB_URL"].replace("${KEYCLOAK_DB_NAME:-keycloak}", "/keycloak}")
    assert kc["ports"] == ["127.0.0.1:8081:8080"], "Keycloak must only bind loopback (admin via SSH tunnel)"
    assert kc["restart"] == "unless-stopped" and "health/ready" in " ".join(kc["healthcheck"]["test"])
    assert kc["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert kc["depends_on"]["keycloak-db-init"]["condition"] == "service_completed_successfully"
    assert c["services"]["keycloak-config"]["profiles"] == ["keycloak-tools"]  # never auto-started
    assert c["services"]["keycloak-db-init"]["command"] == ["python", "-m", "app.tools.keycloak_db_init"]


def test_edge_auth_block_exposes_only_the_realm():
    t = (ROOT / "deploy/digitalocean/nginx/edge-auth.conf.template").read_text()
    for loc in ("/admin/", "/realms/master/"):
        block = t.split(f"location {loc} {{", 1)[1].split("}", 1)[0]
        assert "include /etc/nginx/ironvision/auth-admin-allow.conf;" in block
    assert "location /realms/${KEYCLOAK_REALM}/ { proxy_pass $keycloak; }" in t
    assert "location / { return 404; }" in t and ":9000" not in t
    assert "proxy_set_header X-Forwarded-For $remote_addr;" in t  # overwrite, never append


@pytest.mark.skipif(not os.environ.get("KEYCLOAK_LIVE_URL") or not subprocess.run(["which", "nginx"], capture_output=True).returncode == 0,
                    reason="needs nginx + the live Keycloak")
def test_edge_blocks_admin_console_from_public(tmp_path):
    """Render the real auth template, point it at the live Keycloak and send real HTTPS requests."""
    import httpx
    subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1", "-subj", f"/CN={AUTHD}",
                    "-keyout", str(tmp_path / "k.pem"), "-out", str(tmp_path / "c.pem")], check=True, capture_output=True)
    (tmp_path / "allow.conf").write_text("deny all;\n")
    t = (ROOT / "deploy/digitalocean/nginx/edge-auth.conf.template").read_text()
    t = (t.replace("${AUTH_DOMAIN}", AUTHD).replace("${APP_DOMAIN}", APP).replace("${KEYCLOAK_REALM}", "ironvision-demo")
         .replace(f"/etc/letsencrypt/live/{AUTHD}/fullchain.pem", str(tmp_path / "c.pem"))
         .replace(f"/etc/letsencrypt/live/{AUTHD}/privkey.pem", str(tmp_path / "k.pem"))
         .replace("/etc/nginx/ironvision/auth-admin-allow.conf", str(tmp_path / "allow.conf"))
         .replace("listen 80;", "listen 18080;").replace("listen [::]:80;", "").replace("listen 443 ssl;", "listen 18443 ssl;")
         .replace("listen [::]:443 ssl;", "").replace("http2 on;", "").replace("resolver 127.0.0.11 valid=30s ipv6=off;", "")
         .replace("http://keycloak:8080", os.environ["KEYCLOAK_LIVE_URL"].replace("localhost", "127.0.0.1")))
    conf = tmp_path / "nginx.conf"
    conf.write_text(f"pid {tmp_path}/nginx.pid; error_log {tmp_path}/err.log; events {{}} http {{ access_log off; {t} }}")
    assert subprocess.run(["nginx", "-t", "-c", str(conf)], capture_output=True).returncode == 0
    subprocess.run(["nginx", "-c", str(conf)], check=True)
    try:
        c = httpx.Client(verify=False, base_url="https://127.0.0.1:18443", headers={"Host": AUTHD})
        assert c.get("/admin/master/console/").status_code == 403
        assert c.get("/realms/master/protocol/openid-connect/auth").status_code == 403
        assert c.get("/metrics").status_code == 404 and c.get("/health/ready").status_code == 404
        assert c.get("/").status_code == 302
        assert c.get("/realms/ironvision-demo/.well-known/openid-configuration").status_code == 200
    finally:
        subprocess.run(["nginx", "-c", str(conf), "-s", "stop"])


def test_tls_handles_app_and_auth_domains(tls):  # noqa: F811
    tmp, f, data, env = tls
    f.write_text(f.read_text() + f"AUTH_DOMAIN={AUTHD}\nKEYCLOAK_REALM=ironvision-demo\n")
    from tests.test_tls_domain import FAKES
    live = data / "letsencrypt" / "live"
    (tmp / "bin" / "docker").write_text(  # fake certbot writes the certificate for the requested -d domain
        '#!/bin/bash\necho "docker $*" >> "$FAKE_LOG"\ncase "$*" in *certonly*) d=$(sed -n "s/.* -d \\([^ ]*\\).*/\\1/p" <<<"$*"); '
        f'mkdir -p {live}/$d; echo CERT > {live}/$d/fullchain.pem; touch {tmp}/issued ;; esac\nexit 0\n')
    (tmp / "bin" / "openssl").write_text("#!/bin/bash\n" + FAKES["openssl"].replace('[ "${FAKE_CERT_OK:-0}" = 1 ]', f'[ -f {tmp}/issued ]')
                                         .replace('if [ "${FAKE_CERT_OK:-0}" = 1 ]', f'if [ -f {tmp}/issued ]'))
    r = _ensure(env, f)
    log = _log(tmp)
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"-d {APP}" in log and f"-d {AUTHD}" in log, log  # separate certificate per domain
    assert r.stdout.count("DNS:") == 2  # DNS preflight for both
    assert "nothing to do" in _ensure(env, f).stdout  # both valid now → certbot not called again
    import shutil
    shutil.rmtree(live / AUTHD)
    r = _ensure({**env, "FAKE_DNS_IP": ""}, f)
    assert r.returncode != 0 and "does not resolve" in r.stderr


def test_tls_refuses_same_app_and_auth_domain(tls):  # noqa: F811
    tmp, f, data, env = tls
    f.write_text(f.read_text() + f"AUTH_DOMAIN={APP}\n")
    r = _ensure(env, f)
    assert r.returncode != 0 and "must differ" in r.stderr


def _prod_env(tmp_path: Path) -> Path:
    f = tmp_path / ".env.production"
    f.write_text((ROOT / "deploy/digitalocean/env.production.template").read_text().replace("POSTGRES_PASSWORD=", "POSTGRES_PASSWORD=keep-me-1234567890"))
    sd = _load("set_domain")
    assert sd.main([str(f), APP, "--email", "k.hill@theironvision.com"]) == 0
    return f


def test_set_auth_domain_and_generated_secrets(tmp_path):
    f = _prod_env(tmp_path)
    sd, gen = _load("set_domain"), _load("gen_env_secrets")
    from app.envfile import parse_env_text
    before = parse_env_text(f.read_text())
    assert sd.main([str(f), "--auth-domain", AUTHD]) == 0
    e = parse_env_text(f.read_text())
    assert e["AUTH_DOMAIN"] == AUTHD and e["OIDC_ISSUER"] == f"https://{AUTHD}/realms/ironvision-demo"
    assert e["OIDC_CLIENT_ID"] == "ironvision-app" and e["OIDC_REDIRECT_URI"] == f"https://{APP}/api/v1/auth/oidc/callback"
    assert e["OIDC_POST_LOGOUT_REDIRECT_URI"] == f"https://{APP}/login"
    assert e["AUTH_PROVIDERS"] == before["AUTH_PROVIDERS"], "sign-in mode must not be switched implicitly"
    assert list(tmp_path.glob(".env.production.bak-*")) and oct(f.stat().st_mode & 0o777) == "0o600"
    gen.fill(f)
    e2 = parse_env_text(f.read_text())
    for k in ("KEYCLOAK_DB_PASSWORD", "KC_BOOTSTRAP_ADMIN_PASSWORD", "KEYCLOAK_ADMIN_PASSWORD", "KEYCLOAK_CONFIGURATOR_CLIENT_SECRET", "OIDC_CLIENT_SECRET",
              "KEYCLOAK_DEMO_PASSWORD", "KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET"):
        assert len(e2[k]) >= 32, k
    assert e2["KEYCLOAK_DEMO_USERNAME"].startswith("demo-launcher-") and "@" not in e2["KEYCLOAK_DEMO_USERNAME"]  # unpublished handle
    assert e2["POSTGRES_PASSWORD"] == "keep-me-1234567890"
    gen.fill(f)
    assert parse_env_text(f.read_text())["OIDC_CLIENT_SECRET"] == e2["OIDC_CLIENT_SECRET"]  # never overwritten
    g = tmp_path / "noapp.env"
    g.write_text("APP_DOMAIN=app.example.gov\n")
    assert sd.main([str(g), "--auth-domain", AUTHD]) == 2


def test_gen_secrets_skips_keycloak_without_auth_domain(tmp_path):
    f = _prod_env(tmp_path)
    _load("gen_env_secrets").fill(f)
    from app.envfile import parse_env_text
    assert parse_env_text(f.read_text()).get("KEYCLOAK_DB_PASSWORD", "") == ""


def _good_kc_env() -> dict:
    s = "q7Lm2Vw9Rz4Kp8Td3Nb6Hc1Jf5Yg0Ua"
    return {"APP_ENV": "production", "APP_DOMAIN": APP, "AUTH_DOMAIN": AUTHD, "KEYCLOAK_REALM": "ironvision-demo",
            "OIDC_ISSUER": f"https://{AUTHD}/realms/ironvision-demo", "OIDC_REDIRECT_URI": f"https://{APP}/api/v1/auth/oidc/callback",
            "OIDC_POST_LOGOUT_REDIRECT_URI": f"https://{APP}/login", "OIDC_CLIENT_ID": "ironvision-app", "AUTH_PROVIDERS": "oidc",
            "KEYCLOAK_DB_PASSWORD": "Kc" + s, "KC_BOOTSTRAP_ADMIN_PASSWORD": "Bt" + s, "KEYCLOAK_ADMIN_PASSWORD": "Ad" + s,
            "KEYCLOAK_CONFIGURATOR_CLIENT_SECRET": "Cf" + s, "OIDC_CLIENT_SECRET": "Oc" + s, "KEYCLOAK_ADMIN_USERNAME": "ironvision-admin"}


def test_check_env_keycloak_rules():
    from app.check_env import validate
    errs = [e for e in validate(_good_kc_env())[0] if "KEYCLOAK" in e or "OIDC" in e or "AUTH_DOMAIN" in e]
    assert errs == [], errs
    bad = {**_good_kc_env(), "OIDC_ISSUER": f"http://{AUTHD}/realms/other", "KEYCLOAK_ADMIN_ALLOWED_CIDRS": "0.0.0.0/0,nope",
           "OIDC_CLIENT_SECRET": "", "KEYCLOAK_ADMIN_USERNAME": "bootstrap-admin"}
    e = " | ".join(validate(bad)[0])
    for frag in ("OIDC_ISSUER must be https://", "OIDC_ISSUER must be https:// in staging", "0.0.0.0/0", "'nope' is not a valid CIDR",
                 "OIDC_CLIENT_SECRET is required", "must differ from KC_BOOTSTRAP_ADMIN_USERNAME"):
        assert frag in e, frag
    prod_realm = {**_good_kc_env(), "KEYCLOAK_REALM": "ironvision-prod", "OIDC_ISSUER": f"https://{AUTHD}/realms/ironvision-prod"}
    assert any("KEYCLOAK_REQUIRE_MFA=true is required" in x for x in validate(prod_realm)[0])


def test_demo_login_is_404_without_dev_password(client, monkeypatch):
    monkeypatch.setenv("ALLOW_DEMO_LOGIN", "true")
    from app.config import get_settings
    get_settings.cache_clear()
    try:
        monkeypatch.setenv("AUTH_PROVIDERS", "oidc")
        monkeypatch.delenv("KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET", raising=False)  # launcher absent → oidc-only means no demo
        assert client.post("/api/v1/auth/demo-login").status_code == 404
        assert client.get("/api/v1/auth/provider").json()["demo_login_enabled"] is False
    finally:
        get_settings.cache_clear()


def test_identity_mapping_conflicts():
    from app.db import SessionLocal
    from app.models import Organization, User
    from app.services import identity_map
    iss = "https://auth.test/realms/unit"
    with SessionLocal() as db:
        org = db.query(Organization).first()
        a = User(org_id=org.id, email="map-a@example.org", display_name="A", source="pytest")
        b = User(org_id=org.id, email="map-b@example.org", display_name="B", source="pytest")
        db.add_all([a, b])
        db.flush()
        _, created = identity_map.map_identity(db, user=a, issuer=iss, sub="sub-a", reason="unit", actor="pytest")
        assert created
        assert identity_map.map_identity(db, user=a, issuer=iss, sub="sub-a", reason="unit", actor="pytest")[1] is False  # idempotent
        with pytest.raises(identity_map.MappingConflict):
            identity_map.map_identity(db, user=b, issuer=iss, sub="sub-a", reason="unit", actor="pytest")  # one sub → one user
        with pytest.raises(identity_map.MappingConflict):
            identity_map.map_identity(db, user=a, issuer=iss, sub="sub-a2", reason="unit", actor="pytest")  # one identity per issuer
        with pytest.raises(identity_map.MappingConflict):
            identity_map.map_identity(db, user=b, issuer=iss, sub="sub-b", reason=" ", actor="pytest")  # reason required
        ident = identity_map.by_subject(db, iss, "sub-a")
        assert ident.attributes["mapped_by"] == "pytest" and ident.attributes["reason"] == "unit"
        db.rollback()


def test_email_linking_only_in_development(monkeypatch):
    from app.api.v1 import auth as a
    from app.config import get_settings
    monkeypatch.setenv("OIDC_ALLOW_EMAIL_LINKING", "true")
    for envname, expect in (("production", False), ("staging", False), ("development", True)):
        monkeypatch.setenv("APP_ENV", envname)
        get_settings.cache_clear()
        assert a._email_linking_allowed() is expect, envname
    get_settings.cache_clear()


def test_login_code_expired_or_unknown_is_401(client, monkeypatch):
    import hashlib
    from datetime import datetime, timedelta, timezone

    from app.db import SessionLocal
    from app.models import OidcLoginCode, User
    monkeypatch.setenv("AUTH_PROVIDERS", "dev_password,oidc")
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == "isso@aegisrmf.demo").one()
        db.add(OidcLoginCode(code_sha256=hashlib.sha256(b"old-code").hexdigest(), user_id=u.id,
                             expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.commit()
    assert client.post("/api/v1/auth/oidc/exchange", json={"code": "old-code"}).status_code == 401
    assert client.post("/api/v1/auth/oidc/exchange", json={"code": "never-issued"}).status_code == 401


def test_logout_returns_rp_logout_url_for_oidc_sessions(client, monkeypatch):
    """Mocked discovery (no IdP needed): an OIDC session's logout yields the end_session URL with id_token_hint."""
    import hashlib
    import secrets
    from datetime import datetime, timedelta, timezone

    from app.db import SessionLocal
    from app.models import OidcLoginCode, User
    from app.security import oidc
    iss = "https://auth.unit.test/realms/r"
    for k, v in {"AUTH_PROVIDERS": "dev_password,oidc", "OIDC_ISSUER": iss, "OIDC_CLIENT_ID": "ironvision-app",
                 "OIDC_REDIRECT_URI": "https://app.unit.test/api/v1/auth/oidc/callback",
                 "OIDC_POST_LOGOUT_REDIRECT_URI": "https://app.unit.test/login"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setattr(oidc, "discovery", lambda i: {"issuer": iss, "end_session_endpoint": f"{iss}/protocol/openid-connect/logout"})
    raw = secrets.token_urlsafe(16)
    with SessionLocal() as db:
        u = db.query(User).filter(User.email == "isso@aegisrmf.demo").one()
        db.add(OidcLoginCode(code_sha256=hashlib.sha256(raw.encode()).hexdigest(), user_id=u.id, id_token="hdr.payload.sig",
                             expires_at=datetime.now(timezone.utc) + timedelta(seconds=60)))
        db.commit()
    tok = client.post("/api/v1/auth/oidc/exchange", json={"code": raw}).json()["access_token"]
    url = client.post("/api/v1/auth/logout", headers=auth(tok)).json()["end_session_url"]
    assert url.startswith(f"{iss}/protocol/openid-connect/logout?") and "id_token_hint=hdr.payload.sig" in url
    assert "post_logout_redirect_uri=https%3A%2F%2Fapp.unit.test%2Flogin" in url and "client_id=ironvision-app" in url


def test_check_env_demo_launcher_rules():
    from app.check_env import validate
    base = {**_good_kc_env(), "ALLOW_DEMO_LOGIN": "true", "DEPLOYMENT_KIND": "demo", "KEYCLOAK_DEMO_USERNAME": "demo-launcher-a1b2c3d4e5f6",
            "KEYCLOAK_DEMO_PASSWORD": "Dp7Lm2Vw9Rz4Kp8Td3Nb6Hc1", "KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET": "Ls7Lm2Vw9Rz4Kp8Td3Nb6Hc1Jf5Yg0Ua9"}
    assert not [e for e in validate(base)[0] if "DEMO" in e], validate(base)[0]
    errs = " | ".join(validate({**base, "KEYCLOAK_DEMO_USERNAME": "demo@ironvision.ai"})[0])
    assert "unpublished handle" in errs
    errs = " | ".join(validate({**base, "DEPLOYMENT_KIND": "customer"})[0])
    assert "never on a customer deployment" in errs
    assert "DEPLOYMENT_KIND must be demo or customer" in " | ".join(validate({**base, "DEPLOYMENT_KIND": "qa"})[0])


def test_customer_template_never_allows_demo():
    from app.envfile import parse_env_text
    e = parse_env_text((ROOT / "deploy/digitalocean/env.customer-production.template").read_text())
    assert e["DEPLOYMENT_KIND"] == "customer" and e["ALLOW_DEMO_LOGIN"] == "false" and e["KEYCLOAK_REQUIRE_MFA"] == "true"
    assert parse_env_text((ROOT / "deploy/digitalocean/env.production.template").read_text())["DEPLOYMENT_KIND"] == "demo"


def test_demo_login_404_when_launcher_not_configured(client, monkeypatch):
    from app.config import get_settings
    monkeypatch.setenv("ALLOW_DEMO_LOGIN", "true")
    monkeypatch.setenv("AUTH_PROVIDERS", "oidc")
    monkeypatch.delenv("KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET", raising=False)
    get_settings.cache_clear()
    assert client.post("/api/v1/auth/demo-login").status_code == 404


def test_every_ingest_source_type_has_a_catalog_entry():
    """Regression: a SARIF upload created a 'sarif' EvidenceSource that /systems/{id}/sources could not render (500)."""
    from app.services.connectors import SOURCE_TYPES
    from app.services.ingest.parsers import SOURCE_TYPE
    from app.services.ingest.pipeline import EVIDENCE_TYPE, SRC_NAMES
    created = set(SRC_NAMES) | set(SOURCE_TYPE.values())
    assert created <= set(SOURCE_TYPES), created - set(SOURCE_TYPES)
    assert set(EVIDENCE_TYPE) <= set(SOURCE_TYPE) | {"nessus_xml", "nessus_csv"}
