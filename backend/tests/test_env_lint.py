"""Env files are data: one parser for every reader, lint/--fix, and no repo script may source an env file."""
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from dotenv import dotenv_values

from app.envfile import fix_env_text, lint_env_text, parse_env_text
from app.security.oidc import scopes

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = [".env.example", "backend/.env.example", "backend/worker/.env.example", "frontend/.env.example",
             "deploy/digitalocean/.env.production.example", "deploy/digitalocean/.env.staging.example",
             "env.template", "backend/env.template", "backend/worker/env.template", "frontend/env.template",
             "deploy/digitalocean/env.production.template", "deploy/digitalocean/env.staging.template"]
TRICKY = {
    "OIDC_SCOPES": ('"openid email profile"', "openid email profile"),
    "OPENROUTER_APP_NAME": ('"IronVision AI"', "IronVision AI"),
    "BANNER": ('"CUI // SP-PRVCY (synthetic)"', "CUI // SP-PRVCY (synthetic)"),
    "CSP": ('"default-src \'self\'; img-src \'self\' data:"', "default-src 'self'; img-src 'self' data:"),
    "CRON": ('"*/15 * * * *"', "*/15 * * * *"),
    "CIDRS": ('"10.0.0.0/8, 172.16.0.0/12"', "10.0.0.0/8, 172.16.0.0/12"),
    "URL": ('"https://x.example/cb?a=1&b=2"', "https://x.example/cb?a=1&b=2"),
    "PW_DOLLAR": ("'pa$$w0rd!#;|'", "pa$$w0rd!#;|"),
    "PLAIN": ("abc123", "abc123"),
    "INLINE": ("value   # trailing comment", "value"),
    "EMPTY": ("", ""),
}


def _tricky_file(tmp_path: Path) -> Path:
    f = tmp_path / "tricky.env"
    f.write_text("\n".join(f"{k}={raw}" for k, (raw, _) in TRICKY.items()) + "\n")
    return f


@pytest.mark.parametrize("tpl", TEMPLATES)
def test_templates_pass_env_lint(tpl):
    assert lint_env_text((ROOT / tpl).read_text()) == []


def test_parse_equivalence_python_dotenv_envget_shell(tmp_path):
    f = _tricky_file(tmp_path)
    ours = parse_env_text(f.read_text())
    dot = dotenv_values(f, interpolate=False)
    for k, (_, want) in TRICKY.items():
        assert ours[k] == want, k
        assert dot[k] == want or (want == "" and dot[k] in ("", None)), k
        got = subprocess.run(["python3", str(ROOT / "scripts/envget.py"), str(f), k], capture_output=True, text=True, check=True).stdout
        assert got == want, k
    sh = subprocess.run(["bash", "-c", f'. "{ROOT}/scripts/lib/envfile.sh"; env_get "$1" OIDC_SCOPES', "_", str(f)],
                        capture_output=True, text=True, check=True).stdout
    assert sh == "openid email profile"


def _compose() -> str | None:
    for c in (shutil.which("docker-compose"), "/root/tools/docker-compose"):
        if c and os.path.exists(c):
            return c
    return None


@pytest.mark.skipif(_compose() is None, reason="standalone docker compose binary not available")
def test_parse_equivalence_with_docker_compose(tmp_path):
    f = _tricky_file(tmp_path)
    keys = [k for k in TRICKY if k != "PW_DOLLAR"]        # `$` handling is covered by single quotes (literal) below
    yml = tmp_path / "c.yml"
    yml.write_text("services:\n  a:\n    image: alpine\n    environment:\n"
                   + "".join(f"      {k}: ${{{k}}}\n" for k in keys)
                   + "    env_file: [tricky.env]\n")
    out = subprocess.run([_compose(), "--env-file", str(f), "-f", str(yml), "config", "--format", "json"],
                         capture_output=True, text=True, check=True, cwd=tmp_path).stdout
    import json
    env = json.loads(out)["services"]["a"]["environment"]
    for k in keys:
        assert (env.get(k) or "") == TRICKY[k][1], k
    assert env["PW_DOLLAR"].replace("$$", "$") == "pa$$w0rd!#;|"   # literal; `config` re-escapes $ as $$ in its YAML output


