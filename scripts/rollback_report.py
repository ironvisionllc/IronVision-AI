#!/usr/bin/env python3
"""recover.sh rollback: steps file (TSV step/status/detail) → rollback-<ts>.json + .md (mode 600)."""
import json
import os
import sys


def main(steps: str, ts: str, out_json: str, out_md: str) -> int:
    rows = [dict(zip(("step", "status", "detail"), line.rstrip("\n").split("\t"), strict=False)) for line in open(steps)]
    body = {"ts": ts, "steps": rows, "passed": all(r["status"] != "FAIL" for r in rows)}
    md = [f"# Rollback {ts}", "", "| step | status | detail |", "|---|---|---|"] + [f"| {r['step']} | {r['status']} | {r.get('detail', '')} |" for r in rows]
    for path, text in ((out_json, json.dumps(body, indent=1)), (out_md, "\n".join(md) + "\n")):
        with open(path, "w") as f:
            f.write(text)
        os.chmod(path, 0o600)
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:5]))
