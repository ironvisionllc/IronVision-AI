"""scripts/apply_demo_settings.py + ./deploy.sh --apply-demo-settings: key diff, dry run, backup, secrets untouched,
Keycloak client verification (fake Keycloak for pass/fail; the REAL Keycloak 26 when KEYCLOAK_LIVE_URL is set)."""
import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "apply_demo_settings.py"
_spec = importlib.util.spec_from_file_location("apply_demo_settings", SCRIPT)
ads = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ads)

SECRETS = {"JWT_SECRET": "Jw7Lm2Vw9Rz4Kp8Td3Nb6Hc1Jf5Yg0Ua9Qe", "POSTGRES_PASSWORD": "Pg3Xq8Lm1Vt6Rz9Kc4Nb7Hd2Jf5Yw0Ua",
           "OIDC_CLIENT_SECRET": "Oc7Lm2Vw9Rz4Kp8Td3Nb6Hc1Jf5Yg0Ua9", "KEYCLOAK_ADMIN_PASSWORD": "Ka5Wd8Lp2Qx7Rm1Vt4Nc9Hb6Jf3Yz0Ue"}
OLD_DROPLET = """# existing Droplet env (older layout)
APP_ENV=production
DEPLOYMENT_KIND=demo
APP_DOMAIN=demo.ironvisionai.com
FRONTEND_URL=https://demo.ironvisionai.com
CORS_ORIGINS=https://old.example.org
LETSENCRYPT_EMAIL=
AUTH_PROVIDERS=oidc
OIDC_ISSUER=https://auth.demo.ironvisionai.com/realms/ironvision-demo
OIDC_CLIENT_ID=ironvision
OIDC_REDIRECT_URI=https://demo.ironvisionai.com/api/v1/auth/oidc/callback
OIDC_SCOPES="openid profile email"
ALLOW_DEMO_LOGIN=false
SEED_DEMO_DATA=false
""" + "".join(f"{k}={v}\n" for k, v in SECRETS.items())


class FakeKeycloak(BaseHTTPRequestHandler):
    clients = {"ironvision-app"}
    redirect = ads.DEMO["OIDC_REDIRECT_URI"]

    def log_message(self, *a):
        pass

    def do_GET(self):
        base = f"http://127.0.0.1:{self.server.server_port}/realms/ironvision-demo"
        u = urllib.parse.urlparse(self.path)
        if u.path.endswith("/.well-known/openid-configuration"):
            return self._send(200, json.dumps({"issuer": base, "authorization_endpoint": f"{base}/protocol/openid-connect/auth"}))
        q = dict(urllib.parse.parse_qsl(u.query))
        if q.get("client_id") not in self.clients:
            return self._send(400, "<html><p id='kc-error-message'>Client not found.</p></html>")
        if q.get("redirect_uri") != self.redirect:
            return self._send(400, "<html><p>Invalid parameter: redirect_uri</p></html>")
        return self._send(200, '<form id="kc-form-login"><input name="username"></form>')

    def _send(self, code, body):
        self.send_response(code)
        self.end_headers()
        self.wfile.write(body.encode())


@pytest.fixture
def kc(monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeKeycloak)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    monkeypatch.setenv("APPLY_DEMO_PROBE_ISSUER", f"http://127.0.0.1:{srv.server_port}/realms/ironvision-demo")
    FakeKeycloak.clients = {"ironvision-app"}
    yield FakeKeycloak
    srv.shutdown()


@pytest.fixture
def envf(tmp_path):
    p = tmp_path / ".env.production"
    p.write_text(OLD_DROPLET)
    p.chmod(0o600)
    return p


def run(*args, cwd=ROOT, script=None):
    cmd = script or [sys.executable, str(SCRIPT)]
    return subprocess.run([*cmd, *map(str, args)], capture_output=True, text=True, cwd=cwd, env=os.environ.copy(), timeout=60, check=False)


def parse(p: Path) -> dict:
    return ads.envfile.parse_env_text(p.read_text())


def test_dry_run_prints_key_diff_and_writes_nothing(kc, envf):
    before = hashlib.sha256(envf.read_bytes()).hexdigest()
    r = run(envf)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "~ CORS_ORIGINS: https://old.example.org → https://demo.ironvisionai.com" in r.stdout
    assert "~ OIDC_CLIENT_ID: ironvision → ironvision-app" in r.stdout and "= APP_DOMAIN: demo.ironvisionai.com" in r.stdout
    assert "DRY RUN" in r.stdout and "client check" in r.stdout and "OK" in r.stdout
    assert hashlib.sha256(envf.read_bytes()).hexdigest() == before
    assert not list(envf.parent.glob("*.bak-*"))


