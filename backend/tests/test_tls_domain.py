"""--set-domain rewrite and automatic TLS (scripts/ensure_tls.sh) with fake docker / openssl / getent / curl / ss."""
import importlib.util
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("set_domain", ROOT / "scripts" / "set_domain.py")
sd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sd)

FAKES = {
    "docker": 'echo "docker $*" >> "$FAKE_LOG"\nexit 0\n',
    "getent": '[ -n "$FAKE_DNS_IP" ] && echo "$FAKE_DNS_IP     STREAM $2"\nexit 0\n',
    "curl": 'case "$*" in *169.254.169.254*) echo "${FAKE_PUBLIC_IP}"; exit 0 ;; esac\necho "curl $*" >> "$FAKE_LOG"\nexit 0\n',
    "ss": "exit 0\n",
    "openssl": r'''case "$*" in
  *-checkend*) [ "${FAKE_CERT_OK:-0}" = 1 ]; exit $? ;;
  *-checkhost*) if [ "${FAKE_CERT_OK:-0}" = 1 ]; then echo "Hostname $FAKE_DOMAIN does match certificate"; else echo "does NOT match"; fi; exit 0 ;;
  *-issuer*) echo "issuer=C = US, O = Let's Encrypt, CN = R11"; exit 0 ;;
  *-enddate*) echo "notAfter=Jan  1 00:00:00 2027 GMT"; exit 0 ;;
esac
exit 0
''',
}
DOMAIN = "demo.ironvisionai.com"


@pytest.fixture
def tls(tmp_path):
    b = tmp_path / "bin"
    b.mkdir()
    for name, body in FAKES.items():
        (b / name).write_text("#!/bin/bash\n" + body)
        (b / name).chmod(0o755)
    data = tmp_path / "data"
    f = tmp_path / "prod.env"
    f.write_text(f"APP_DOMAIN={DOMAIN}\nDATA_ROOT={data}\nLETSENCRYPT_EMAIL=k.hill@theironvision.com\nLETSENCRYPT_STAGING=false\n")
    env = {**os.environ, "PATH": f"{b}:{os.environ['PATH']}", "FAKE_LOG": str(tmp_path / "log"), "FAKE_DOMAIN": DOMAIN,
           "FAKE_DNS_IP": "203.0.113.10", "FAKE_PUBLIC_IP": "203.0.113.10"}
    return tmp_path, f, data, env


def _ensure(env, f):
    return subprocess.run([str(ROOT / "scripts/ensure_tls.sh"), "ensure", str(f), "--", "docker", "compose", "-p", "ironvision"],
                          env=env, capture_output=True, text=True, timeout=60)


def _log(tmp):
    p = tmp / "log"
    return p.read_text() if p.exists() else ""


def test_set_domain_rewrites_every_occurrence_with_backup(tmp_path):
    tpl = (ROOT / "deploy/digitalocean/env.production.template").read_text()
    f = tmp_path / ".env.production"
    f.write_text(tpl.replace("POSTGRES_PASSWORD=", "POSTGRES_PASSWORD=keep-this-secret-app.example.gov")
                 + "PUBLIC_BASE_URL=https://app.example.gov/portal\n")
    before = sd.envfile.parse_env_text(f.read_text())
    assert sd.main([str(f), DOMAIN, "--email", "k.hill@theironvision.com"]) == 0
    after = sd.envfile.parse_env_text(f.read_text())
    assert after["APP_DOMAIN"] == DOMAIN and after["FRONTEND_URL"] == after["CORS_ORIGINS"] == f"https://{DOMAIN}"
    assert after["OPENROUTER_SITE_URL"] == f"https://{DOMAIN}" and after["LETSENCRYPT_EMAIL"] == "k.hill@theironvision.com"
    assert after["OIDC_REDIRECT_URI"] == f"https://{DOMAIN}/api/v1/auth/oidc/callback"
    assert after["PUBLIC_BASE_URL"] == f"https://{DOMAIN}/portal"
    assert after["POSTGRES_PASSWORD"] == before["POSTGRES_PASSWORD"]           # secrets never rewritten
    assert after["OIDC_ISSUER"] == before["OIDC_ISSUER"]                       # the IdP host is not the app domain
    assert "app.example.gov" not in "".join(v for k, v in after.items() if not sd.is_secret(k))
    backups = list(tmp_path.glob(".env.production.bak-*"))
    assert len(backups) == 1 and oct(f.stat().st_mode & 0o777) == "0o600"
    assert sd.main([str(f), DOMAIN]) == 0                                      # idempotent
    assert sd.main([str(f), "not a domain"]) == 2 and sd.main([str(f), "app.example.gov"]) == 2


