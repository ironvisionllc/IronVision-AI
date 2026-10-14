"""Repo-root ./deploy.sh: creates + stops on a missing env file, auto-fixes unquoted values then deploys, refuses tracked env files.
Runs the real scripts with a fake `docker` on PATH (no daemon needed)."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
FAKE_DOCKER = r"""#!/bin/bash
echo "docker $*" >> "$FAKE_LOG"
case "$1" in info) exit 0 ;; ps) exit 0 ;; esac
if [ "$1" = compose ]; then
  shift
  [ "$1" = version ] && { echo 2.29.7; exit 0; }
  if printf '%s\n' "$@" | grep -qx config; then
    printf '%s\n' "$@" | grep -qx -- --services && printf 'postgres\nseaweedfs\nobjectstore-init\nmigrate\nbackend\nworker\nfrontend\nedge\n'
    exit 0
  fi
  printf '%s\n' "$@" | grep -qx ps && printf 'backend\nworker\nfrontend\nedge\n'
  exit 0
fi
exit 0
"""


@pytest.fixture
def sim(tmp_path):
    if not shutil.which("bash"):
        pytest.skip("bash required")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    (bindir / "docker").write_text(FAKE_DOCKER)
    (bindir / "docker").chmod(0o755)
    (bindir / "systemctl").write_text('#!/bin/bash\necho "systemctl $*" >> "$FAKE_LOG"\n')
    (bindir / "systemctl").chmod(0o755)
    (tmp_path / "systemd").mkdir()
    env = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "FAKE_LOG": str(tmp_path / "docker.log"), "READY_TIMEOUT": "5",
           "SYSTEMD_DIR": str(tmp_path / "systemd")}
    return tmp_path, env


def _run(env, *args):
    return subprocess.run([str(ROOT / "deploy.sh"), *args], cwd="/", env=env, capture_output=True, text=True, timeout=120)


def test_missing_env_file_is_created_and_deploy_stops(sim):
    tmp, env = sim
    f = tmp / "new.env"
    r = _run(env, str(f))
    assert r.returncode == 2, r.stdout + r.stderr
    assert f.exists() and oct(f.stat().st_mode & 0o777) == "0o600"
    assert "NOT deployed yet" in r.stdout and "- APP_DOMAIN" in r.stdout and "- CORS_ORIGINS" in r.stdout
    text = f.read_text()
    assert "\nJWT_SECRET=\n" not in text and "POSTGRES_PASSWORD=" in text
    assert not (tmp / "docker.log").exists()                   # nothing was deployed


def test_existing_env_with_unquoted_scopes_is_fixed_then_deployed(sim):
    tmp, env = sim
    f = tmp / "prod.env"
    t = (ROOT / "deploy/digitalocean/env.production.template").read_text()
    t = (t.replace("app.example.gov", "rmf.agency.test").replace("idp.example.gov", "idp.agency.test")
          .replace('OIDC_SCOPES="openid profile email"', "OIDC_SCOPES=openid email profile")
          .replace("OIDC_CLIENT_SECRET=\n", "OIDC_CLIENT_SECRET=oidc-client-secret-value\n")
          .replace("DATA_ROOT=/srv/ironvision", f"DATA_ROOT={tmp}/data")
          .replace("LETSENCRYPT_EMAIL=\n", "LETSENCRYPT_EMAIL=k.hill@theironvision.com\n"))
    f.write_text(t)
    r = _run(env, str(f), "--skip-edge-check", "--no-cache")
    out = r.stdout + r.stderr
    assert r.returncode == 0, out[-3000:]
    assert "FIXED" in out and 'OIDC_SCOPES="openid email profile"' in f.read_text()
    assert list(tmp.glob("prod.env.bak-*")), "check_env --fix must leave a backup"
    assert "#### DEPLOYMENT SUCCEEDED" in out and "Ready: https://rmf.agency.test" in out
    assert "command not found" not in out
    log = (tmp / "docker.log").read_text()
    assert "build --no-cache" in log
    if os.geteuid() == 0:                                       # root → systemd units rendered for this checkout + enabled
        unit = (tmp / "systemd" / "ironvision-certbot-renew.service").read_text()
        assert f"WorkingDirectory={ROOT}" in unit and "/opt/ironvision/app" not in unit and "User=root" in unit
        assert f"--env-file {f}" in unit and "exec -T edge nginx -s reload" in unit
        assert "systemctl enable --now ironvision-certbot-renew.timer" in log


def test_placeholders_block_deploy(sim):
    tmp, env = sim
    f = tmp / "ph.env"
    shutil.copy(ROOT / "deploy/digitalocean/env.production.template", f)
    r = _run(env, str(f))
    assert r.returncode == 2 and "placeholder" in r.stderr and "- APP_DOMAIN" in r.stderr


def test_tracked_env_file_is_refused(sim):
    _, env = sim
    if subprocess.run(["git", "ls-files", "--error-unmatch", "deploy/digitalocean/.env.production.example"],
                      cwd=ROOT, capture_output=True).returncode != 0:
        pytest.skip("needs a git checkout with the templates tracked")
    r = _run(env, "deploy/digitalocean/.env.production.example")
    assert r.returncode == 1 and "is tracked by git" in r.stderr


def test_root_deploy_script_is_safe():
    s = (ROOT / "deploy.sh").read_text()
    assert os.access(ROOT / "deploy.sh", os.X_OK) and "set -euo pipefail" in s
    assert 'cd "$(dirname "${BASH_SOURCE[0]}")"' in s and "/opt/" not in s
    assert "scripts/envget.py" in s and 'exec scripts/deploy.sh "$F" "${PASS[@]}"' in s and "scripts/set_domain.py" in s
