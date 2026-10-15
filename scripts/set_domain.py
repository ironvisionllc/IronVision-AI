#!/usr/bin/env python3
"""Switch the public domain in an env file safely (backup first, mode 600, never sources the file, never prints secrets).
Usage: python3 scripts/set_domain.py deploy/digitalocean/.env.production demo.ironvisionai.com [--email admin@example.org]
       python3 scripts/set_domain.py deploy/digitalocean/.env.production --auth-domain auth.demo.ironvisionai.com
Sets APP_DOMAIN, FRONTEND_URL, CORS_ORIGINS, OPENROUTER_SITE_URL, OIDC_REDIRECT_URI and LETSENCRYPT_EMAIL, and replaces every
other occurrence of the old domain (and of the template placeholder app.example.gov) in non-secret values."""
import importlib.util
import os
import re
import shutil
import sys
import time
from pathlib import Path

_spec = importlib.util.spec_from_file_location("envfile", Path(__file__).resolve().parent.parent / "backend" / "app" / "envfile.py")
envfile = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(envfile)

PLACEHOLDER = "app.example.gov"
SECRETISH = ("SECRET", "PASSWORD", "TOKEN", "_KEY")
HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def is_secret(key: str) -> bool:
    return any(s in key for s in SECRETISH) and key != "LETSENCRYPT_EMAIL"


def plan(env: dict, domain: str, email: str | None) -> dict[str, str]:
    url = f"https://{domain}"
    want = {"APP_DOMAIN": domain, "FRONTEND_URL": url, "CORS_ORIGINS": url, "OPENROUTER_SITE_URL": url,
            "OIDC_REDIRECT_URI": f"{url}/api/v1/auth/oidc/callback"}
    if email:
        want["LETSENCRYPT_EMAIL"] = email
    old = {d for d in (env.get("APP_DOMAIN"), PLACEHOLDER) if d and d != domain}
    for k, v in env.items():
        if k not in want and not is_secret(k) and any(o in v for o in old):
            nv = v
            for o in old:
                nv = nv.replace(o, domain)
            want[k] = nv
    return {k: v for k, v in want.items() if env.get(k) != v}


def plan_auth(env: dict, auth_domain: str) -> dict[str, str]:
    """Built-in Keycloak on AUTH_DOMAIN. AUTH_PROVIDERS is deliberately NOT changed (switch only after the user migration)."""
    app = env.get("APP_DOMAIN") or ""
    realm = env.get("KEYCLOAK_REALM") or "ironvision-demo"
    want = {"AUTH_DOMAIN": auth_domain, "KEYCLOAK_REALM": realm, "OIDC_ISSUER": f"https://{auth_domain}/realms/{realm}",
            "OIDC_CLIENT_ID": "ironvision-app",
            "OIDC_REDIRECT_URI": f"https://{app}/api/v1/auth/oidc/callback", "OIDC_POST_LOGOUT_REDIRECT_URI": f"https://{app}/login",
            "KEYCLOAK_ADMIN_USERNAME": env.get("KEYCLOAK_ADMIN_USERNAME") or "ironvision-admin"}
    return {k: v for k, v in want.items() if env.get(k) != v}


def apply(text: str, changes: dict[str, str]) -> str:
    out, done = [], set()
    for raw in text.split("\n"):
        s = raw.strip()
        key = s.split("=", 1)[0].strip() if "=" in s and not s.startswith("#") else None
        if key in changes:
            v = changes[key]
            out.append(f"{key}={envfile.quote(v) if envfile.needs_quotes(v) else v}")
            done.add(key)
        else:
            out.append(raw)
    missing = [k for k in changes if k not in done]
    if missing:
        if out and out[-1] == "":
            out.pop()
        out += ["# added by scripts/set_domain.py"] + [f"{k}={changes[k]}" for k in missing] + [""]
    return "\n".join(out)


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    email = argv[argv.index("--email") + 1] if "--email" in argv else None
    if email:
        args.remove(email)
    auth = argv[argv.index("--auth-domain") + 1].strip().lower().rstrip(".") if "--auth-domain" in argv else None
    if auth:
        args = [a for a in args if a.strip().lower().rstrip(".") != auth]
        return set_auth(Path(args[0]), auth) if len(args) == 1 else 2
    if len(args) != 2:
        print(__doc__.split("\n")[1])
        return 2
    path, domain = Path(args[0]), args[1].strip().lower().rstrip(".")
    if not HOST_RE.match(domain) or domain.endswith((".example.gov", ".example.com", ".example")):
        print(f"set_domain: {domain!r} is not a usable public hostname")
        return 2
    if email and not EMAIL_RE.match(email):
        print(f"set_domain: {email!r} is not a valid e-mail address")
        return 2
    text = path.read_text()
    changes = plan(envfile.parse_env_text(text), domain, email)
    if not changes:
        print(f"set_domain: {path} already uses {domain} – nothing to change")
        return 0
    env = envfile.parse_env_text(text)
    backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup)
    os.chmod(backup, 0o600)
    tmp = path.with_name(path.name + ".domaintmp")
    tmp.write_text(apply(text, changes))
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    print(f"set_domain: {path} → {domain} (backup {backup})")
    for k, v in changes.items():
        print(f"  {k}: {env.get(k, '<unset>')!s} → {v}")
    return 0


def _write(path: Path, text: str, changes: dict[str, str], label: str) -> int:
    env = envfile.parse_env_text(text)
    backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup)
    os.chmod(backup, 0o600)
    tmp = path.with_name(path.name + ".domaintmp")
    tmp.write_text(apply(text, changes))
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    print(f"set_domain: {path} → {label} (backup {backup})")
    for k, v in changes.items():
        print(f"  {k}: {env.get(k, '<unset>')!s} → {v}")
    return 0


def set_auth(path: Path, auth: str) -> int:
    text = path.read_text()
    env = envfile.parse_env_text(text)
    app = env.get("APP_DOMAIN") or ""
    if not HOST_RE.match(auth) or auth.endswith((".example.gov", ".example.com", ".example")):
        print(f"set_domain: {auth!r} is not a usable public hostname")
        return 2
    if not app or app == PLACEHOLDER or auth == app:
        print("set_domain: set APP_DOMAIN first (--set-domain) – the auth domain must differ from it, e.g. auth.<app-domain>")
        return 2
    changes = plan_auth(env, auth)
    if not changes:
        print(f"set_domain: {path} already uses auth domain {auth} – nothing to change")
        return 0
    return _write(path, text, changes, f"auth domain {auth}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
