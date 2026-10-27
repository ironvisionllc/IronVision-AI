#!/usr/bin/env python3
"""Show what a user sees for one analysed policy: control maps (review items), coverage per control, gaps and policy findings.
Usage: python scripts/perf/inspect_policy.py <policy-id> [--json out.json]"""
import json
import re
import sys
import uuid
from collections import Counter, defaultdict

sys.path.insert(0, "/app/backend")
from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Policy, PolicyControlMap, PolicyFinding, PolicyRequirementCoverage  # noqa: E402

REMOTE = re.compile(r"\bremote\b|\bac-17\b|\bvpn\b|telework", re.I)


def main() -> None:
    pid = uuid.UUID(sys.argv[1])
    with SessionLocal() as db:
        pol = db.get(Policy, pid)
        maps = db.scalars(select(PolicyControlMap).where(PolicyControlMap.policy_id == pid, PolicyControlMap.valid_to.is_(None))).all()
        cov = db.scalars(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id == pid)).all()
        fnd = db.scalars(select(PolicyFinding).where(PolicyFinding.policy_id == pid)).all()
        out = {
            "policy": {"id": str(pid), "version": pol.version, "analysis_status": pol.analysis_status, "chars": len(pol.text_content or "")},
            "maps": sorted([{"control": m.control_id, "status": m.status, "source": m.source, "confidence": m.confidence,
                             "basis": (m.basis or "")[:160], "quote": (lambda s: (s.get("text") if isinstance(s, dict) else str(s)) or "")((m.snippets or [""])[0])[:160],
                             "review_flag": m.review_flag} for m in maps], key=lambda x: x["control"]),
            "coverage_by_control": {}, "gaps": [], "findings": [],
        }
        by = defaultdict(Counter)
        for c in cov:
            by[c.control_id][c.status] += 1
            if c.status in ("missing", "partial"):
                out["gaps"].append({"control": c.control_id, "req": c.requirement_id, "status": c.status, "reason": c.reason[:240],
                                    "needs": c.needs if hasattr(c, "needs") else None})
        out["coverage_by_control"] = {k: dict(v) for k, v in sorted(by.items())}
        out["findings"] = [{"type": f.finding_type, "control": f.control_id, "status": f.status, "description": f.description[:300],
                            "quote": (f.quote or "")[:160]} for f in fnd]
        blob = json.dumps(out, default=str)
        out["summary"] = {
            "review_items_maps_proposed": sum(1 for m in maps if m.status == "proposed"),
            "maps_total": len(maps), "policy_findings": len(fnd), "coverage_rows": len(cov),
            "gap_rows": len(out["gaps"]), "controls_mapped": sorted({m.control_id for m in maps}),
            "ac17_or_remote_mentions": [m.group(0) for m in REMOTE.finditer(blob)][:20],
            "ra5": out["coverage_by_control"].get("ra-5"),
        }
    if "--json" in sys.argv:
        open(sys.argv[sys.argv.index("--json") + 1], "w").write(json.dumps(out, indent=1, default=str))
    print(json.dumps(out["summary"], default=str))


if __name__ == "__main__":
    main()
