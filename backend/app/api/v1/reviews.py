import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1.records import get_system, to_dict, visible_systems
from app.db import get_db
from app.models import (ApprovalDecision, ApprovalRequest, Asset, ControlAssignment, DecisionRule, Evidence, Finding, FindingControlMap,
                        FindingObservation, IngestRun, Notification, Poam, PoamFinding, System, User)
from app.security.deps import CurrentUser, enforce, get_current_user
from app.services import workflow as wf
from app.services.people import attach

router = APIRouter(tags=["reviews"])


def _req_out(db, r: ApprovalRequest) -> dict:
    sys_ = db.get(System, r.system_id)
    requester = db.get(User, r.requester_id)
    poam = db.get(Poam, r.poam_id) if r.poam_id else None
    f = db.get(Finding, r.finding_id) if r.finding_id else None
    rule = db.get(DecisionRule, r.decision_rule_id)
    return {**to_dict(r), "type_label": wf.REQUEST_TYPES.get(r.request_type, r.request_type), "system_acronym": sys_.acronym,
            "system_name": sys_.name, "requester_email": requester.email, "requester_name": requester.display_name,
            "poam_human_id": poam.human_id if poam else None, "finding_title": f.title if f else None,
            "rule_label": rule.label, "steps": rule.steps}


@router.get("/reviews")
def list_reviews(request: Request, role: str | None = None, status: str = "pending", mine: bool = False, db: Session = Depends(get_db),
                 current: CurrentUser = Depends(get_current_user)) -> dict:
    ids = [s.id for s in visible_systems(db, current)]
    q = select(ApprovalRequest).where(ApprovalRequest.system_id.in_(ids))
    if mine:
        q = q.where(ApprovalRequest.requester_id == current.user.id)
    elif status != "all":
        q = q.where(ApprovalRequest.status == status)
    if role:
        q = q.where(ApprovalRequest.assigned_role == role)
    counts = dict(db.execute(select(ApprovalRequest.assigned_role, func.count()).where(ApprovalRequest.system_id.in_(ids), ApprovalRequest.status == "pending")
                             .group_by(ApprovalRequest.assigned_role)).all())
    items = [_req_out(db, r) for r in db.scalars(q.order_by(ApprovalRequest.created_at.desc()).limit(200))]
    return {"items": items, "counts": {k: counts.get(k, 0) for k in ("issm", "sca", "ao")}}