def test_yes_writes_only_demo_keys_with_backup_and_mode_600(kc, envf):
    r = run(envf, "--yes")
    assert r.returncode == 0, r.stdout + r.stderr
    env = parse(envf)
    assert all(env[k] == v for k, v in ads.DEMO.items())
    assert all(env[k] == v for k, v in SECRETS.items()), "secrets must be byte-identical"
    assert env["OIDC_SCOPES"] == "openid profile email" and env["AUTH_PROVIDERS"] == "oidc"
    (bak,) = envf.parent.glob(".env.production.bak-*")
    assert bak.read_text() == OLD_DROPLET
    assert stat.S_IMODE(envf.stat().st_mode) == 0o600 and stat.S_IMODE(bak.stat().st_mode) == 0o600
    for v in SECRETS.values():
        assert v not in r.stdout + r.stderr, "secret printed"
    old_lines = [ln for ln in OLD_DROPLET.splitlines() if ln.split("=", 1)[0] not in ads.DEMO]
    assert all(ln in envf.read_text().splitlines() for ln in old_lines), "non-demo lines must stay untouched"
    r2 = run(envf, "--yes")
    assert r2.returncode == 0 and "nothing to change" in r2.stdout
    assert len(list(envf.parent.glob(".env.production.bak-*"))) == 1


def test_missing_client_keeps_oidc_client_id_and_prints_fix(kc, envf):
    kc.clients = {"ironvision", "account"}
    r = run(envf, "--yes")
    assert r.returncode == 3, r.stdout
    assert "MISSING" in r.stdout and "not found" in r.stdout and "--apply-realm" in r.stdout and "clients" in r.stdout
    env = parse(envf)
    assert env["OIDC_CLIENT_ID"] == "ironvision", "OIDC_CLIENT_ID must not change when the client does not exist"
    assert env["CORS_ORIGINS"] == ads.DEMO["CORS_ORIGINS"] and env["ALLOW_DEMO_LOGIN"] == "true"


def test_unreachable_keycloak_keeps_oidc_client_id(monkeypatch, envf):
    monkeypatch.setenv("APPLY_DEMO_PROBE_ISSUER", "http://127.0.0.1:9/realms/ironvision-demo")
    r = run(envf, "--yes")
    assert r.returncode == 3 and "UNREACHABLE" in r.stdout
    assert parse(envf)["OIDC_CLIENT_ID"] == "ironvision"


def test_redirect_mismatch_means_client_exists(kc, envf):
    kc.redirect = "https://other.example/cb"
    try:
        r = run(envf, "--yes")
    finally:
        kc.redirect = ads.DEMO["OIDC_REDIRECT_URI"]
    assert r.returncode == 0 and "REDIRECT_MISMATCH" in r.stdout and "--apply-realm" in r.stdout
    assert parse(envf)["OIDC_CLIENT_ID"] == "ironvision-app"


def test_usage_errors(tmp_path):
    assert run().returncode == 2
    assert run(tmp_path / "nope.env").returncode == 2
    assert run(tmp_path / "x", "--force").returncode == 2


def test_deploy_sh_dry_run_changes_nothing_and_does_not_deploy(kc, envf):
    before = envf.read_bytes()
    r = run(envf, "--apply-demo-settings", script=["bash", str(ROOT / "deploy.sh")])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "Dry run only" in r.stdout and "~ OIDC_CLIENT_ID" in r.stdout
    assert envf.read_bytes() == before and not list(envf.parent.glob("*.bak-*"))


def test_demo_values_contain_no_secrets():
    assert not any(ads.set_domain.is_secret(k) for k in ads.DEMO)


@pytest.mark.skipif(not os.environ.get("KEYCLOAK_LIVE_URL"), reason="REAL Keycloak not available (set KEYCLOAK_LIVE_URL)")
def test_verify_client_against_real_keycloak():
    issuer, redirect = os.environ["OIDC_ISSUER"], os.environ["OIDC_REDIRECT_URI"]
    assert ads.verify_client(issuer, os.environ["OIDC_CLIENT_ID"], redirect)[0] == "ok"
    assert ads.verify_client(issuer, "no-such-client-xyz", redirect)[0] == "missing"
    assert ads.verify_client(issuer, os.environ["OIDC_CLIENT_ID"], "https://evil.example/cb")[0] == "redirect_mismatch"
