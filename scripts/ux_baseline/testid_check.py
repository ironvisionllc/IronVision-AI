#!/usr/bin/env python3
"""COMPAT.md testid guard: every data-testid referenced by tests and scripts must still exist in frontend/src (static or as a template prefix).
Run: python3 scripts/ux_baseline/testid_check.py  (exit 1 on a missing testid)"""
import re
import sys
from pathlib import Path

ROOT = Path("/app")
SRC = "\n".join(p.read_text(errors="ignore") for p in (ROOT / "frontend/src").rglob("*.tsx") if not p.name.endswith(".test.tsx"))
static = set(re.findall(r'data-testid="([^"]+)"', SRC)) | set(re.findall(r'testId="([^"]+)"', SRC)) | set(re.findall(r'testId=\{?"([^"]+)"', SRC))
prefixes = {m for m in re.findall(r'data-testid=\{`([^`$]+)\$\{', SRC)} | {m for m in re.findall(r'testId=\{`([^`$]+)\$\{', SRC)}
refs = set()
for p in list((ROOT / "scripts").rglob("*.py")) + list((ROOT / "frontend/src").rglob("*.test.tsx")) + list((ROOT / "tests").rglob("*.py")):
    t = p.read_text(errors="ignore")
    refs |= set(re.findall(r"\[data-testid=['\"]?([a-z0-9][a-z0-9-]+)['\"]?\]", t)) | set(re.findall(r'data-testid="([a-z0-9][a-z0-9-]+)"', t))
    refs |= set(re.findall(r"getByTestId\([\"']([^\"']+)", p.read_text(errors="ignore")))
missing = sorted(r for r in refs if r not in static and not any(r.startswith(x) or x.startswith(r) for x in prefixes))
print(f"{len(refs)} referenced testids, {len(missing)} missing")
for m in missing:
    print("MISSING", m)
sys.exit(1 if missing else 0)
