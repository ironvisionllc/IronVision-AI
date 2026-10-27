import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import Session

from app.api.v1.records import get_system, to_dict, visible_systems
from app.db import get_db
from app.models import (ApprovalRequest, Asset, ControlAssignment, EmassChange, Evidence, Finding, Poam, PoamFinding, PoamHistory, PoamMatchRule,
                        PoamMilestone, System, User)
from app.security.deps import CurrentUser, enforce, get_current_user, require_body_permission, require_object_permission
from app.services import emass
from app.services import audit
from app.services.people import attach
from app.services import workflow as wf
from app.services.evaluation import evaluate_system, take_snapshots

router = APIRouter(tags=["poams"])
SORTS = {"human_id": Poam.seq, "due_date": Poam.due_date, "severity": Poam.severity, "status": Poam.status, "created_at": Poam.created_at}


def _poam(db, request, current, poam_id: str, perm="system.read") -> Poam:
    p = db.scalar(select(Poam).where(Poam.human_id == poam_id, Poam.org_id == current.user.org_id)) if poam_id.upper().startswith("P-") \
        else db.get(Poam, uuid.UUID(poam_id))
    if p is None:
        raise HTTPException(404, "POA&M not found")
    enforce(request, current, perm, p.system_id)
    return p


def _row(db, p: Poam) -> dict:
    from app.services.queue import score_poam

    ms = list(db.scalars(select(PoamMilestone).where(PoamMilestone.poam_id == p.id)))
    owner = db.get(User, p.owner_id) if p.owner_id else None
    assets = [a for (a,) in db.execute(select(Asset.name).where(Asset.id.in_([uuid.UUID(x) for x in p.asset_ids or []])))]
    from app.services.metrics import emass_states

    em = emass_states(db, [p])[p.id]
    q = db.scalar(select(EmassChange.status).where(EmassChange.entity_type == "poam", EmassChange.entity_id == str(p.id))
                  .order_by(EmassChange.created_at.desc()).limit(1))
    return {**to_dict(p), "display_status": wf.display_status(p), "emass_queue_status": q, "emass": em,
            "emass_status": em["state"], "emass_remote_id": em["remote_id"], "system_acronym": db.get(System, p.system_id).acronym,
            "system_name": db.get(System, p.system_id).name, "risk_score": score_poam(p)[0], "risk_breakdown": score_poam(p)[1], "owner_name": owner.display_name if owner else None,
            "asset_names": assets, "milestones_done": sum(m.status == "completed" for m in ms), "milestones_total": len(ms),
            "finding_count": db.scalar(select(func.count()).select_from(PoamFinding).where(PoamFinding.poam_id == p.id))}


def summary(db, system_ids) -> dict:
    from app.services.metrics import poam_summary

    out = poam_summary(db, system_ids)
    first = db.get(System, system_ids[0]) if system_ids else None
    out["emass_note"] = emass.status(db, first.org_id)["mode_label"] if first else None
    return out


