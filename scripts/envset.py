#!/usr/bin/env python3
"""Set one KEY in an env file in place (value from stdin), with a timestamped backup and mode 600. Never prints the value.

Usage: printf '%s' "$VALUE" | python3 scripts/envset.py deploy/digitalocean/.env.production KEYCLOAK_DEMO_PASSWORD
"""
import os
import re
import shutil
import sys
import time
from pathlib import Path


def quote(v: str) -> str:
    return v if re.fullmatch(r"[A-Za-z0-9_./:@+=,-]*", v) else '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def main(argv: list[str]) -> int:
    if len(argv) != 2 or not re.fullmatch(r"[A-Z][A-Z0-9_]*", argv[1]):
        print(__doc__)
        return 2
    path, key = Path(argv[0]), argv[1]
    value = sys.stdin.read().rstrip("\n")
    lines = path.read_text().splitlines()
    out, done = [], False
    for line in lines:
        if re.match(rf"^\s*{key}\s*=", line):
            out.append(f"{key}={quote(value)}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key}={quote(value)}")
    backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d%H%M%S')}")
    shutil.copy2(path, backup)
    os.chmod(backup, 0o600)
    tmp = path.with_name(path.name + ".envsettmp")
    tmp.write_text("\n".join(out) + "\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    print(f"envset: {key} updated in {path} (backup {backup})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
