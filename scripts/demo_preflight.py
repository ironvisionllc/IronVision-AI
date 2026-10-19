#!/usr/bin/env python3
"""Read-only preflight for ./deploy.sh --demo-without-recovery (never writes, never prints secrets).
Usage: python3 scripts/demo_preflight.py ENV_FILE [--recovery-dir DIR]
Reads the same switch records recover.sh uses (RDIR/env-switch-*.json; rolled back = *.rolled-back.json).
Exit: 0 ok · 2 usage · 20 un-rolled-back cutover switch · 21 env not on the original database · 22 env differs from pre-cutover backup."""
import json
import subprocess
import sys
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECOVERY_PREFIXES = ("rec_target_", "rec_", "ironvision_recovered", "ironvision_restored", "recovery_")


def envget(path: Path, key: str) -> str:
    return subprocess.run([sys.executable, str(HERE / "envget.py"), str(path), key], capture_output=True, text=True).stdout.strip()


def dbname(url: str) -> str:
    return urllib.parse.urlsplit(url).path.lstrip("/").split("?")[0]


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    rdir = Path("/root/ironvision-recovery")
    if "--recovery-dir" in argv:
        rdir = Path(argv[argv.index("--recovery-dir") + 1])
        args.remove(str(rdir))
    if len(args) != 1 or not Path(args[0]).is_file():
        print(__doc__.split("\n")[1], file=sys.stderr)
        return 2
    env = Path(args[0])
    print(f"preflight: recovery dir {rdir} (read-only; nothing in it is changed)")

    pending = sorted(p for p in rdir.glob("env-switch-*.json") if "rolled-back" not in p.name) if rdir.is_dir() else []
    if pending:
        j = json.loads(pending[-1].read_text())
        print(f"REFUSED: cutover switch {pending[-1].name} ({j.get('previous_db')} → {j.get('new_db')}) is NOT rolled back.\n"
              "  This command never rolls back or switches by itself. Run it manually first:\n"
              "    sudo ./recover.sh rollback\n  then re-run: sudo ./deploy.sh --demo-without-recovery", file=sys.stderr)
        return 20
    print("preflight: OK no un-rolled-back DATABASE_URL switch")

    expected = envget(env, "POSTGRES_DB") or "ironvision"
    url = envget(env, "DATABASE_URL")
    db = dbname(url) if url else expected
    if db != expected or db.startswith(RECOVERY_PREFIXES) or expected.startswith(RECOVERY_PREFIXES):
        print(f"REFUSED: the env file points the app at database '{db}' (expected the original '{expected}').\n"
              "  A recovery target must never be served by this path. Restore the pre-cutover env with: sudo ./recover.sh rollback",
              file=sys.stderr)
        return 21
    print(f"preflight: OK env uses the original database '{db}'{' (DATABASE_URL)' if url else ' (derived from POSTGRES_DB)'}")

    done = sorted(rdir.glob("env-switch-*.rolled-back.json")) if rdir.is_dir() else []
    if done:
        bk = Path(json.loads(done[-1].read_text()).get("env_backup") or "")
        if bk.is_file():
            bdb = dbname(envget(bk, "DATABASE_URL")) or (envget(bk, "POSTGRES_DB") or "ironvision")
            if bdb != db:
                print(f"REFUSED: pre-cutover env backup {bk} uses database '{bdb}', the env file uses '{db}'.", file=sys.stderr)
                return 22
            print(f"preflight: OK database matches the pre-cutover env backup {bk}")
        else:
            print(f"preflight: NOTE pre-cutover env backup {bk} not found – database check above still applies")
    else:
        print("preflight: no pre-cutover env backup recorded (no switch was ever made)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