@router.get("/poams")
def list_poams(request: Request, system_id: uuid.UUID | None = None, q: str | None = None, status: str | None = None,
               severity: str | None = None, sort: str = "risk", desc: bool = False, page: int = 1, page_size: int = 25,
               db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    ids = [system_id] if system_id else [s.id for s in visible_systems(db, current)]
    if system_id:
        enforce(request, current, "system.read", system_id)
    base = select(Poam).where(Poam.system_id.in_(ids))
    if q:
        like = f"%{q}%"
        base = base.where(or_(Poam.human_id.ilike(like), Poam.weakness.ilike(like), cast(Poam.control_ids, String).ilike(like),
                              cast(Poam.vuln_ids, String).ilike(like)))
    if status == "overdue":
        base = base.where(Poam.status.in_(("new", "in_progress")), Poam.due_date < date.today())
    elif status == "open":
        base = base.where(Poam.status.in_(wf.ACTIVE_POAM))
    elif status in ("new", "in_progress"):  # filter on display_status: past-due new/in_progress show as "overdue"
        base = base.where(Poam.status == status, or_(Poam.due_date.is_(None), Poam.due_date >= date.today()))
    elif status:
        base = base.where(Poam.status == status)
    if severity:
        base = base.where(Poam.severity == severity)
    total = db.scalar(select(func.count()).select_from(base.subquery()))
    page_size, off = max(1, min(page_size, 1000)), (max(page, 1) - 1) * max(1, min(page_size, 1000))
    if sort == "risk":
        from app.services.queue import SEV_RANK, score_poam

        allp = list(db.scalars(base))
        allp.sort(key=lambda p: (-score_poam(p)[0], SEV_RANK.get(p.cat or p.severity or "", 9), p.due_date or date.max, p.seq), reverse=desc)
        items = allp[off:off + page_size]
    else:
        col = SORTS.get(sort, Poam.seq)
        items = db.scalars(base.order_by(col.desc().nulls_last() if desc else col.asc().nulls_last()).offset(off).limit(page_size))
    return {"items": [_row(db, p) for p in items], "total": total, "page": page, "page_size": page_size, "summary": summary(db, ids), "sort": sort}


RISK_RX = "^(Very Low|Low|Moderate|High|Very High)$"  # eMASS risk scale; never derived from technical severity/CAT
RISK_FIELDS = ("raw_severity", "relevance_of_threat", "likelihood", "impact", "residual_risk_level", "mitigations")


class PoamIn(BaseModel):
    weakness: str | None = Field(None, min_length=5, max_length=5000)
    security_impact: str | None = Field(None, max_length=5000)
    control_ids: list[str] | None = None
    severity: str | None = Field(None, pattern="^(critical|high|medium|low)$")
    cat: str | None = Field(None, pattern="^CAT (I|II|III)$")
    source_label: str | None = Field(None, max_length=50)
    root_cause: str | None = Field(None, max_length=5000)
    remediation_plan: str | None = Field(None, max_length=5000)
    resources: str | None = Field(None, max_length=2000)
    owner_id: uuid.UUID | None = None
    due_date: date | None = None
    status: str | None = Field(None, pattern="^(new|in_progress)$")
    raw_severity: str | None = Field(None, pattern=RISK_RX)
    relevance_of_threat: str | None = Field(None, pattern=RISK_RX)
    likelihood: str | None = Field(None, pattern=RISK_RX)
    impact: str | None = Field(None, pattern=RISK_RX)
    residual_risk_level: str | None = Field(None, pattern=RISK_RX)
    mitigations: str | None = Field(None, max_length=5000)
    comments: str | None = Field(None, max_length=5000)


class PoamCreate(PoamIn):
    system_id: uuid.UUID
    weakness: str = Field(min_length=5, max_length=5000)
    control_ids: list[str] = Field(min_length=1)
    finding_ids: list[uuid.UUID] = []
    allow_duplicate_justification: str | None = Field(None, min_length=10)


@router.post("/poams", status_code=201)
def create(body: PoamCreate, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_body_permission("poam.manage"))) -> dict:
    enforce(request, current, "poam.manage", body.system_id)
    system = get_system(db, body.system_id)
    findings = [f for f in (db.get(Finding, i) for i in body.finding_ids) if f and f.system_id == system.id]
    if len(findings) != len(body.finding_ids):
        raise HTTPException(422, "All findings must belong to the system")
    assigned = set(db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == system.id)))
    ctl = [c.lower() for c in body.control_ids]
    if missing := [c for c in ctl if c not in assigned]:
        raise HTTPException(422, f"Controls not assigned to this system: {', '.join(missing)}")
    for f in findings:
        matches, rule = wf.find_matching_poams(db, f, system.org_id)
        if matches and not body.allow_duplicate_justification:
            raise HTTPException(409, {"message": f"Finding matches open {', '.join(m.human_id for m in matches)} (match rule v{rule.version})",
                                      "matches": [{"id": str(m.id), "human_id": m.human_id, "weakness": m.weakness} for m in matches]})
    data = body.model_dump(exclude={"system_id", "finding_ids", "allow_duplicate_justification"}, exclude_none=True)
    data["control_ids"], data["status"] = ctl, data.get("status", "new")
    p = wf.create_poam(db, system=system, actor=current.user, data=data, findings=findings)
    if body.allow_duplicate_justification:
        wf.history(db, p, current.user, "duplicate_override", justification=body.allow_duplicate_justification)
    db.flush()
    take_snapshots(db, trigger="poam.created")
    db.commit()
    return _row(db, p)


