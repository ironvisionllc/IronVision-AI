"""UX helpers: link evidence to a control (existing EvidenceControl link, same rules as ingest) and per-user UI preferences."""
import hashlib
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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


def _link(db: Session, s, control_id: str, ev: Evidence | None, current: CurrentUser) -> dict:
    a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == s.id, ControlAssignment.control_id == control_id.lower()))
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
    return {"linked": True, "already_linked": False}


@router.post("/systems/{system_id}/controls/{control_id}/evidence-links", status_code=201)
def link_evidence(system_id: uuid.UUID, control_id: str, body: LinkIn, db: Session = Depends(get_db),
                  current: CurrentUser = Depends(require_permission("ingest.upload"))) -> dict:
    out = _link(db, get_system(db, system_id), control_id, db.get(Evidence, body.evidence_id), current)
    db.commit()
    return out


@router.post("/systems/{system_id}/controls/{control_id}/evidence", status_code=201)
async def upload_control_evidence(system_id: uuid.UUID, control_id: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                                  current: CurrentUser = Depends(require_permission("ingest.upload"))) -> dict:
    """General evidence (documents, images, exports): evidence allow-list + magic bytes + scanner, hash-keyed storage, linked to the control."""
    from app.services import rmf
    from app.services.upload_security import UploadRejected, validate_upload

    s = get_system(db, system_id)
    if db.scalar(select(ControlAssignment.id).where(ControlAssignment.system_id == s.id, ControlAssignment.control_id == control_id.lower())) is None:
        raise HTTPException(404, "Control or evidence not found in this system")
    data = await file.read()
    name = file.filename or "evidence"
    try:
        validate_upload(name, data, "evidence")
    except UploadRejected as exc:
        raise HTTPException(415 if "type" in str(exc) or "match" in str(exc) else 413 if "limit" in str(exc) else 422, str(exc))
    sha = hashlib.sha256(data).hexdigest()
    ev = db.scalar(select(Evidence).where(Evidence.system_id == s.id, Evidence.sha256 == sha, Evidence.status == "active").limit(1))
    duplicate = ev is not None
    if ev is None:
        ev = rmf.store_evidence(db, s.id, name, data, "document", current.user.email, "manual_upload")
        audit.record(db, action="evidence.uploaded", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="evidence",
                     entity_id=str(ev.id), after={"file_name": name, "sha256": sha, "size_bytes": len(data), "control_id": control_id.lower()})
    out = _link(db, s, control_id, ev, current)
    db.commit()
    return {"evidence_id": str(ev.id), "sha256": sha, "name": ev.name, "status": "duplicate" if duplicate else "stored", **out}


class PrefsIn(BaseModel):
    guided: str | None = Field(None, pattern="^(on|off)$")
    sca_auto_advance: bool | None = None
    autosave: bool | None = None


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
