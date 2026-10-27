"""text-3 re-extraction (DOCX tables): queued as a normal policy.analyze job (AI lane, never inline / never the bulk lane); after the job runs,
(policy, control) pairs with a human decision get no new open review item – differences show only as "differs from approved"."""
import uuid
from pathlib import Path

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Job, Organization, Policy, PolicyControlMap, System, User
from app.services import policy_mapping as pm
from app.services.rmf import TEXT_VERSION, analyze_policy, refresh_text
from app.services.storage.base import get_storage

FIX = Path(__file__).parent / "fixtures" / "policies" / "ra_policy_dod_aws_raven_demo.docx"


def _old_text(data: bytes) -> str:  # text-2 extraction: paragraphs only (tables dropped)
    import io

    import docx
    return "\n".join(p.text for p in docx.Document(io.BytesIO(data)).paragraphs)


def test_reextraction_queues_job_and_keeps_human_decisions():
    import worker.main as wm
    from worker.handlers import handle_policy_analyze
    data = FIX.read_bytes()
    with SessionLocal() as db:
        org = Organization(name="TEXT3 – SYNTHETIC", slug=f"t3-{uuid.uuid4().hex[:8]}", is_synthetic=True, is_sandbox=True)
        db.add(org)
        db.flush()
        sysm = System(id=uuid.uuid4(), org_id=org.id, name="SYNTHETIC t3")
        db.add(sysm)
        key = f"tests/{uuid.uuid4().hex}.docx"
        get_storage().put(key, data)
        pol = Policy(org_id=org.id, policy_key="T3", title="t3", version=1, status="current", text_content=_old_text(data), file_name="ra.docx",
                     storage_key=key, analysis_status="queued", system_ids=[str(sysm.id)])
        db.add(pol)
        db.flush()
        analyze_policy(db, pol)
        pol.analysis = {**pol.analysis, "text_version": "text-2"}
        actor = db.scalar(select(User).limit(1))
        pm.decide(db, pol, "ra-5", "mapped", actor, "reviewed by a human")
        pm.decide(db, pol, "ra-6", "rejected", actor, "not selected for this system")
        db.commit()
        pid = pol.id

    with SessionLocal() as db:
        pol = db.get(Policy, pid)
        before = {m.control_id: (m.id, m.status) for m in pm.current(db, pid)}
        assert refresh_text(db, pol) is True
        db.commit()
        pol = db.get(Policy, pid)
        assert pol.analysis_status == "queued" and pol.analysis["text_version"] == TEXT_VERSION
        assert pol.analysis["text_refreshed"]["reason"] == "improved table extraction"
        jobs = list(db.scalars(select(Job).where(Job.job_type == "policy.analyze", Job.payload["policy_id"].astext == str(pid))))
        assert len(jobs) == 1 and jobs[0].status == "queued"
        assert "policy.analyze" not in wm.FAST_LANE  # AI lane, never the bulk/interactive lane
        assert {m.control_id: (m.id, m.status) for m in pm.current(db, pid)} == before  # nothing analysed inline
        assert refresh_text(db, pol) is False  # idempotent: no second job
        db.commit()

    with SessionLocal() as db:
        handle_policy_analyze(db, {"policy_id": str(pid)})
        db.commit()
        cur = {m.control_id: m for m in pm.current(db, pid)}
        for c in ("ra-5", "ra-6"):
            assert cur[c].id == before[c][0] and cur[c].status == before[c][1]  # decision row untouched, no new open item
        assert not [m for m in db.scalars(select(PolicyControlMap).where(PolicyControlMap.policy_id == pid, PolicyControlMap.control_id.in_(("ra-5", "ra-6")),
                                                                          PolicyControlMap.status == "proposed", PolicyControlMap.valid_to.is_(None)))]
        assert cur["ra-5"].reanalysis and cur["ra-5"].reanalysis["label"] == "differs from approved"  # matrix row now quoted → differs
        assert db.get(Policy, pid).analysis_status == "analyzed"
