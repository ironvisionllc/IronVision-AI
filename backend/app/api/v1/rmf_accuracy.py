"""RMF accuracy endpoints: categorization revisions/approval, PTA, agency overlays, framework reference."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import AgencyOverlay, CategorizationRecord, PtaQuestionSet, PtaResponse, System
from app.security.deps import CurrentUser, get_current_user, require_permission
from app.security.rbac import has_permission
from app.services import audit
from app.services import rmf_accuracy as ra

router = APIRouter(tags=["rmf-accuracy"])


def _sys(db: Session, sid: uuid.UUID, current: CurrentUser) -> System:
    s = db.get(System, sid)
    if s is None or s.org_id != current.user.org_id:
        raise HTTPException(404, "System not found")
    return s


def _real_email(current: CurrentUser) -> str:
    return (current.operator or current.user).email


@router.get("/reference/frameworks")
def frameworks(_: CurrentUser = Depends(get_current_user)) -> dict:
    return {"frameworks": ra.FRAMEWORKS, "nss_help": ra.NSS_HELP, "nss_answers": ["yes", "no", "unsure"], "srg_source": ra.SRG}


@router.get("/systems/{system_id}/categorization/records")
def categorization_records(system_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    s = _sys(db, system_id, current)
    hist = list(db.scalars(select(CategorizationRecord).where(CategorizationRecord.system_id == s.id).order_by(CategorizationRecord.revision.desc())))
    f = ra.flags(s)
    return {"current": ra.rec_out(hist[0]) if hist else None, "approved": next((ra.rec_out(r) for r in hist if r.status == "approved"), None),
            "history": [ra.rec_out(r) for r in hist], "nss_determination": s.nss_determination, "classified_information": f.get("classified_information"),
            "review_flags": ra.review_flags(s), "il_options": ra.il_options(s.operating_environment, s.categorization_mode, f.get("classified_information")),
            "il_note": None if s.operating_environment in ra.CLOUD_ENVS else ra.IL_REASON["not_cloud"], "srg_source": ra.SRG,
            "can_approve": has_permission(current.assignments, "authorization.decide", s.org_id, s.id)}


class ApproveIn(BaseModel):
    rationale: str = Field(min_length=10, max_length=4000)


@router.post("/systems/{system_id}/categorization/records/{record_id}/approve")
def approve_categorization(system_id: uuid.UUID, record_id: uuid.UUID, body: ApproveIn, request: Request, db: Session = Depends(get_db),
                           current: CurrentUser = Depends(require_permission("authorization.decide"))) -> dict:
    s = _sys(db, system_id, current)
    rec = db.get(CategorizationRecord, record_id)
    if rec is None or rec.system_id != s.id:
        raise HTTPException(404, "Categorization revision not found")
    try:
        ra.approve(db, s, rec, current.user, _real_email(current), body.rationale)
    except ValueError as e:
        raise HTTPException(422, str(e))
    audit.record(db, action="categorization.approved", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system",
                 entity_id=str(s.id), after={"revision": rec.revision, "framework": rec.framework, "impacts": rec.impacts, "baseline": rec.baseline},
                 details={"rationale": body.rationale}, **audit.request_meta(request))
    db.commit()
    return ra.rec_out(rec)


# ---------- PTA ----------
def _set_out(q: PtaQuestionSet) -> dict:
    return {"id": str(q.id), "key": q.key, "version": q.version, "title": q.title, "label": q.label, "questions": q.questions,
            "agency_defined": q.org_id is not None, "active": q.is_active}


@router.get("/systems/{system_id}/pta")
def get_pta(system_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    s = _sys(db, system_id, current)
    qs = ra.active_set(db, s.org_id)
    db.commit()
    hist = list(db.scalars(select(PtaResponse).where(PtaResponse.system_id == s.id).order_by(PtaResponse.revision.desc())))
    return {"question_set": _set_out(qs), "latest": ra.pta_out(hist[0]) if hist else None, "history": [ra.pta_out(r) for r in hist],
            "note": "The outcome is a recommendation. Only a privacy official's approval makes a privacy determination."}


class PtaIn(BaseModel):
    answers: dict = Field(description="question id → {answer: yes|no|not_sure, explanation}")


@router.post("/systems/{system_id}/pta", status_code=201)
def submit_pta(system_id: uuid.UUID, body: PtaIn, request: Request, db: Session = Depends(get_db),
               current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    s = _sys(db, system_id, current)
    try:
        r = ra.submit(db, s, body.answers, current.user.email)
    except ValueError as e:
        raise HTTPException(422, str(e))
    audit.record(db, action="pta.submitted", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system", entity_id=str(s.id),
                 after={"revision": r.revision, "flags": r.flags}, **audit.request_meta(request))
    db.commit()
    return ra.pta_out(r)


class PtaReviewIn(BaseModel):
    decision: str = Field(pattern="^(approve|return)$")
    rationale: str = Field(min_length=10, max_length=4000)
    determination: str | None = Field(None, pattern="^(pii|no_pii)$")


@router.post("/systems/{system_id}/pta/{response_id}/review")
def review_pta(system_id: uuid.UUID, response_id: uuid.UUID, body: PtaReviewIn, request: Request, db: Session = Depends(get_db),
               current: CurrentUser = Depends(require_permission("privacy.review"))) -> dict:
    s = _sys(db, system_id, current)
    r = db.get(PtaResponse, response_id)
    if r is None or r.system_id != s.id:
        raise HTTPException(404, "PTA not found")
    if body.decision == "approve" and not body.determination:
        raise HTTPException(422, "Approving needs a determination (pii or no_pii)")
    try:
        ra.review(db, s, r, current.user.email, body.decision, body.rationale, body.determination)
    except ValueError as e:
        raise HTTPException(422, str(e))
    audit.record(db, action=f"pta.{'approved' if body.decision == 'approve' else 'returned'}", actor_user_id=current.user.id, actor_email=current.user.email,
                 entity_type="system", entity_id=str(s.id), after={"revision": r.revision, "determination": r.determination},
                 details={"rationale": body.rationale}, **audit.request_meta(request))
    db.commit()
    return ra.pta_out(r)


class QuestionSetIn(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    questions: list[dict] = Field(min_length=1, max_length=100)


@router.get("/pta/question-sets")
def list_sets(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> list[dict]:
    ra.default_set(db)
    db.commit()
    rows = db.scalars(select(PtaQuestionSet).where((PtaQuestionSet.org_id.is_(None)) | (PtaQuestionSet.org_id == current.user.org_id))
                      .order_by(PtaQuestionSet.key, PtaQuestionSet.version.desc()))
    return [_set_out(q) for q in rows]


@router.post("/pta/question-sets", status_code=201)
def create_set(body: QuestionSetIn, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("admin.content.load"))) -> dict:
    """Agency-specific question set: a new version deactivates the previous one (old responses keep their version)."""
    for q in body.questions:
        if not q.get("id") or not q.get("text"):
            raise HTTPException(422, "Each question needs an id and text")
    key = f"agency-{current.user.org_id}"
    prev = list(db.scalars(select(PtaQuestionSet).where(PtaQuestionSet.org_id == current.user.org_id)))
    for p in prev:
        p.is_active = False
    q = PtaQuestionSet(org_id=current.user.org_id, key=key, version=max([p.version for p in prev] or [0]) + 1, title=body.title,
                       label="Agency-defined question set", questions=body.questions, created_by=current.user.email)
    db.add(q)
    db.flush()
    audit.record(db, action="pta.question_set_created", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="pta_question_set",
                 entity_id=str(q.id), after={"version": q.version, "questions": len(body.questions)}, **audit.request_meta(request))
    db.commit()
    return _set_out(q)


# ---------- agency overlays ----------
class AgencyOverlayIn(BaseModel):
    name: str = Field(min_length=3, max_length=255)
    issuing_authority: str = Field(min_length=2, max_length=255)
    source_document: str = Field(min_length=3, max_length=500)
    framework: str = Field(pattern="^(fips199|cnssi1253)$")
    version: str = Field(min_length=1, max_length=50)
    applicability: str = Field(min_length=10, max_length=4000)
    status: str = Field("approved", pattern="^(approved|pending_validation|retired)$")
    effective_date: date | None = None


def _ao_out(o: AgencyOverlay) -> dict:
    return {"id": str(o.id), "name": o.name, "issuing_authority": o.issuing_authority, "source_document": o.source_document, "framework": o.framework,
            "version": o.version, "applicability": o.applicability, "status": o.status, "effective_date": o.effective_date.isoformat() if o.effective_date else None,
            "agency_defined": True}


@router.get("/agency-overlays")
def list_agency_overlays(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return [_ao_out(o) for o in db.scalars(select(AgencyOverlay).where(AgencyOverlay.org_id == current.user.org_id).order_by(AgencyOverlay.name))]


@router.post("/agency-overlays", status_code=201)
def create_agency_overlay(body: AgencyOverlayIn, request: Request, db: Session = Depends(get_db),
                          current: CurrentUser = Depends(require_permission("admin.content.load"))) -> dict:
    o = AgencyOverlay(org_id=current.user.org_id, created_by=current.user.email, **body.model_dump())
    db.add(o)
    db.flush()
    audit.record(db, action="overlay.agency_created", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="agency_overlay",
                 entity_id=str(o.id), after=body.model_dump(mode="json"), **audit.request_meta(request))
    db.commit()
    return _ao_out(o)


# ---------- side-by-side policy mapping review ----------
def _pmap(db: Session, policy_id: uuid.UUID, control_id: str, current: CurrentUser):
    from app.models import Policy, PolicyControlMap
    from app.services import policy_mapping as pm

    p = db.get(Policy, policy_id)
    if p is None or p.org_id != current.user.org_id:
        raise HTTPException(404, "Policy not found")
    m = next((x for x in pm.current(db, p.id) if x.control_id == control_id.lower()), None)
    if m is None:
        raise HTTPException(404, "No current mapping for this control")
    return p, m


@router.get("/policies/{policy_id}/mappings/{control_id}/review")
def mapping_review_sbs(policy_id: uuid.UUID, control_id: str, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    from app.services import mapping_sbs

    p, m = _pmap(db, policy_id, control_id, current)
    return mapping_sbs.review(db, p, m)


class MapDecisionIn(BaseModel):
    action: str = Field(pattern="^(accept|reject|edit|reanalyze|flag|override_coverage)$")
    comment: str = Field("", max_length=4000)
    edit_control_id: str | None = None
    coverage_outcome: str | None = Field(None, pattern="^(Fully Addressed|Partially Addressed|Not Addressed|Requires Manual Review)$")


@router.post("/policies/{policy_id}/mappings/{control_id}/decision")
def mapping_decision(policy_id: uuid.UUID, control_id: str, body: MapDecisionIn, request: Request, db: Session = Depends(get_db),
                     current: CurrentUser = Depends(get_current_user)) -> dict:
    """Accept / Reject / Edit mapping / Request reanalysis / Flag for manual review / Override coverage – each with a comment, audited."""
    from app.models import PolicyControlMap
    from app.services import mapping_sbs, policy_mapping as pm

    p, m = _pmap(db, policy_id, control_id, current)
    sids = [uuid.UUID(str(x)) for x in (p.system_ids or [])] or [None]
    if not any(has_permission(current.assignments, "finding.map", p.org_id, sid) for sid in sids):
        raise HTTPException(403, "Missing permission: finding.map")
    need = {"reject": 10, "edit": 10, "flag": 5, "override_coverage": 10}.get(body.action, 0)
    if len(body.comment.strip()) < need:
        raise HTTPException(422, f"A comment of at least {need} characters is required for {body.action.replace('_', ' ')}.")
    before = {"status": m.status, "control_id": m.control_id}
    who = current.user.email
    if body.action == "accept":
        m = pm.decide(db, p, m.control_id, "mapped", current.user, body.comment or None)
        m.reanalysis = None
    elif body.action == "reject":
        m = pm.decide(db, p, m.control_id, "rejected", current.user, body.comment)
    elif body.action == "edit":
        new = (body.edit_control_id or "").strip().lower().replace("(", ".").replace(")", "")
        if not new or new == m.control_id:
            raise HTTPException(422, "Choose the control the mapping should point to instead")
        pm.decide(db, p, m.control_id, "rejected", current.user, f"Edited to {new.upper()}: {body.comment}")
        m = pm.decide(db, p, new, "mapped", current.user, body.comment)
    elif body.action == "reanalyze":
        from app.services.policy_mapping import extract_mappings, store_proposals

        store_proposals(db, p, extract_mappings(db, p.text_content or ""))
        m = next(x for x in pm.current(db, p.id) if x.control_id == m.control_id)
    elif body.action == "flag":
        m.review_flag = True
    elif body.action == "override_coverage":
        if not body.coverage_outcome:
            raise HTTPException(422, "Pick the coverage outcome")
        m.coverage_override = {"outcome": body.coverage_outcome, "justification": body.comment, "by": who, "at": mapping_sbs.now().isoformat()}
    mapping_sbs.comment(m, who, body.action, body.comment)
    audit.record(db, action=f"policy_mapping.{body.action}", actor_user_id=current.user.id, actor_email=who, entity_type="policy", entity_id=str(p.id),
                 before=before, after={"status": m.status, "control_id": m.control_id, "coverage_override": m.coverage_override, "review_flag": m.review_flag},
                 details={"comment": body.comment}, **audit.request_meta(request))
    db.commit()
    return mapping_sbs.review(db, p, m)
