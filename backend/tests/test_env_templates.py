"""Env templates ship in the repo (dot and non-dot copies), hold no secrets, cover every variable, and are not git-ignored.
Domain values: the DEMO template carries the demo.ironvisionai.com values; staging/customer-production keep placeholders."""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PAIRS = [
    (".env.example", "env.template"),
    ("backend/.env.example", "backend/env.template"),
    ("backend/worker/.env.example", "backend/worker/env.template"),
    ("frontend/.env.example", "frontend/env.template"),
    ("deploy/digitalocean/.env.production.example", "deploy/digitalocean/env.production.template"),
    ("deploy/digitalocean/.env.staging.example", "deploy/digitalocean/env.staging.template"),
    ("deploy/digitalocean/.env.customer-production.example", "deploy/digitalocean/env.customer-production.template"),
]
SECRET_KEY = re.compile(r"(SECRET|PASSWORD|PASSWD|TOKEN|API_KEY|PRIVATE|CREDENTIAL|SECRET_ACCESS_KEY|STORE_KEY)")
PLACEHOLDER = re.compile(r"(change-me|generate-with|example|^env_key$|^/)", re.I)
DOCUMENTED_DEV_DEMO = "AegisDemo!2026"   # public dev-only demo password; check_env refuses it outside development
REAL_SECRET_SHAPES = [re.compile(p) for p in (
    r"AKIA[0-9A-Z]{16}", r"sk-[A-Za-z0-9_-]{20,}", r"sk-ant-[A-Za-z0-9_-]{20,}", r"-----BEGIN [A-Z ]*PRIVATE KEY-----",
    r"ghp_[A-Za-z0-9]{30,}", r"xox[bp]-[A-Za-z0-9-]{20,}", r"dop_v1_[a-f0-9]{40,}")]


def _kv(path: Path) -> dict[str, str]:
    out = {}
    for line in path.read_text().splitlines():
        s = line.strip()
        if s and not s.startswith("#") and "=" in s:
            k, v = s.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    return out


@pytest.mark.parametrize("dot,plain", PAIRS)
def test_template_pairs_exist_and_are_identical(dot, plain):
    assert (ROOT / dot).is_file() and (ROOT / plain).is_file()
    assert (ROOT / dot).read_bytes() == (ROOT / plain).read_bytes(), f"{plain} must be an identical copy of {dot}"


@pytest.mark.parametrize("dot,plain", PAIRS)
def test_templates_hold_placeholders_only(dot, plain):
    text = (ROOT / plain).read_text()
    for pat in REAL_SECRET_SHAPES:
        assert not pat.search(text), f"{plain}: looks like a real credential ({pat.pattern})"
    for k, v in _kv(ROOT / plain).items():
        if not v or not SECRET_KEY.search(k) or k == "SECRET_STORE_BACKEND":
            continue
        if v == DOCUMENTED_DEV_DEMO:
            assert "digitalocean" not in plain, f"{plain}: {k} must be empty in deployment templates"
            continue
        assert PLACEHOLDER.search(v), f"{plain}: {k} has a non-placeholder value"


def test_deploy_templates_cover_every_variable_the_code_reads():
    pat = re.compile(r"""(?:environ(?:\.get)?\(|environ\[|getenv\(|_opt\(|_req\(|_bool\()['"]([A-Z_0-9]+)['"]""")
    used = {m for f in (ROOT / "backend/app").rglob("*.py") for m in pat.findall(f.read_text())}
    ignore = {"EMERGENT_LLM_KEY", "EMERGENT_AI_VENDOR", "DATABASE_URL", "DOCS_ROOT", "CONTENT_DIR", "SAMPLES_DIR",
              "CLAMAV_HOST", "CLAMAV_PORT", "AUTH_PROVIDER", "SUDO_USER",
              # written per run by recover.sh into <run>/sources.env, never operator config
              "RECOVER_OBJECT_DIR", "RECOVER_OBJECT_ORIGIN", "RECOVER_SOURCE_ORIGIN", "RECOVER_LEGACY_BUCKET", "REHEARSAL_FORBIDDEN_HOSTS",
              # image-build selfcheck process only (scrubbed child env), never operator config
              "IRONVISION_SELFCHECK", "PATH"}
    for tpl in ("deploy/digitalocean/env.production.template", "deploy/digitalocean/env.staging.template",
                "deploy/digitalocean/env.customer-production.template"):
        keys = {line.split("=", 1)[0].lstrip("# ").strip() for line in (ROOT / tpl).read_text().splitlines() if "=" in line}
        missing = used - keys - ignore
        assert not missing, f"{tpl} missing {sorted(missing)}"


