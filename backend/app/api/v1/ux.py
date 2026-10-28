"""UX helpers: link evidence to a control (existing EvidenceControl link, same rules as ingest) and per-user UI preferences."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.records import get_system
from app.db import get_db
from app.models import ControlAssignment, Evidence, EvidenceControl, Implementation, User
from app.security.deps import CurrentUser, get_current_user, require_permission, self_scoped
from app.services import audit

router = APIRouter(tags=["ux"])
PREFS = {"guided": ("on", "off"), "sca_auto_advance": (True, False)}


class LinkIn(BaseModel):
    evidence_id: uuid.UUID


@router.post("/systems/{system_id}/controls/{control_id}/evidence-links", status_code=201)
def link_evidence(system_id: uuid.UUID, control_id: str, body: LinkIn, db: Session = Depends(get_db),
                  current: CurrentUser = Depends(require_permission("ingest.upload"))) -> dict:
    s = get_system(db, system_id)
    a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == s.id, ControlAssignment.control_id == control_id.lower()))
    ev = db.get(Evidence, body.evidence_id)
    if a is None or ev is None or ev.system_id != s.id:
        raise HTTPException(404, "Control or evidence not found in this system")
    if db.scalar(select(EvidenceControl.id).where(EvidenceControl.evidence_id == ev.id, EvidenceControl.assignment_id == a.id)):
        return {"linked": False, "already_linked": True}
    db.add(EvidenceControl(evidence_id=ev.id, assignment_id=a.id))
    for impl in db.scalars(select(Implementation).where(Implementation.assignment_id == a.id,
                                                        Implementation.review_status.in_(("approved", "draft", "in_review")))):
        impl.needs_reconsideration = True  # same rule as the ingest pipeline: new evidence → statement should be reconsidered
    audit.record(db, action="evidence.linked_to_control", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="evidence",
                 entity_id=str(ev.id), after={"system_id": str(s.id), "control_id": a.control_id})
    db.commit()
    return {"linked": True, "already_linked": False}


class PrefsIn(BaseModel):
    guided: str | None = Field(None, pattern="^(on|off)$")
    sca_auto_advance: bool | None = None


@router.get("/me/preferences")
def get_prefs(current: CurrentUser = Depends(get_current_user)) -> dict:
    return (current.user.onboarding or {}).get("prefs", {})


@router.put("/me/preferences")
def put_prefs(body: PrefsIn, db: Session = Depends(get_db), current: CurrentUser = Depends(self_scoped)) -> dict:
    u = db.get(User, current.user.id)
    data = dict(u.onboarding or {})
    prefs = {**data.get("prefs", {}), **body.model_dump(exclude_none=True)}
    u.onboarding = {**data, "prefs": prefs}
    db.add(u)
    db.commit()
    return prefs
