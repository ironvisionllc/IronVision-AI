#!/usr/bin/env python3
"""Fills EMPTY secret values in an env file in place. Never overwrites a value that is already set; never prints secrets.
Usage: python3 scripts/gen_env_secrets.py deploy/digitalocean/.env.production
S3 keys are generated only for the built-in object store (STORAGE_DRIVER=s3 with S3_ENDPOINT_URL empty); external S3
(Spaces/AWS) keys must come from the provider. The file is rewritten atomically with mode 600."""
import base64
import os
import secrets
import string
import sys
from pathlib import Path

ALNUM = string.ascii_letters + string.digits


def pw() -> str:
    return "".join(secrets.choice(ALNUM) for _ in range(48))


BASE = {
    "POSTGRES_PASSWORD": pw,
    "JWT_SECRET": pw,
    "SECRET_STORE_KEY": lambda: base64.urlsafe_b64encode(os.urandom(32)).decode(),
    "DEMO_USER_PASSWORD": pw,
}
KEYCLOAK = {   # only when AUTH_DOMAIN is set (built-in Keycloak); an external IdP's client secret comes from that IdP
    "KEYCLOAK_DB_PASSWORD": pw,
    "KC_BOOTSTRAP_ADMIN_PASSWORD": pw,
    "KEYCLOAK_ADMIN_PASSWORD": pw,
    "KEYCLOAK_CONFIGURATOR_CLIENT_SECRET": pw,
    "OIDC_CLIENT_SECRET": pw,
    "KEYCLOAK_DEMO_PASSWORD": pw,
    "KEYCLOAK_DEMO_USERNAME": lambda: "demo-launcher-" + secrets.token_hex(6),
    "KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET": pw,
}
BUILTIN_S3 = {
    "S3_ACCESS_KEY_ID": lambda: "ivapp" + secrets.token_hex(8),
    "S3_SECRET_ACCESS_KEY": pw,
    "S3_ADMIN_ACCESS_KEY_ID": lambda: "ivadmin" + secrets.token_hex(8),
    "S3_ADMIN_SECRET_ACCESS_KEY": pw,
}


def _value(line: str) -> str:
    return line.split("=", 1)[1].strip().strip('"').strip("'")


def fill(path: Path) -> tuple[list[str], list[str]]:
    lines = path.read_text().splitlines()
    current = {}
    for ln in lines:
        s = ln.strip()
        if s and not s.startswith("#") and "=" in s:
            current[s.split("=", 1)[0].strip()] = _value(s)
    gens = dict(BASE)
    if current.get("STORAGE_DRIVER") == "s3" and not current.get("S3_ENDPOINT_URL"):
        gens.update(BUILTIN_S3)
    if current.get("AUTH_DOMAIN"):
        gens.update(KEYCLOAK)
    filled, kept = [], []
    out = []
    for ln in lines:
        s = ln.strip()
        key = s.split("=", 1)[0].strip() if "=" in s and not s.startswith("#") else ""
        if key in gens and not _value(s) and key not in filled:
            out.append(f"{key}={gens[key]()}")
            filled.append(key)
            continue
        if key in gens and _value(s):
            kept.append(key)
        out.append(ln)
    missing = [k for k in gens if k not in current]
    if missing:
        out.append("# added by scripts/gen_env_secrets.py")
        for k in missing:
            out.append(f"{k}={gens[k]()}")
            filled.append(k)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(out) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    return filled, sorted(set(kept))


if __name__ == "__main__":
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_file():
        sys.exit("usage: python3 scripts/gen_env_secrets.py <env-file>   (the file must exist – create it first, e.g.\n"
                 "  cp deploy/digitalocean/env.production.template deploy/digitalocean/.env.production)")
    f, k = fill(Path(sys.argv[1]))
    print(f"gen_env_secrets: {sys.argv[1]} (mode 600)")
    print("  generated: " + (", ".join(f) or "nothing – every secret already had a value"))
    if k:
        print("  kept existing: " + ", ".join(k))
    print("  next: edit APP_DOMAIN / FRONTEND_URL / CORS_ORIGINS / OIDC_* if needed, then: python3 scripts/check_env.py " + sys.argv[1])