def test_dns_mismatch_stops(tls):
    tmp, f, _, env = tls
    r = _ensure({**env, "FAKE_DNS_IP": "198.51.100.7"}, f)
    assert r.returncode == 1 and f"Create DNS A record {DOMAIN} → 203.0.113.10" in r.stderr
    assert "certbot" not in _log(tmp)
    r = _ensure({**env, "FAKE_DNS_IP": ""}, f)
    assert r.returncode == 1 and "does not resolve" in r.stderr


def test_valid_certificate_is_kept(tls):
    tmp, f, data, env = tls
    live = data / "letsencrypt" / "live" / DOMAIN
    live.mkdir(parents=True)
    (live / "fullchain.pem").write_text("CERT")
    r = _ensure({**env, "FAKE_CERT_OK": "1"}, f)
    assert r.returncode == 0 and "nothing to do" in r.stdout and "certbot" not in _log(tmp)


def test_missing_certificate_runs_certbot_standalone(tls):
    tmp, f, data, env = tls
    live = data / "letsencrypt" / "live" / DOMAIN
    script = tmp / "bin" / "docker"     # simulate certbot writing the cert so the post-check passes
    script.write_text(f'#!/bin/bash\necho "docker $*" >> "$FAKE_LOG"\ncase "$*" in *certonly*) mkdir -p {live}; echo CERT > {live}/fullchain.pem; '
                      f'touch {tmp}/issued ;; esac\nexit 0\n')
    (tmp / "bin" / "openssl").write_text("#!/bin/bash\n" + FAKES["openssl"].replace('[ "${FAKE_CERT_OK:-0}" = 1 ]', f'[ -f {tmp}/issued ]')
                                         .replace('if [ "${FAKE_CERT_OK:-0}" = 1 ]', f'if [ -f {tmp}/issued ]'))
    r = _ensure(env, f)
    assert r.returncode == 0, r.stdout + r.stderr
    log = _log(tmp)
    assert "docker compose -p ironvision stop edge" in log
    cmd = next(line for line in log.splitlines() if "certonly" in line)
    assert "--profile certbot run --rm --no-deps -p 80:80 certbot certonly --standalone --non-interactive --agree-tos" in cmd
    assert f"-m k.hill@theironvision.com --no-eff-email -d {DOMAIN} --keep-until-expiring" in cmd and "--staging" not in cmd


def test_staging_flag_and_missing_email(tls):
    tmp, f, _, env = tls
    f.write_text(f.read_text().replace("LETSENCRYPT_STAGING=false", "LETSENCRYPT_STAGING=true"))
    _ensure(env, f)
    assert "--staging" in next(line for line in _log(tmp).splitlines() if "certonly" in line)
    f.write_text(f.read_text().replace("LETSENCRYPT_EMAIL=k.hill@theironvision.com", "LETSENCRYPT_EMAIL="))
    r = _ensure(env, f)
    assert r.returncode == 1 and "LETSENCRYPT_EMAIL is required" in r.stderr


def test_force_tls_skips_dns(tls):
    tmp, f, _, env = tls
    _ensure({**env, "FAKE_DNS_IP": "198.51.100.7", "FORCE_TLS": "1"}, f)
    assert "certonly" in _log(tmp)
