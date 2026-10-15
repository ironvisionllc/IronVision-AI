"""Env templates ship in the repo (dot and non-dot copies), contain placeholders only, cover every variable, and are not git-ignored."""
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
              "CLAMAV_HOST", "CLAMAV_PORT", "AUTH_PROVIDER", "SUDO_USER"}
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
