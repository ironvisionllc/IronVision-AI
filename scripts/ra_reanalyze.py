"""Re-analyse policies with the current analyzer and AI, bypassing the tenant AI cache (POLICY_AI_CACHE=0 is set before import).
Old per-requirement results are appended to policy.analysis["history"] first; human Mapping Review decisions are kept by the analysis.
Usage: python3 scripts/ra_reanalyze.py <policy-id> [...]"""
import os
import sys
from datetime import datetime, timezone

os.environ["POLICY_AI_CACHE"] = "0"
sys.path.insert(0, "/app/backend")
sys.path.insert(0, "/app/backend/worker")
os.chdir("/app/backend")
import uuid  # noqa: E402

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Policy, PolicyRequirementCoverage  # noqa: E402
from app.services import audit  # noqa: E402
from worker.handlers import handle_policy_analyze  # noqa: E402

for pid in sys.argv[1:]:
    db = SessionLocal()
    p = db.get(Policy, uuid.UUID(pid))
    old = db.scalars(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id == p.id)).all()
    snap = {"at": datetime.now(timezone.utc).isoformat(), "reason": "re-analysis with latest auditor (cache bypassed)",
            "analyzer": (p.analysis or {}).get("analyzer"), "coverage_version": (p.analysis or {}).get("coverage_version"),
            "rows": [{"control_id": c.control_id, "requirement_id": c.requirement_id, "status": c.status, "source": c.source, "reason": c.reason[:300]} for c in old]}
    p.analysis = {**(p.analysis or {}), "history": ((p.analysis or {}).get("history") or [])[-4:] + [snap]}
    audit.record(db, action="policy.reanalysis_requested", actor_email="system:ra-root-cause", entity_type="policy", entity_id=str(p.id),
                 details={"reason": "stale deterministic results (RA root-cause task)", "cache": "bypassed", "previous_analyzer": snap["analyzer"]})
    db.commit()
    t0 = datetime.now(timezone.utc)
    res = handle_policy_analyze(db, {"policy_id": pid, "reason": "ra_root_cause"})
    db.commit()
    p = db.get(Policy, uuid.UUID(pid))
    print(pid[:8], "done in", round((datetime.now(timezone.utc) - t0).total_seconds(), 1), "s analyzer", (p.analysis or {}).get("analyzer"), str(res)[:200], flush=True)
    db.close()