@router.get("/reviews/{request_id}")
def review_detail(request_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    r = db.get(ApprovalRequest, request_id)
    if r is None:
        raise HTTPException(404, "Request not found")
    enforce(request, current, "system.read", r.system_id)
    ev = [{"id": str(e.id), "name": e.name, "sha256": e.sha256, "state": e.state}
          for e in db.scalars(select(Evidence).where(Evidence.id.in_([uuid.UUID(x) for x in r.evidence_ids or []])))]
    rule = db.get(DecisionRule, r.decision_rule_id)
    step = rule.steps[r.current_step] if r.status == "pending" else None
    can = bool(step) and r.requester_id != current.user.id and any(
        a.role == step["role"] and a.scope_id in (r.system_id, current.user.org_id) for a in current.assignments)
    impl = None
    if r.implementation_id:
        from app.models import Implementation

        i = db.get(Implementation, r.implementation_id)
        impl = to_dict(i)
    return {"request": _req_out(db, r), "evidence": ev, "implementation": impl,
            "decisions": attach(db, [to_dict(d) for d in db.scalars(select(ApprovalDecision).where(ApprovalDecision.request_id == r.id).order_by(ApprovalDecision.created_at))], "decider_id", "decider"),
            "can_decide": can, "current_step": step, "is_requester": r.requester_id == current.user.id, "signature_label": wf.SIGNATURE}


class DecisionIn(BaseModel):
    action: str = Field(pattern="^(approve|reject|return|request_evidence|endorse|escalate)$")
    rationale: str = Field(default="", max_length=5000)


@router.post("/reviews/{request_id}/decisions")
def decide(request_id: uuid.UUID, body: DecisionIn, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    r = wf.decide(db, request_id, current.user, current.assignments, body.action, body.rationale)
    db.commit()
    return _req_out(db, r)


@router.get("/decision-rules")
def decision_rules(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return [{**to_dict(r), "type_label": wf.REQUEST_TYPES.get(r.request_type, r.request_type)} for r in db.scalars(
        select(DecisionRule).where(DecisionRule.org_id == current.user.org_id, DecisionRule.is_active.is_(True)).order_by(DecisionRule.request_type))]


class FalsePositiveIn(BaseModel):
    justification: str = Field(min_length=10, max_length=5000)
    evidence_ids: list[str] = []


@router.post("/findings/{finding_id}/request-false-positive", status_code=201)
def request_fp(finding_id: uuid.UUID, body: FalsePositiveIn, request: Request, db: Session = Depends(get_db),
               current: CurrentUser = Depends(get_current_user)) -> dict:
    f = db.get(Finding, finding_id)
    if f is None:
        raise HTTPException(404, "Finding not found")
    enforce(request, current, "finding.map", f.system_id)
    if db.scalar(select(ApprovalRequest.id).where(ApprovalRequest.finding_id == f.id, ApprovalRequest.status == "pending")):
        raise HTTPException(409, "A pending request already exists for this finding")
    ctl = wf.finding_controls(db, f)
    req = wf.create_request(db, system=get_system(db, f.system_id), requester=current.user, request_type="false_positive",
                            justification=body.justification, finding_id=f.id, control_id=ctl[0] if ctl else None,
                            evidence_ids=wf.evidence_in_system(db, f.system_id, body.evidence_ids) or ([str(f.latest_evidence_id)] if f.latest_evidence_id else []))
    db.commit()
    return to_dict(req)


@router.get("/findings/{finding_id}")
def finding_detail(finding_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    f = db.get(Finding, finding_id)
    if f is None:
        raise HTTPException(404, "Finding not found")
    enforce(request, current, "system.read", f.system_id)
    asset = db.get(Asset, f.asset_id) if f.asset_id else None
    obs = db.execute(select(FindingObservation, IngestRun.file_name).join(IngestRun, IngestRun.id == FindingObservation.ingest_run_id)
                     .where(FindingObservation.finding_id == f.id).order_by(FindingObservation.observed_at.desc())).all()
    ev_ids = {o.evidence_id for o, _ in obs if o.evidence_id}
    maps = list(db.scalars(select(FindingControlMap).where(FindingControlMap.finding_id == f.id)))
    assigned = set(db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == f.system_id)))
    return {"finding": to_dict(f, ("dedup_fields",)), "asset": to_dict(asset) if asset else None,
            "controls": group_mappings(maps, assigned),
            "observations": [{**to_dict(o, ("raw",)), "file_name": fn} for o, fn in obs],
            "evidence": [{"id": str(e.id), "name": e.name, "sha256": e.sha256, "state": e.state, "collected_at": e.collected_at}
                         for e in db.scalars(select(Evidence).where(Evidence.id.in_(ev_ids)))],
            "poams": [{"id": str(p.id), "human_id": p.human_id, "status": wf.display_status(p), "weakness": p.weakness}
                      for p in db.scalars(select(Poam).join(PoamFinding, PoamFinding.poam_id == Poam.id).where(PoamFinding.finding_id == f.id))],
            "reviews": [_req_out(db, r) for r in db.scalars(select(ApprovalRequest).where(
                (ApprovalRequest.finding_id == f.id) | ApprovalRequest.poam_id.in_(select(PoamFinding.poam_id).where(PoamFinding.finding_id == f.id))))]}


def group_mappings(maps: list, assigned: set | None = None) -> list[dict]:
    """One row per control; CCIs and provenance listed under it (no repeated control rows)."""
    out: dict[str, dict] = {}
    for m in maps:
        g = out.setdefault(m.control_id, {"control_id": m.control_id, "ccis": [], "sources": [], "review_status": m.review_status,
                                          "confidence": m.confidence, "assigned": assigned is None or m.control_id in assigned})
        if m.cci_id and m.cci_id not in g["ccis"]:
            g["ccis"].append(m.cci_id)
        if m.source and m.source not in g["sources"]:
            g["sources"].append(m.source)
    return sorted(out.values(), key=lambda x: x["control_id"])


@router.get("/notifications")
def notifications(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    q = select(Notification).where(Notification.user_id == current.user.id)
    unread = db.scalar(select(func.count()).select_from(Notification).where(Notification.user_id == current.user.id, Notification.read_at.is_(None)))
    return {"unread": unread, "items": [to_dict(n) for n in db.scalars(q.order_by(Notification.created_at.desc()).limit(30))]}


@router.post("/notifications/{notification_id}/ack")
def ack(notification_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    n = db.get(Notification, notification_id)
    if n is None or n.user_id != current.user.id:
        raise HTTPException(404, "Notification not found")
    n.read_at = n.read_at or datetime.now(timezone.utc)
    db.commit()
    return {"ok": True}


_ = date
