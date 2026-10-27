"""Item 4: review.bulk has its own worker lane (never behind policy/AI analysis); policy analysis records per-stage timing and runs AI calls concurrently."""
import time
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.db import SessionLocal
from app.models import Job
from tests.test_sandbox import signup_on  # noqa: F401


def test_claim_query_separates_interactive_lane():
    import worker.main as w
    old = datetime(2000, 1, 1, tzinfo=timezone.utc)
    ids = {"policy.analyze": uuid.uuid4(), "review.bulk": uuid.uuid4()}
    with SessionLocal() as db:
        for i, (t, jid) in enumerate(ids.items()):  # the analysis job is older (FIFO would pick it first)
            db.add(Job(id=jid, job_type=t, payload={}, status="queued", created_at=old + timedelta(seconds=i), run_after=old))
        db.commit()
    try:
        with SessionLocal() as db:
            fast = db.scalar(w.CLAIM_SQL, {"worker": "t:fast", "fast": w.FAST_LANE, "fast_lane": True})
            slow = db.scalar(w.CLAIM_SQL, {"worker": "t", "fast": w.FAST_LANE, "fast_lane": False})
            db.rollback()
        assert fast == ids["review.bulk"], "bulk decisions are claimed even while an older analysis job is queued"
        assert slow == ids["policy.analyze"], "the normal lane never takes review.bulk"
    finally:
        with SessionLocal() as db:
            db.execute(delete(Job).where(Job.id.in_(list(ids.values()))))
            db.commit()


def test_policy_analysis_ai_stage_concurrent_and_timing_recorded(client, signup_on, monkeypatch):  # noqa: F811
    from pathlib import Path

    from sqlalchemy import select

    from app.models import ControlAssignment, Policy, PolicyControlMap, System
    from app.services import policy_coverage as pc
    from tests.conftest import auth
    from tests.test_sandbox import _signup
    t = _signup(client, f"l4-{uuid.uuid4().hex[:6]}@example.com", "Lanes Org")
    sid = client.post("/api/v1/systems", json={"name": "Lanes", "acronym": f"LN{uuid.uuid4().hex[:3]}", "baseline_key": "moderate",
                                                "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]},
                      headers=auth(t["access_token"])).json()["id"]
    calls = []

    def slow_refine(text, cid, reqs, results, org_id):
        calls.append(cid)
        time.sleep(0.3)
        return {}
    monkeypatch.setattr(pc, "ai_refine", slow_refine)
    text = (Path(__file__).resolve().parents[2] / "samples/policies/access_control_policy.txt").read_text()
    with SessionLocal() as db:
        s = db.get(System, uuid.UUID(sid))
        ac = sorted(c for c in db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == s.id))
                    if c.startswith("ac-") and not pc.is_xx1(c))[:8]
        p = Policy(org_id=s.org_id, policy_key="SYN-L4", title="SYNTHETIC AC policy", version=1, status="current", text_content=text, analysis_status="analyzed")
        db.add(p)
        db.flush()
        for c in ac:
            db.add(PolicyControlMap(policy_id=p.id, org_id=s.org_id, control_id=c, status="mapped", source="statement_language",
                                    confidence="High", basis="SYNTHETIC", snippets=["SYNTHETIC"]))
        db.flush()
        pc.analyze(db, p, use_ai=True)
        tm = p.analysis["timing_s"]
        db.rollback()
    assert len(calls) == len(ac) == tm["ai_controls"] == 8 and tm["ai_workers"] == pc.AI_WORKERS
    assert tm["ai"] < 8 * 0.3 * 0.6, f"AI calls ran concurrently ({tm})"
    print("analysis timing", tm)