@router.get("/findings/{finding_id}/poam-match")
def poam_match(finding_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    f = db.get(Finding, finding_id)
    if f is None:
        raise HTTPException(404, "Finding not found")
    enforce(request, current, "system.read", f.system_id)
    matches, rule = wf.find_matching_poams(db, f, current.user.org_id)
    asset = db.get(Asset, f.asset_id) if f.asset_id else None
    ident = f.vuln_id or f.rule_id or (f"plugin {f.plugin_id}" if f.plugin_id else "")
    prefill = {"system_id": str(f.system_id), "finding_ids": [str(f.id)], "control_ids": wf.finding_controls(db, f) or [],
               "weakness": f"{ident} {f.title}".strip() + (f" on {asset.name}" if asset else ""), "severity": f.severity, "cat": f.cat,
               "source_label": wf.source_label(f.source_type), "asset_name": asset.name if asset else None,
               "vuln_ids": [x for x in (f.vuln_id, f.rule_id, *(f.cves or [])) if x], "evidence_id": str(f.latest_evidence_id) if f.latest_evidence_id else None}
    return {"matches": [{"id": str(m.id), "human_id": m.human_id, "weakness": m.weakness, "status": m.status} for m in matches],
            "match_rule": {"version": rule.version, "fields": rule.fields, "across_assets": rule.across_assets, "description": rule.description} if rule else None,
            "prefill": prefill}


class LinkIn(BaseModel):
    finding_id: uuid.UUID


@router.post("/poams/{poam_id}/findings")
def link(poam_id: str, body: LinkIn, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("poam.manage", "Poam", "poam_id"))) -> dict:
    p = _poam(db, request, current, poam_id, "poam.manage")
    f = db.get(Finding, body.finding_id)
    if f is None or f.system_id != p.system_id:
        raise HTTPException(422, "Finding must belong to the POA&M's system")
    wf.link_finding(db, p, f, current.user)
    audit.record(db, action="poam.finding_linked", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="poam",
                 entity_id=str(p.id), after={"finding_id": str(f.id)})
    db.commit()
    return _row(db, p)


