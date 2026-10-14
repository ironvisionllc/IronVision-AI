#!/usr/bin/env python3
"""Switch the public domain in an env file safely (backup first, mode 600, never sources the file, never prints secrets).
Usage: python3 scripts/set_domain.py deploy/digitalocean/.env.production demo.ironvisionai.com [--email admin@example.org]
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


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
