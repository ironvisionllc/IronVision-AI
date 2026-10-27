"""eMASS Control Information import: upload → review (per-field accept/reject) → apply / discard; history per system."""
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.emass_fields import _can_edit
from app.api.v1.records import enforce, get_system
from app.db import get_db
from app.models import EmassImport
from app.security.deps import CurrentUser, require_permission
from app.services import audit
from app.services import emass_fields as ef
from app.services import emass_import as ei

router = APIRouter(tags=["emass-import"])


def _imp(db: Session, system_id: uuid.UUID, import_id: uuid.UUID) -> EmassImport:
    imp = db.get(EmassImport, import_id)
    if imp is None or imp.system_id != system_id:
        raise HTTPException(404, "Import not found")
    return imp


@router.get("/systems/{system_id}/emass-imports")
def history(system_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    enforce(request, current, "system.read", system_id)
    get_system(db, system_id)
    rows = db.scalars(select(EmassImport).where(EmassImport.system_id == system_id).order_by(EmassImport.created_at.desc()).limit(100))
    return {"label": ei.LABEL, "can_apply": _can_edit(current, system_id), "items": [ei.out(i) for i in rows]}


@router.get("/systems/{system_id}/emass-imports/sample.xlsx")
def sample(system_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))):
    enforce(request, current, "system.read", system_id)
    s = get_system(db, system_id)
    return Response(ei.sample_xlsx(ef.rows(db, s)), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="SYNTHETIC_{s.acronym or "system"}_ControlInfoExport_sample.xlsx"'})


@router.post("/systems/{system_id}/emass-imports", status_code=201)
async def upload(system_id: uuid.UUID, request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
                 current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    enforce(request, current, "implementation.write", system_id)
    s = get_system(db, system_id)
    data = await file.read(ei.MAX_BYTES + 1)
    imp = ei.create(db, s, file.filename or "upload.xlsx", data, current.user)
    audit.record(db, action="emass.import_uploaded", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="emass_import",
                 entity_id=str(imp.id), after={"file_name": imp.file_name, "sha256": imp.sha256, "size_bytes": imp.size_bytes, "counts": imp.counts},
                 details={"system_id": str(system_id)}, **audit.request_meta(request))
    db.commit()
    return ei.out(imp, full=True)


@router.get("/systems/{system_id}/emass-imports/{import_id}")
def detail(system_id: uuid.UUID, import_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
           current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    enforce(request, current, "system.read", system_id)
    return {**ei.out(_imp(db, system_id, import_id), full=True), "can_apply": _can_edit(current, system_id)}


class Decision(BaseModel):
    control_id: str = Field(max_length=50)
    field: str | None = Field(None, max_length=40)
    decision: str | None = Field(None, pattern="^(accept|reject)$")


class DecideIn(BaseModel):
    decisions: list[Decision] = Field(default_factory=list, max_length=20000)
    bulk: str | None = Field(None, pattern="^(accept_safe|reject_all|reset)$")


@router.put("/systems/{system_id}/emass-imports/{import_id}/decisions")
def decisions(system_id: uuid.UUID, import_id: uuid.UUID, body: DecideIn, request: Request, db: Session = Depends(get_db),
              current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    enforce(request, current, "implementation.write", system_id)
    imp = _imp(db, system_id, import_id)
    ei.decide(db, imp, [d.model_dump() for d in body.decisions], body.bulk)
    db.commit()
    return {**ei.out(imp, full=True), "can_apply": True}


@router.post("/systems/{system_id}/emass-imports/{import_id}/apply")
def apply(system_id: uuid.UUID, import_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
          current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    enforce(request, current, "implementation.write", system_id)
    imp = _imp(db, system_id, import_id)
    res = ei.apply(db, imp, current, audit.request_meta(request))
    audit.record(db, action="emass.import_applied", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="emass_import",
                 entity_id=str(imp.id), after={"counts": imp.counts}, details={"file_name": imp.file_name, "sha256": imp.sha256}, **audit.request_meta(request))
    from app.services.evaluation import evaluate_system
    db.flush()
    evaluate_system(db, system_id)
    db.commit()
    return {**ei.out(imp, full=True), **res}


@router.post("/systems/{system_id}/emass-imports/{import_id}/discard")
def discard(system_id: uuid.UUID, import_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
            current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    enforce(request, current, "implementation.write", system_id)
    imp = _imp(db, system_id, import_id)
    if imp.status != "review":
        raise HTTPException(409, f"This import is already {imp.status}")
    from datetime import datetime, timezone
    imp.status, imp.finished_at, imp.applied_by_email = "discarded", datetime.now(timezone.utc), current.user.email
    audit.record(db, action="emass.import_discarded", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="emass_import",
                 entity_id=str(imp.id), details={"file_name": imp.file_name, "sha256": imp.sha256}, **audit.request_meta(request))
    db.commit()
    return ei.out(imp)
