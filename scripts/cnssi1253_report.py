#!/usr/bin/env python3
"""CNSSI 1253 Appendix D data checks: catalog normalisation flags (written back to the JSON), per-level counts and an
information-only comparison with NIST SP 800-53B baselines. Run inside the backend environment: python3 scripts/cnssi1253_report.py"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Control  # noqa: E402
from app.services import cnssi1253  # noqa: E402
from app.services.content.loader import active_catalog_id  # noqa: E402
from app.services.systems import baseline_control_ids  # noqa: E402

with SessionLocal() as db:
    cat = {c.control_id: c for c in db.scalars(select(Control).where(Control.catalog_version_id == active_catalog_id(db)))}
    nist = {k: set(baseline_control_ids(db, k)) for k in ("low", "moderate", "high", "privacy")}
d = json.loads(cnssi1253.PATH.read_text())
rows = d["rows"]
for r in rows:
    r.pop("not_in_catalog", None)
    if r["control_id"] not in cat:
        r["not_in_catalog"] = True
wd_mismatch = [r["id"] for r in rows if r["control_id"] in cat and r["withdrawn"] != cat[r["control_id"]].is_withdrawn]
d["catalog_check"] = {"rows": len(rows), "in_catalog": sum(1 for r in rows if r["control_id"] in cat), "not_in_catalog": [r["id"] for r in rows if r.get("not_in_catalog")],
                      "catalog_not_in_tables": sorted(c for c in cat if c not in {r["control_id"] for r in rows}),
                      "withdrawn_mismatch": wd_mismatch}
cnssi1253.PATH.write_text(json.dumps(d, indent=1, ensure_ascii=False) + "\n")
cnssi1253.data.cache_clear()
counts = {}
for o in "cia":
    for lv, name in (("l", "low"), ("m", "moderate"), ("h", "high")):
        sel = {r["control_id"] for r in rows if not r["withdrawn"] and r["marks"][f"{o}_{lv}"] in ("X", "+")}
        counts[f"{o.upper()}-{lv.upper()}"] = {"selected": len(sel), "X": sum(1 for r in rows if r["marks"][f"{o}_{lv}"] == "X"),
                                               "+": sum(1 for r in rows if r["marks"][f"{o}_{lv}"] == "+")}
print(json.dumps({"catalog_check": {k: (v if not isinstance(v, list) or len(v) < 15 else f"{len(v)} ids") for k, v in d["catalog_check"].items()},
                  "per_level": counts, "privacy_control_baseline": sum(1 for r in rows if r["privacy_baseline"] in ("X", "+")),
                  "withdrawn_rows": sum(r["withdrawn"] for r in rows)}, indent=1))
print("\nComparison with NIST SP 800-53B (information only):")
for tri, key in (("L-L-L", "low"), ("M-M-M", "moderate"), ("H-H-H", "high")):
    s = cnssi1253.selection(tri)
    sec = s["by"]["c"] | s["by"]["i"] | s["by"]["a"]
    n = nist[key]
    print(f" {tri}: CNSSI security union {len(sec)}, NIST {key} {len(n)}, NIST in CNSSI {len(n & sec)} ({100 * len(n & sec) / len(n):.1f}%), "
          f"NIST-only {len(n - sec)} {sorted(n - sec)[:12]}, CNSSI-only {len(sec - n)}")
    xs = {r["control_id"] for r in rows if not r["withdrawn"] and any(r["marks"][f"{o}_{key[0]}"] == "X" for o in "cia")}
    print(f"        rows marked X (NIST 800-53B applicability) at {key}: {len(xs)}; X but not in NIST {key}: {sorted(xs - n)[:12]}; NIST {key} without X: {len(n - xs)} {sorted(n - xs)[:12]}")
pv = {r["control_id"] for r in rows if r["privacy_baseline"] in ("X", "+")}
print(f" privacy: CNSSI privacy control baseline {len(pv)}, NIST privacy {len(nist['privacy'])}, overlap {len(pv & nist['privacy'])}, "
      f"NIST-only {sorted(nist['privacy'] - pv)[:15]}, CNSSI-only {sorted(pv - nist['privacy'])[:15]}")
dash = [r["id"] for r in rows if "--" in r["marks"].values() or r["privacy_baseline"] == "--"]
print(f" rows with '--' (NIST-selected, not NSS-selected): {len(dash)} {dash[:20]}")