@pytest.mark.skipif(not shutil.which("git") or not (ROOT / ".git").exists(), reason="git checkout required")
def test_gitignore_keeps_templates_and_ignores_real_env_files():
    def ignored(p: str) -> bool:
        return subprocess.run(["git", "check-ignore", "-q", "--no-index", p], cwd=ROOT).returncode == 0
    for dot, plain in PAIRS:
        assert not ignored(dot), f"{dot} is git-ignored"
        assert not ignored(plain), f"{plain} is git-ignored"
    for real in (".env", "backend/.env", "frontend/.env", "backend/worker/.env", "deploy/digitalocean/.env.production",
                 "deploy/digitalocean/.env.staging", "prod.env", "server.key", "cert.pem", "credentials.json"):
        assert ignored(real), f"{real} must stay git-ignored"


DOMAIN_KEYS = ("APP_DOMAIN", "FRONTEND_URL", "CORS_ORIGINS", "OIDC_ISSUER", "OIDC_REDIRECT_URI", "OIDC_POST_LOGOUT_REDIRECT_URI",
               "AUTH_DOMAIN", "LETSENCRYPT_EMAIL", "OPENROUTER_SITE_URL")


def _demo_settings() -> dict:
    import importlib.util
    spec = importlib.util.spec_from_file_location("ads", ROOT / "scripts" / "apply_demo_settings.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.DEMO


def test_demo_template_carries_the_demo_deployment_values():
    """The DEMO template (DEPLOYMENT_KIND=demo) ships the demo.ironvisionai.com values = apply_demo_settings.DEMO (single source)."""
    kv = _kv(ROOT / "deploy/digitalocean/env.production.template")
    assert {k: kv.get(k) for k in _demo_settings()} == _demo_settings()


@pytest.mark.parametrize("tpl", ["deploy/digitalocean/env.staging.template", "deploy/digitalocean/env.customer-production.template"])
def test_staging_and_customer_templates_keep_placeholders(tpl):
    kv = _kv(ROOT / tpl)
    for k in DOMAIN_KEYS:
        assert "ironvisionai.com" not in kv.get(k, "") and "theironvision.com" not in kv.get(k, ""), f"{tpl}: {k} must stay a placeholder"
    if "customer" in tpl:
        assert kv["DEPLOYMENT_KIND"] == "customer" and kv["ALLOW_SIGNUP"] == "false" and kv["ALLOW_DEMO_LOGIN"] == "false"
        assert kv["KEYCLOAK_ALLOW_REGISTRATION"] == "false"


def test_app_client_id_is_ironvision_app_everywhere():
    for tpl in ("env.production.template", "env.customer-production.template"):
        assert _kv(ROOT / "deploy/digitalocean" / tpl)["OIDC_CLIENT_ID"] == "ironvision-app"


def test_demo_template_passes_check_env_with_generated_secrets(tmp_path):
    import sys
    e = tmp_path / ".env.production"
    shutil.copy(ROOT / "deploy/digitalocean/env.production.template", e)
    e.chmod(0o600)
    subprocess.run([sys.executable, str(ROOT / "scripts/gen_env_secrets.py"), str(e)], check=True, capture_output=True)
    r = subprocess.run([sys.executable, str(ROOT / "scripts/check_env.py"), str(e)], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
