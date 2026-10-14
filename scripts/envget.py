#!/usr/bin/env python3
"""Print ONE value from an env file without sourcing or evaluating it (same parsing as Docker Compose / check_env).
Usage: python3 scripts/envget.py deploy/digitalocean/.env.production APP_DOMAIN      (missing key → empty output)
Shell:  APP_DOMAIN="$(python3 scripts/envget.py "$F" APP_DOMAIN)"     – never `. "$F"` / `source "$F"`."""
import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("envfile", Path(__file__).resolve().parent.parent / "backend" / "app" / "envfile.py")
envfile = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(envfile)

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("usage: python3 scripts/envget.py <env-file> <KEY>")
    path = Path(sys.argv[1])
    if not path.is_file():
        sys.exit(f"envget: env file not found: {path}")
    sys.stdout.write(envfile.parse_env_file(path).get(sys.argv[2], ""))
