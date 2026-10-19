#!/usr/bin/env python3
"""Atomically set one KEY in an env file (value from stdin), or copy an env file byte-for-byte. Never prints the value.

Usage: printf '%s' "$VALUE" | python3 scripts/envset.py deploy/digitalocean/.env.production KEYCLOAK_DEMO_PASSWORD
       python3 scripts/envset.py --copy SRC DST      # byte-exact atomic copy (env backup / rollback restore), mode 600

Every write: temp file (O_EXCL, mode 600) in the same directory → fsync → rename → fsync(dir). A failure at any point leaves
the destination exactly as it was (the rename is the only step that changes it) and removes the temp file.
"""
import os
import re
import sys
import time
from pathlib import Path


def quote(v: str) -> str:
    return v if re.fullmatch(r"[A-Za-z0-9_./:@+=,-]*", v) else '"' + v.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def atomic_write(path: Path, data: bytes, fault: bool = False) -> None:
    tmp = path.with_name(f".{path.name}.envsettmp-{os.getpid()}")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, 0o600)
        if fault:
            raise OSError("injected fault before rename (ENVSET_FAULT=before-rename, RECOVER_LOCAL=1 test mode only)")
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def main(argv: list[str]) -> int:
    if len(argv) == 3 and argv[0] == "--copy":
        atomic_write(Path(argv[2]), Path(argv[1]).read_bytes())
        return 0
    if len(argv) != 2 or not re.fullmatch(r"[A-Z][A-Z0-9_]*", argv[1]):
        print(__doc__)
        return 2
    path, key = Path(argv[0]), argv[1]
    value = sys.stdin.read().rstrip("\n")
    out, done = [], False
    for line in path.read_text().splitlines():
        if re.match(rf"^\s*{key}\s*=", line):
            out.append(f"{key}={quote(value)}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key}={quote(value)}")
    backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d%H%M%S')}")
    atomic_write(backup, path.read_bytes())
    fault = os.environ.get("RECOVER_LOCAL") == "1" and os.environ.get("ENVSET_FAULT") == "before-rename"
    atomic_write(path, ("\n".join(out) + "\n").encode(), fault=fault)
    print(f"envset: {key} updated in {path} (backup {backup})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
