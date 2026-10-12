#!/usr/bin/env python3
"""Validates a deployment env file (or the current environment) before `docker compose up`.
Usage: python3 scripts/check_env.py deploy/digitalocean/.env.production   [--local]   (exit 1 on errors)
--local skips deployment-only requirements (APP_DOMAIN). Secret values are never printed."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.check_env import validate  # noqa: E402


def load(path: str) -> dict:
    env = {}
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


args = [a for a in sys.argv[1:] if not a.startswith("--")]
env = load(args[0]) if args else dict(os.environ)
errors, warns = validate(env, deployed="--local" not in sys.argv)
print(f"check_env: profile={env.get('APP_ENV', 'development')} source={args[0] if args else 'process env'}")
for w in warns:
    print(f"  WARN  {w}")
for e in errors:
    print(f"  ERROR {e}")
print("RESULT:", "FAIL" if errors else "PASS", f"({len(errors)} errors, {len(warns)} warnings)")
sys.exit(1 if errors else 0)