@router.get("/poams/{poam_id}")
def detail(poam_id: str, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    p = _poam(db, request, current, poam_id)
    findings = db.execute(select(Finding, Asset.name).join(PoamFinding, PoamFinding.finding_id == Finding.id)
                          .outerjoin(Asset, Asset.id == Finding.asset_id).where(PoamFinding.poam_id == p.id)).all()
    ev_ids = [uuid.UUID(x) for x in {*(p.detection_evidence_ids or []), *(p.closure_evidence_ids or [])}]
    evidence = {str(e.id): {"id": str(e.id), "name": e.name, "sha256": e.sha256, "state": e.state, "collected_at": e.collected_at}
                for e in db.scalars(select(Evidence).where(Evidence.id.in_(ev_ids)))}
    from app.api.v1.controls import get_control

    reqs = db.scalars(select(ApprovalRequest).where(ApprovalRequest.poam_id == p.id).order_by(ApprovalRequest.created_at.desc()))
    controls = []
    for c in p.control_ids:
        try:
            cc = get_control(c, db)
            controls.append({"control_id": c, "label": cc.label, "title": cc.title, "statement": cc.statement})
        except HTTPException:
            controls.append({"control_id": c, "label": c.upper(), "title": None, "statement": None})
    return {"poam": _row(db, p), "findings": [{**to_dict(f, ("dedup_fields",)), "asset_name": a} for f, a in findings],
            "controls": controls,
            "detection_evidence": [evidence[x] for x in p.detection_evidence_ids or [] if x in evidence],
            "closure_evidence": [evidence[x] for x in p.closure_evidence_ids or [] if x in evidence],
            "milestones": [to_dict(m) for m in db.scalars(select(PoamMilestone).where(PoamMilestone.poam_id == p.id).order_by(PoamMilestone.due_date))],
            "history": attach(db, [to_dict(h) for h in db.scalars(select(PoamHistory).where(PoamHistory.poam_id == p.id).order_by(PoamHistory.created_at.desc()))], "actor_id", "actor"),
            "requests": [to_dict(r) for r in reqs],
            "system_evidence": [{"id": str(e.id), "name": e.name, "collected_at": e.collected_at, "state": e.state}
                                for e in db.scalars(select(Evidence).where(Evidence.system_id == p.system_id).order_by(Evidence.collected_at.desc()).limit(50))]}


def _control_risk(db, p: Poam) -> list[dict]:
    from app.models import EmassControlFields

    out = []
    for cid in p.control_ids or []:
        f = db.scalar(select(EmassControlFields).where(EmassControlFields.system_id == p.system_id, EmassControlFields.control_id == cid))
        vals = {"raw_severity": f.severity, "relevance_of_threat": f.relevance_of_threat, "likelihood": f.likelihood, "impact": f.impact,
                "residual_risk_level": f.residual_risk_level, "mitigations": f.mitigations} if f else {}
        out.append({"control_id": cid, "values": {k: v for k, v in vals.items() if v}})
    return out


@router.get("/poams/{poam_id}/risk")
def risk_view(poam_id: str, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    p = _poam(db, request, current, poam_id)
    return {"technical": {"severity": p.severity, "cat": p.cat, "note": "Technical severity / CAT from the scan or checklist – not the eMASS risk scale"},
            "emass": {k: getattr(p, k) for k in (*RISK_FIELDS, "comments")}, "source": p.risk_source or {},
            "control_risk_assessments": _control_risk(db, p),
            "scale": ["Very Low", "Low", "Moderate", "High", "Very High"]}


class FromControlIn(BaseModel):
    control_id: str
    overwrite: bool = False


@router.post("/poams/{poam_id}/risk/from-control")
def risk_from_control(poam_id: str, body: FromControlIn, request: Request, db: Session = Depends(get_db),
                      current: CurrentUser = Depends(require_object_permission("poam.manage", "Poam", "poam_id"))) -> dict:
    """Default the POA&M risk fields from the control's eMASS Risk Assessment (Implement step); manual values are kept unless overwrite."""
    p = _poam(db, request, current, poam_id, "poam.manage")
    if p.status in ("closed", "risk_accepted"):
        raise HTTPException(409, f"POA&M is {p.status}")
    src = next((c for c in _control_risk(db, p) if c["control_id"] == body.control_id.lower()), None)
    if src is None:
        raise HTTPException(422, f"{body.control_id} is not one of this POA&M's controls")
    if not src["values"]:
        raise HTTPException(422, f"{body.control_id.upper()} has no Risk Assessment values recorded (Control Information → Risk Assessment)")
    changed = {k: v for k, v in src["values"].items() if body.overwrite or not getattr(p, k)}
    before = {k: getattr(p, k) for k in changed}
    for k, v in changed.items():
        setattr(p, k, v)
    p.risk_source = {**(p.risk_source or {}), **{k: f"control:{body.control_id.lower()}" for k in changed}}
    wf.history(db, p, current.user, "risk_defaulted_from_control", before=before, after=changed)
    audit.record(db, action="poam.risk_from_control", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="poam",
                 entity_id=str(p.id), before=before, after={**changed, "control_id": body.control_id.lower()})
    db.commit()
    return {"applied": changed, "kept": [k for k in src["values"] if k not in changed]}


@router.patch("/poams/{poam_id}")
def update(poam_id: str, body: PoamIn, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("poam.manage", "Poam", "poam_id"))) -> dict:
    p = _poam(db, request, current, poam_id, "poam.manage")
    if p.status in ("closed", "risk_accepted"):
        raise HTTPException(409, f"POA&M is {p.status}")
    changes = body.model_dump(exclude_unset=True)
    if "status" in changes and p.status in ("closure_review", "risk_acceptance_review"):
        raise HTTPException(409, f"{p.human_id} is in {p.status.replace('_', ' ')}; status changes only through the pending review decision")
    if "due_date" in changes and p.due_date and changes["due_date"] and changes["due_date"] > p.due_date:
        raise HTTPException(409, "Moving the due date later requires a deadline extension or waiver request")
    before = {k: str(getattr(p, k)) for k in changes}
    for k, v in changes.items():
        setattr(p, k, [c.lower() for c in v] if k == "control_ids" else v)
    if risk := [k for k in changes if k in (*RISK_FIELDS, "comments")]:
        p.risk_source = {**(p.risk_source or {}), **{k: "manual" for k in risk}}
    if "owner_id" in changes and p.owner_id:
        wf.notify(db, p.owner_id, f"{p.human_id} assigned to you", f"/poams/{p.id}", "assignment", p.weakness[:200])
    wf.history(db, p, current.user, "updated", before=before, after={k: str(v) for k, v in changes.items()})
    audit.record(db, action="poam.updated", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="poam",
                 entity_id=str(p.id), before=before, after={k: str(v) for k, v in changes.items()})
    take_snapshots(db, trigger="poam.updated")
    db.commit()
    return _row(db, p)


class MilestoneIn(BaseModel):
    title: str | None = Field(None, min_length=3, max_length=2000)
    due_date: date | None = None
    status: str | None = Field(None, pattern="^(open|completed)$")


@router.post("/poams/{poam_id}/milestones", status_code=201)
def add_milestone(poam_id: str, body: MilestoneIn, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("poam.manage", "Poam", "poam_id"))) -> dict:
    p = _poam(db, request, current, poam_id, "poam.manage")
    if not body.title:
        raise HTTPException(422, "title required")
    m = PoamMilestone(poam_id=p.id, title=body.title, due_date=body.due_date)
    db.add(m)
    if p.status == "new":
        p.status = "in_progress"
    wf.history(db, p, current.user, "milestone_added", title=body.title)
    db.commit()
    return to_dict(m)


