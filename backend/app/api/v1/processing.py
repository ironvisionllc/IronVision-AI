"""Processing state of every upload (scan/checklist ingest runs and policies): Processing… / Analysed / Failed (reason), a plain
summary when done, and an idempotent Retry. The UI polls this while anything is processing and refreshes every screen when it ends."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.records import get_system
from app.db import get_db
from app.models import Finding, FindingControlMap, FindingObservation, IngestRun, Policy, PolicyControlMap
from app.security.deps import CurrentUser, require_permission
from app.services import audit
from app.services import jobs

router = APIRouter(tags=["processing"])
STATE = {"received": "queued", "queued": "queued", "processing": "processing", "completed": "analysed", "duplicate": "analysed",
         "failed": "failed", "analyzed": "analysed"}


def _run_item(db: Session, r: IngestRun) -> dict:
    st = STATE.get(r.status, r.status)
    summary = None
    if st == "analysed":
        open_n = db.scalar(select(func.count(func.distinct(Finding.id))).join(FindingObservation, FindingObservation.finding_id == Finding.id)
                           .where(FindingObservation.ingest_run_id == r.id, Finding.current_state == "open")) or 0
        review = db.scalar(select(func.count(FindingControlMap.id)).join(Finding, Finding.id == FindingControlMap.finding_id).where(
            Finding.system_id == r.system_id, FindingControlMap.review_status == "pending")) or 0
        summary = {"rules_parsed": r.total or 0, "mapped": r.mapped or 0, "unmapped": r.unmapped or 0, "controls_touched": r.controls_touched or 0,
                   "open_findings": open_n, "mappings_to_review": review,
                   "text": (f"{r.total or 0} rules/results parsed, {open_n} open findings, {r.mapped or 0} mapped to controls, {r.unmapped or 0} unmapped sent to Mapping Review, "
                            f"{r.controls_touched or 0} controls updated" if r.status != "duplicate" else "Identical file already processed – not double-counted")}
    return {"kind": "ingest", "id": str(r.id), "file_name": r.file_name, "format": r.file_format, "state": st, "raw_status": r.status,
            "reason": "; ".join(r.errors or []) or None if st == "failed" else None, "summary": summary,
            "at": (r.finished_at or r.received_at).isoformat() if (r.finished_at or r.received_at) else None}


def _policy_item(db: Session, p: Policy) -> dict:
    from app.services import policy_coverage as pc

    st = STATE.get(p.analysis_status, p.analysis_status)
    summary = None
    if st == "analysed":
        maps = list(db.scalars(select(PolicyControlMap).where(PolicyControlMap.policy_id == p.id, PolicyControlMap.valid_to.is_(None))))
        from app.models import PolicyRequirementCoverage as PRC

        rows = list(db.scalars(select(PRC).where(PRC.policy_id == p.id)))
        s = pc.summarize(rows)
        n = len((p.text_content or "").strip())
        ctl = sorted({c.control_id for c in rows})
        summary = {"mappings": len(maps), "proposed": sum(m.status == "proposed" for m in maps), "requirements": s["total"], "met": s["met"],
                   "scope": f"policy-wide: all {len(ctl)} mapped controls and enhancements together", "controls": ctl,
                   "text": (f"{len(maps)} control mappings ({sum(m.status == 'proposed' for m in maps)} sent to Mapping Review), "
                            f"{s['met']} of {s['total']} CCI/objective requirements met across all {len(ctl)} mapped controls/enhancements (policy-wide, not per control)") if maps else
                           f"No controls found: the extracted text ({n} characters) names no NIST control, family or requirement – check that the right file was uploaded"}
    return {"kind": "policy", "id": str(p.id), "file_name": p.file_name, "title": f"{p.title} v{p.version}", "state": st, "raw_status": p.analysis_status,
            "reason": (p.analysis or {}).get("error") if st == "failed" else None, "summary": summary,
            "at": p.created_at.isoformat()}


@router.get("/systems/{system_id}/processing")
def processing(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    s = get_system(db, system_id)
    runs = list(db.scalars(select(IngestRun).where(IngestRun.system_id == s.id).order_by(IngestRun.received_at.desc()).limit(15)))
    from app.services.policy_coverage import applicable_policies

    pols = sorted(applicable_policies(db, s), key=lambda p: p.created_at, reverse=True)[:10]
    items = sorted([_run_item(db, r) for r in runs] + [_policy_item(db, p) for p in pols], key=lambda i: i["at"] or "", reverse=True)
    return {"items": items, "active": sum(i["state"] in ("queued", "processing") for i in items), "failed": sum(i["state"] == "failed" for i in items)}


@router.post("/ingest-runs/{run_id}/retry", status_code=202)
def retry_run(run_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("ingest.upload"))) -> dict:
    r = db.get(IngestRun, run_id)
    if r is None or get_system(db, r.system_id).org_id != current.user.org_id:
        raise HTTPException(404, "Upload not found")
    if r.status != "failed":
        raise HTTPException(409, f"Only failed uploads can be retried (this one is {r.status})")
    r.status = "queued"
    job = jobs.enqueue(db, "ingest.process", {"run_id": str(r.id)}, requested_by=current.user.id)
    audit.record(db, action="ingest.retried", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="ingest_run", entity_id=str(r.id),
                 details={"job_id": str(job.id)})
    db.commit()
    return {"ok": True, "job_id": str(job.id)}


@router.post("/policies/{policy_id}/reanalyze", status_code=202)
def reanalyze_policy(policy_id: uuid.UUID, latest: bool = False, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("ingest.upload"))) -> dict:
    p = db.get(Policy, policy_id)
    if p is None or p.org_id != current.user.org_id:
        raise HTTPException(404, "Policy not found")
    est = None
    if latest:  # "Re-analyze with latest" (stale / keyword-only results): ISSO or ISSM only, estimated cost recorded in the audit
        if not {"isso", "issm", "admin"} & set(current.roles):
            raise HTTPException(403, "Only the ISSO or ISSM can re-analyse a policy with the latest auditor")
        from app.services.policy_coverage import auditor_status
        est = auditor_status(db, p)
    p.analysis_status = "queued"
    job = jobs.enqueue(db, "policy.analyze", {"policy_id": str(p.id), **({"reason": "latest_auditor"} if latest else {})})
    from app.services.policy_analyzer_v2 import queued_progress
    queued_progress(db, p, job)
    audit.record(db, action="policy.reanalysis_requested", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="policy",
                 entity_id=str(p.id), details={"job_id": str(job.id), **({"latest": True, "from_version": est["used_version"], "from_analyzer": est["analyzer"],
                                                                          "est_cost_usd": est["est_cost_usd"]} if est else {})})
    db.commit()
    return {"ok": True, "job_id": str(job.id)}
