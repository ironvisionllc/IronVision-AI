#!/usr/bin/env python3
"""Effective compose config audit (stdlib only; Ubuntu 24.04 host python3 3.12 compatible). Reads `docker compose config
--format json` on stdin and prints image / published ports / selected environment per service, secrets redacted.

    docker compose --env-file ENV config --format json | python3 scripts/compose_audit.py

Was an inline `python3 -c '…'` in recover_audit.sh whose \\" escapes inside an f-string broke on python3 3.12
("unexpected character after line continuation character")."""
import json
import re
import sys

KEEP = re.compile(r"DATABASE_URL|S3_ENDPOINT|S3_BUCKET|DOMAIN|OIDC_ISSUER|OIDC_REDIRECT|KEYCLOAK_URL|AUTH_PROVIDERS|DEPLOYMENT_KIND|"
                  r"ALLOW_DEMO|REGISTRATION|APP_ENV")
SECRET = re.compile(r"SECRET|PASSWORD|_KEY$|TOKEN")
USERINFO = re.compile(r"://([^:/@]+):[^@]+@")


def ports(svc: dict) -> list[str]:
    out = []
    for p in svc.get("ports") or []:
        if p.get("published"):
            out.append(f"{p.get('host_ip') or '0.0.0.0'}:{p['published']}->{p.get('target')}")
    return out


def render(cfg: dict) -> list[str]:
    lines = []
    for name, svc in sorted((cfg.get("services") or {}).items()):
        env = svc.get("environment") or {}
        if isinstance(env, list):
            env = dict(e.split("=", 1) if "=" in e else (e, "") for e in env)
        lines.append(f"  {name}: image={svc.get('image', '(build)')} ports={ports(svc)} networks={sorted(svc.get('networks') or {})}")
        for k in sorted(k for k in env if KEEP.search(k)):
            v = "***" if SECRET.search(k) else USERINFO.sub(r"://\1:***@", str(env[k]))
            lines.append(f"      {k}={v}")
    return lines


def main() -> int:
    try:
        cfg = json.load(sys.stdin)
    except ValueError as exc:
        print(f"  FAIL compose config is not valid JSON: {exc}")
        return 1
    print("\n".join(render(cfg)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
