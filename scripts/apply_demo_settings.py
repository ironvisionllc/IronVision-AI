#!/usr/bin/env python3
"""Apply the demo.ironvisionai.com settings to an EXISTING env file in place: backup first, mode 600, the file is never
sourced, secrets are never changed or printed. Dry run by default (prints the key diff); --yes writes.
Usage: python3 scripts/apply_demo_settings.py deploy/digitalocean/.env.production [--dry-run] [--yes]
OIDC_CLIENT_ID is written only after the live Keycloak realm confirms the client exists (OIDC discovery + a PKCE
authorization probe; Keycloak answers "Client not found." otherwise). APPLY_DEMO_PROBE_ISSUER overrides the probed issuer.
Exit: 0 ok · 2 usage error · 3 OIDC_CLIENT_ID kept because the client could not be verified (other keys handled normally)."""
import base64
import hashlib
import importlib.util
import json
import os
import secrets
import shutil
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("set_domain", HERE / "set_domain.py")
set_domain = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(set_domain)
envfile = set_domain.envfile

DEMO = {
    "APP_DOMAIN": "demo.ironvisionai.com",
    "FRONTEND_URL": "https://demo.ironvisionai.com",
    "CORS_ORIGINS": "https://demo.ironvisionai.com",
    "LETSENCRYPT_EMAIL": "k.hill@theironvision.com",
    "OIDC_REDIRECT_URI": "https://demo.ironvisionai.com/api/v1/auth/oidc/callback",
    "AUTH_DOMAIN": "auth.demo.ironvisionai.com",
    "OIDC_ISSUER": "https://auth.demo.ironvisionai.com/realms/ironvision-demo",
    "OIDC_POST_LOGOUT_REDIRECT_URI": "https://demo.ironvisionai.com/login",
    "OIDC_CLIENT_ID": "ironvision-app",
    "ALLOW_DEMO_LOGIN": "true",
    "KEYCLOAK_ALLOW_REGISTRATION": "true",
    "DEPLOYMENT_KIND": "demo",
    "ALLOW_SIGNUP": "false",
    "SEED_DEMO_DATA": "false",
    "APP_ENV": "production",
    "OPENROUTER_SITE_URL": "https://demo.ironvisionai.com",
    "SEAWEEDFS_IMAGE": "chrislusf/seaweedfs:4.48@sha256:4e61d15fd35994cb1e43e1e553dff106794841fd9a99ade2fc8c8bfce4d7872d",
}
assert not any(set_domain.is_secret(k) for k in DEMO), "DEMO must never contain secrets"
FIX = "./deploy.sh --apply-realm   (creates/updates client ironvision-app in realm ironvision-demo), then: ./deploy.sh --apply-demo-settings --yes"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None


def verify_client(issuer: str, client_id: str, redirect_uri: str, timeout: float = 10) -> tuple[str, str]:
    """('ok'|'redirect_mismatch'|'missing'|'unreachable'|'unknown', detail). ok/redirect_mismatch mean the client exists."""
    issuer = issuer.rstrip("/")
    try:
        with urllib.request.urlopen(f"{issuer}/.well-known/openid-configuration", timeout=timeout) as r:
            disco = json.load(r)
    except (urllib.error.URLError, OSError, ValueError) as e:
        return "unreachable", f"discovery {issuer}/.well-known/openid-configuration failed: {e}"
    if (disco.get("issuer") or "").rstrip("/") != issuer:
        return "unreachable", f"discovery issuer {disco.get('issuer')!r} != {issuer!r}"
    verifier = secrets.token_urlsafe(48)
    q = urllib.parse.urlencode({
        "client_id": client_id, "response_type": "code", "scope": "openid", "redirect_uri": redirect_uri,
        "state": secrets.token_urlsafe(16), "nonce": secrets.token_urlsafe(16), "code_challenge_method": "S256",
        "code_challenge": base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()})
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(f"{disco['authorization_endpoint']}?{q}", timeout=timeout) as r:
            code, body, loc = r.status, r.read(), ""
    except urllib.error.HTTPError as e:
        code, body, loc = e.code, e.read(), e.headers.get("Location") or ""
    except (urllib.error.URLError, OSError, KeyError) as e:
        return "unreachable", f"authorization request failed: {e}"
    text = body.decode(errors="replace").lower()
    if "client not found" in text:
        return "missing", f"Keycloak: client {client_id!r} not found in {issuer}"
    if "invalid parameter: redirect_uri" in text or "invalid redirect" in text:
        return "redirect_mismatch", f"client {client_id!r} exists but does not allow redirect {redirect_uri}"
    if code in (302, 303) and loc.startswith(redirect_uri):
        return "ok", f"client {client_id!r} exists (Keycloak redirected back: {urllib.parse.urlparse(loc).query[:80]})"
    if code == 200 and ("kc-form-login" in text or 'name="username"' in text):
        return "ok", f"client {client_id!r} exists (Keycloak login page served)"
    return "unknown", f"unexpected Keycloak answer HTTP {code}"


def main(argv: list[str]) -> int:
    flags = {a for a in argv if a.startswith("--")}
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1 or flags - {"--dry-run", "--yes"}:
        print(__doc__.split("\n")[2])
        return 2
    path = Path(args[0])
    if not path.is_file():
        print(f"apply_demo_settings: {path} not found (run ./deploy.sh once to create it)")
        return 2
    write = "--yes" in flags and "--dry-run" not in flags
    text = path.read_text()
    env = envfile.parse_env_text(text)
    changes = {k: v for k, v in DEMO.items() if env.get(k) != v}
    rc = 0

    probe = os.environ.get("APPLY_DEMO_PROBE_ISSUER") or DEMO["OIDC_ISSUER"]
    status, detail = verify_client(probe, DEMO["OIDC_CLIENT_ID"], DEMO["OIDC_REDIRECT_URI"])
    print(f"apply_demo_settings: Keycloak client check ({probe}): {status.upper()} – {detail}")
    if status not in ("ok", "redirect_mismatch"):
        rc = 3
        if changes.pop("OIDC_CLIENT_ID", None) is not None:
            print(f"  OIDC_CLIENT_ID NOT changed (stays {env.get('OIDC_CLIENT_ID') or '<unset>'}).")
        print(f"  Existing clients: scripts/keycloak.sh {path} clients\n  Fix: {FIX}")
    elif status == "redirect_mismatch":
        print(f"  WARN the client exists but its redirect URIs are stale. Fix: {FIX}")
    if (env.get("KEYCLOAK_REALM") or "ironvision-demo") != "ironvision-demo":
        print(f"  WARN KEYCLOAK_REALM={env.get('KEYCLOAK_REALM')} but OIDC_ISSUER uses realm ironvision-demo – set KEYCLOAK_REALM=ironvision-demo")

    print(f"apply_demo_settings: {path} – {len(changes)} key(s) to change (values are non-secret):")
    for k, v in DEMO.items():
        old = env.get(k, "<unset>")
        print(f"  {'~' if k in changes else '='} {k}: {old} → {v}" if k in changes else f"  = {k}: {v}")
    if not changes:
        print("apply_demo_settings: nothing to change")
        return rc
    if not write:
        print("apply_demo_settings: DRY RUN – nothing written. Apply with: ./deploy.sh --apply-demo-settings --yes")
        return rc
    backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup)
    os.chmod(backup, 0o600)
    tmp = path.with_name(path.name + ".demotmp")
    tmp.write_text(set_domain.apply(text, changes))
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)
    print(f"apply_demo_settings: written {len(changes)} key(s) in place (backup {backup}, mode 600)")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
