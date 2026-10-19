#!/usr/bin/env python3
"""Verify a scripts/backup.sh directory: manifest present, every artifact matches its SHA-256, db.dump is a pg_dump custom
archive whose table of contents pg_restore can read (when pg_restore is on PATH or in PG_BIN).
Usage: python3 scripts/verify_backup.py BACKUP_DIR   → exit 0 verified · 1 not verified"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__.split("\n")[2], file=sys.stderr)
        return 1
    out = Path(argv[0])
    m = out / "manifest.json"
    if not m.is_file():
        print(f"verify_backup: FAIL {m} missing", file=sys.stderr)
        return 1
    man = json.loads(m.read_text())
    arts = man.get("artifacts") or {}
    if "db.dump" not in arts:
        print("verify_backup: FAIL manifest lists no db.dump", file=sys.stderr)
        return 1
    for name, a in arts.items():
        p = out / name
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != a["sha256"]:
            print(f"verify_backup: FAIL {name} missing or SHA-256 mismatch", file=sys.stderr)
            return 1
    dump = out / "db.dump"
    if dump.read_bytes()[:5] != b"PGDMP":
        print("verify_backup: FAIL db.dump is not a pg_dump custom archive", file=sys.stderr)
        return 1
    pr = shutil.which("pg_restore", path=os.environ.get("PG_BIN") or None) or shutil.which("pg_restore")
    toc = "pg_restore not installed – TOC not listed"
    if pr:
        r = subprocess.run([pr, "--list", str(dump)], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"verify_backup: FAIL pg_restore --list: {r.stderr.strip()[:300]}", file=sys.stderr)
            return 1
        toc = f"pg_restore TOC {sum(1 for ln in r.stdout.splitlines() if ln and not ln.startswith(';'))} entries"
    print(f"verify_backup: OK {out} – {len(arts)} artifact(s) SHA-256 verified, {toc}, alembic {man.get('alembic_revision')}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