def test_lint_flags_customer_line_and_fix_rewrites_safely(tmp_path):
    bad = ("APP_ENV=production\r\nOIDC_SCOPES=openid email profile\r\nexport FOO=bar\r\nDUP=1\r\nDUP=2  \r\n"
           "1BAD=x\r\nQ=\"open\r\nOK=\"fine\"\r\n# comment kept\r\n")
    msgs = [i["message"] for i in lint_env_text(bad)]
    assert any("CRLF" in m for m in msgs) and any("OIDC_SCOPES: unquoted value contains whitespace" in m for m in msgs)
    assert any("export" in m for m in msgs) and any("duplicate key DUP" in m for m in msgs)
    assert any("trailing whitespace" in m for m in msgs) and any("invalid variable name '1BAD'" in m for m in msgs)
    assert any("unbalanced quote" in m for m in msgs)
    sug = next(i for i in lint_env_text(bad) if "OIDC_SCOPES" in i["message"])["suggestion"]
    assert sug == 'OIDC_SCOPES="openid email profile"'
    new, changes, unfixable = fix_env_text(bad)
    assert "\r" not in new and 'OIDC_SCOPES="openid email profile"' in new and "\nFOO=bar\n" in new
    assert "# comment kept" in new and "# [check_env --fix] duplicate" in new and "\nDUP=2\n" in new
    assert any("1BAD" in u for u in unfixable) and any("Q has an unbalanced quote" in u for u in unfixable)
    env = parse_env_text(new)
    assert env["OIDC_SCOPES"] == "openid email profile" and env["DUP"] == "2" and env["FOO"] == "bar"


def test_check_env_cli_fix_backup_and_errors_in_production(tmp_path):
    f = tmp_path / ".env.production"
    shutil.copy(ROOT / "deploy/digitalocean/env.production.template", f)
    f.write_text(f.read_text().replace('OIDC_SCOPES="openid profile email"', "OIDC_SCOPES=openid email profile"))
    r = subprocess.run(["python3", str(ROOT / "scripts/check_env.py"), str(f)], capture_output=True, text=True)
    assert r.returncode == 1 and "OIDC_SCOPES: unquoted value contains whitespace" in r.stdout
    assert 'fix: OIDC_SCOPES="openid email profile"' in r.stdout and "--fix" in r.stdout
    r = subprocess.run(["python3", str(ROOT / "scripts/check_env.py"), "--fix", str(f)], capture_output=True, text=True)
    assert "FIXED line" in r.stdout and 'OIDC_SCOPES="openid email profile"' in f.read_text()
    assert oct(f.stat().st_mode & 0o777) == "0o600"
    backups = list(tmp_path.glob(".env.production.bak-*"))
    assert len(backups) == 1 and oct(backups[0].stat().st_mode & 0o777) == "0o600"
    assert "OIDC_SCOPES=openid email profile" in backups[0].read_text()
    r = subprocess.run(["python3", str(ROOT / "scripts/check_env.py"), str(f)], capture_output=True, text=True)
    assert "OIDC_SCOPES" not in r.stdout


def test_oidc_scopes_tolerant():
    assert scopes("openid email profile") == "openid email profile"
    assert scopes('"openid email profile"') == "openid email profile"
    assert scopes("openid,email, profile") == "openid email profile"
    assert scopes("email profile") == "openid email profile"
    assert scopes(None) == "openid profile email"


SOURCING = re.compile(
    r"""(^|[;&|]\s*|\bthen\s+|\bdo\s+)(\.|source)\s+["']?[^\s"']*(\.env\b|env\.production|env\.staging|\$\{?(ENV_FILE|F|ENVF|envf)\b)"""
    r"""|\bset\s+-a\b|export\s+\$\((cat|grep|sed|xargs)|\beval\s+["']?\$\((cat|grep)|xargs\s+-[0-9]*\s*export|\benv\s+\$\(cat""",
    re.M)
SCAN_SUFFIX = {".sh", ".md", ".yml", ".yaml", ".service", ".timer", ".py"}
SKIP_DIRS = {"node_modules", ".git", ".emergent", "build", "memory", "test_reports", "__pycache__"}


def test_no_repo_script_or_doc_sources_an_env_file():
    hits = []
    for p in ROOT.rglob("*"):
        if not p.is_file() or SKIP_DIRS & set(p.relative_to(ROOT).parts):
            continue
        if p.suffix not in SCAN_SUFFIX and p.name != "Makefile":
            continue
        if p.name == "test_env_lint.py":
            continue
        in_code = p.suffix != ".md"                      # markdown: only code blocks are commands people copy-paste
        for n, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
            if p.suffix == ".md" and line.lstrip().startswith("```"):
                in_code = not in_code
                continue
            if in_code and SOURCING.search(line):
                hits.append(f"{p.relative_to(ROOT)}:{n}: {line.strip()[:120]}")
    assert hits == [], "env files must never be sourced – use scripts/envget.py / env_get:\n" + "\n".join(hits)
