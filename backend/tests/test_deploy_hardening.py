"""Deployment hardening helpers: check_env, production guard, staging demo password, create-admin CLI, docs center."""
import pytest

from app.check_env import DOCUMENTED_DEMO_PASSWORD, insecure_production, validate
from tests.conftest import auth

GOOD = {
    "APP_ENV": "production", "APP_DOMAIN": "app.example.gov", "POSTGRES_DB": "ironvision", "POSTGRES_USER": "ironvision",
    "POSTGRES_PASSWORD": "Zq8x1Lr0Pc4Vn7Kw2Ty5", "S3_ACCESS_KEY_ID": "ironvisionapp", "S3_SECRET_ACCESS_KEY": "Mb3Hs9Qd6Jf1Wr8Ux4Ze", "S3_ADMIN_ACCESS_KEY_ID": "ironvisionadmin", "S3_ADMIN_SECRET_ACCESS_KEY": "Ka7Rt2Wx9Lp4Nc6Vb1Qz", "COMPOSE_PROFILES": "seaweedfs", "STORAGE_DRIVER": "s3",
    "S3_BUCKET": "ironvision-evidence", "S3_REGION": "us-east-1", "JWT_SECRET": "k" * 8 + "Q7m2Rz9Xv4Lp1Ns6Bt3Wy8Hc5Jd0Gf",
    "SECRET_STORE_KEY": "ZmVybmV0LWtleS1mb3ItdGVzdHMtb25seS0wMTIzNDU=", "CORS_ORIGINS": "https://app.example.gov",
    "FRONTEND_URL": "https://app.example.gov", "AUTH_PROVIDERS": "oidc", "OIDC_ISSUER": "https://idp.example.gov/realms/x",
    "OIDC_CLIENT_ID": "ironvision", "OIDC_REDIRECT_URI": "https://app.example.gov/api/v1/auth/oidc/callback", "TRUST_PROXY_HEADERS": "true",
    "SEED_DEMO_DATA": "false", "AI_PROVIDER": "none",
}


def test_check_env_production_good_and_insecure():
    errs, _ = validate(GOOD)
    assert errs == []
    bad = GOOD | {"AUTH_PROVIDERS": "dev_password,oidc", "SEED_DEMO_DATA": "true", "JWT_SECRET": "change-me",
                  "DEMO_USER_PASSWORD": DOCUMENTED_DEMO_PASSWORD, "CORS_ORIGINS": "http://localhost:3000", "AI_PROVIDER": "emergent"}
    errs, _ = validate(bad)
    text = " | ".join(errs)
    for frag in ("dev_password in production", "SEED_DEMO_DATA=true", "JWT_SECRET is weak", "publicly documented", "CORS_ORIGINS", "emergent"):
        assert frag in text, frag
    assert insecure_production(bad | {"ALLOW_INSECURE_PRODUCTION": "true"}) == []
    assert validate({k: v for k, v in GOOD.items() if k != "JWT_SECRET"})[0] == ["JWT_SECRET is required"]


def test_production_guard_and_staging_seed_password(monkeypatch):
    from app import seed
    from app.check_env import production_guard
    from app.config import get_settings
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("AUTH_PROVIDERS", "dev_password")
    with pytest.raises(RuntimeError, match="Refusing to start"):
        production_guard()
    monkeypatch.setenv("APP_ENV", "staging")
    production_guard()
    get_settings.cache_clear()
    try:
        monkeypatch.setenv("DEMO_USER_PASSWORD", DOCUMENTED_DEMO_PASSWORD)
        monkeypatch.delenv("STAGING_DEMO_PASSWORD", raising=False)
        with pytest.raises(RuntimeError, match="publicly documented"):
            seed.demo_password()
        monkeypatch.setenv("STAGING_DEMO_PASSWORD", "Staging-only-9f3k2m7q")
        assert seed.demo_password() == "Staging-only-9f3k2m7q"
    finally:
        get_settings.cache_clear()


def test_create_admin_cli_bootstraps_non_demo_admin(client, monkeypatch):
    from app.cli import create_admin, main
    monkeypatch.setenv("AUTH_PROVIDERS", "oidc")
    with pytest.raises(ValueError, match="requires dev_password"):
        create_admin("ops@agency.example", "Ops Admin", "Agency Example", password="x" * 14)
    assert main(["create-admin", "--email", "ops@agency.example", "--name", "Ops Admin", "--org", "Agency Example"]) == 0
    monkeypatch.setenv("AUTH_PROVIDERS", "dev_password")
    user, created = create_admin("ops@agency.example", "Ops Admin", "Agency Example", password="Bootstrap-pass-123")
    assert not created
    tok = client.post("/api/v1/auth/login", json={"email": "ops@agency.example", "password": "Bootstrap-pass-123"}).json()["access_token"]
    me = client.get("/api/v1/auth/me", headers=auth(tok)).json()
    assert any(r["role"] == "platform_admin" and r["scope_type"] == "org" for r in me["roles"])


def test_docs_center_allowlist(client, token):
    h = auth(token("isso@aegisrmf.demo"))
    assert client.get("/api/v1/docs-center").status_code == 401
    items = client.get("/api/v1/docs-center", headers=h).json()["items"]
    assert [i["slug"] for i in items][:2] == ["readme", "digitalocean"]
    d = client.get("/api/v1/docs-center/security", headers=h).json()
    assert d["markdown"].startswith("# Security")
    for bad in ("..%2F..%2Fbackend%2F.env", "%2Fetc%2Fpasswd", "env", "README.md"):
        assert client.get(f"/api/v1/docs-center/{bad}", headers=h).status_code == 404
    r = client.get("/api/v1/docs-center/security/download", headers=h)
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    z = client.get("/api/v1/docs-center/archive.zip", headers=h)
    assert z.status_code == 200 and z.content[:2] == b"PK"


def test_env_templates_cover_every_variable_the_code_reads():
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    pat = re.compile(r"""(?:environ(?:\.get)?\(|environ\[|getenv\(|_opt\(|_req\(|_bool\()['"]([A-Z_0-9]+)['"]""")
    used = {m for f in (root / "backend/app").rglob("*.py") for m in pat.findall(f.read_text())}
    preview_only = {"EMERGENT_LLM_KEY", "EMERGENT_AI_VENDOR"}
    compose_only = {"DATABASE_URL", "DOCS_ROOT", "CONTENT_DIR", "SAMPLES_DIR", "CLAMAV_HOST", "CLAMAV_PORT", "AUTH_PROVIDER"}
    for tpl in ("deploy/digitalocean/.env.production.example", "deploy/digitalocean/.env.staging.example"):
        keys = {l.split("=", 1)[0].lstrip("# ").strip() for l in (root / tpl).read_text().splitlines() if "=" in l}
        missing = used - keys - preview_only - compose_only
        assert not missing, f"{tpl} missing {sorted(missing)}"