@router.patch("/poam-milestones/{milestone_id}")
def update_milestone(milestone_id: uuid.UUID, body: MilestoneIn, request: Request, db: Session = Depends(get_db),
                     current: CurrentUser = Depends(require_object_permission("poam.manage", "PoamMilestone", "milestone_id"))) -> dict:
    from datetime import datetime, timezone

    m = db.get(PoamMilestone, milestone_id)
    if m is None:
        raise HTTPException(404, "Milestone not found")
    p = _poam(db, request, current, str(m.poam_id), "poam.manage")
    for k, v in body.model_dump(exclude_unset=True).items():
        setattr(m, k, v)
    m.completed_at = datetime.now(timezone.utc) if m.status == "completed" else None
    wf.history(db, p, current.user, "milestone_updated", title=m.title, status=m.status)
    db.commit()
    return to_dict(m)


class ClosureIn(BaseModel):
    justification: str = Field(min_length=10, max_length=5000)
    evidence_ids: list[str] = Field(min_length=1)


class RiskIn(BaseModel):
    justification: str = Field(min_length=10, max_length=5000)
    kind: str = Field("waiver_extension", pattern="^(waiver_extension|deadline_extension)$")
    expiration: date | None = None
    new_due_date: date | None = None


def _open_request(db, p: Poam, t: str):
    if db.scalar(select(ApprovalRequest.id).where(ApprovalRequest.poam_id == p.id, ApprovalRequest.request_type == t, ApprovalRequest.status == "pending")):
        raise HTTPException(409, f"A pending {t} request already exists for {p.human_id}")


@router.post("/poams/{poam_id}/request-closure", status_code=201)
def request_closure(poam_id: str, body: ClosureIn, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("poam.manage", "Poam", "poam_id"))) -> dict:
    p = _poam(db, request, current, poam_id, "poam.manage")
    if p.status not in ("new", "in_progress", "closure_eligible"):
        raise HTTPException(409, f"Cannot request closure while {p.status}")
    _open_request(db, p, "poam_closure")
    ev = wf.evidence_in_system(db, p.system_id, body.evidence_ids)
    if not ev:
        raise HTTPException(422, "Closure requires at least one closure evidence item from this system's ledger")
    req = wf.create_request(db, system=get_system(db, p.system_id), requester=current.user, request_type="poam_closure",
                            justification=body.justification, poam_id=p.id, control_id=p.control_ids[0], evidence_ids=ev,
                            payload={"prev_status": p.status})
    p.status, p.closure_evidence_ids = "closure_review", ev
    wf.history(db, p, current.user, "closure_requested", request=req.human_id)
    take_snapshots(db, trigger="review.requested")
    db.commit()
    return to_dict(req)


@router.post("/poams/{poam_id}/request-risk-acceptance", status_code=201)
def request_risk(poam_id: str, body: RiskIn, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("poam.manage", "Poam", "poam_id"))) -> dict:
    p = _poam(db, request, current, poam_id, "poam.manage")
    if not body.expiration or body.expiration <= date.today():
        raise HTTPException(422, "Risk acceptance requires a future expiration date")
    _open_request(db, p, "risk_acceptance")
    req = wf.create_request(db, system=get_system(db, p.system_id), requester=current.user, request_type="risk_acceptance",
                            justification=body.justification, poam_id=p.id, control_id=p.control_ids[0],
                            payload={"expiration": body.expiration.isoformat(), "prev_status": p.status}, deadline=body.expiration)
    p.status = "risk_acceptance_review"
    wf.history(db, p, current.user, "risk_acceptance_requested", request=req.human_id)
    take_snapshots(db, trigger="review.requested")
    db.commit()
    return to_dict(req)


@router.post("/poams/{poam_id}/request-extension", status_code=201)
def request_extension(poam_id: str, body: RiskIn, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_object_permission("poam.manage", "Poam", "poam_id"))) -> dict:
    p = _poam(db, request, current, poam_id, "poam.manage")
    if not body.new_due_date or (p.due_date and body.new_due_date <= p.due_date):
        raise HTTPException(422, "Extension requires a new due date later than the current one")
    _open_request(db, p, body.kind)
    req = wf.create_request(db, system=get_system(db, p.system_id), requester=current.user, request_type=body.kind,
                            justification=body.justification, poam_id=p.id, control_id=p.control_ids[0],
                            payload={"new_due_date": body.new_due_date.isoformat(), "old_due_date": str(p.due_date), "prev_status": p.status})
    wf.history(db, p, current.user, "extension_requested", request=req.human_id)
    db.commit()
    return to_dict(req)


@router.get("/poam-match-rules")
def match_rules(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return [to_dict(r) for r in db.scalars(select(PoamMatchRule).where(PoamMatchRule.org_id == current.user.org_id).order_by(PoamMatchRule.version))]


_ = evaluate_system
