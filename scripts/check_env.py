#!/usr/bin/env python3
"""Validates a deployment env file (or the current environment) before `docker compose up`.
Usage: python3 scripts/check_env.py deploy/digitalocean/.env.production [--local] [--fix]   (exit 1 on errors)
  --local  skip deployment-only requirements (APP_DOMAIN)
  --fix    rewrite the file safely first: quote values with spaces/shell characters, drop `export `, CRLF → LF,
           strip trailing spaces, comment out duplicate keys. A timestamped backup (mode 600) is written next to it.
Syntax problems (unquoted spaces/metacharacters, unbalanced quotes, export, CRLF, trailing spaces, duplicates, invalid
names) are errors in staging/production and warnings otherwise. Secret values are never printed."""
import os
import shutil
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from app.check_env import validate  # noqa: E402
from app.envfile import fix_env_text, lint_env_text, parse_env_text  # noqa: E402

SECRETISH = ("SECRET", "PASSWORD", "KEY", "TOKEN")


def redact(text: str | None) -> str | None:
    if text and "=" in text and any(s in text.split("=", 1)[0] for s in SECRETISH):
        return text.split("=", 1)[0] + "=<quoted value>"
    return text


def fix(path: Path) -> None:
    text = path.read_text()
    new, changes, unfixable = fix_env_text(text)
    for u in unfixable:
        print(f"  MANUAL {u}")
    if new == text:
        print(f"check_env --fix: {path} needs no changes")
        return
    backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup)
    os.chmod(backup, 0o600)
    tmp = path.with_name(path.name + ".fixtmp")
    tmp.write_text(new)
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    print(f"check_env --fix: rewrote {path} (mode 600), backup {backup}")
    for c in changes:
        print(f"  FIXED {c}")


args = [a for a in sys.argv[1:] if not a.startswith("--")]
if "--fix" in sys.argv:
    if not args:
        sys.exit("--fix needs an env file path")
    fix(Path(args[0]))
text = Path(args[0]).read_text() if args else None
env = parse_env_text(text) if text is not None else dict(os.environ)
profile = env.get("APP_ENV", "development")
errors, warns = validate(env, deployed="--local" not in sys.argv)
lint = lint_env_text(text) if text is not None else []
syntax = [f"line {i['line']}: {i['message']}" + (f"  → fix: {redact(i['suggestion'])}" if i["suggestion"] else "") for i in lint]
if syntax:
    (errors if profile in ("staging", "production") else warns).extend(
        syntax + [f"run: python3 scripts/check_env.py --fix {args[0]}"])
print(f"check_env: profile={profile} source={args[0] if args else 'process env'}")
for w in warns:
    print(f"  WARN  {w}")
for e in errors:
    print(f"  ERROR {e}")
print("RESULT:", "FAIL" if errors else "PASS", f"({len(errors)} errors, {len(warns)} warnings)")
sys.exit(1 if errors else 0)
