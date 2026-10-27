"""eMASS Control Information import: upload → review (per-field accept/reject) → apply / discard; history per system."""
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
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
    control_id: str | None = Field(None, max_length=50)
    key: str | None = Field(None, max_length=60)
    field: str | None = Field(None, max_length=40)
    decision: str | None = Field(None, pattern="^(accept|reject)$")


class EmassImportDecideIn(BaseModel):
    decisions: list[Decision] = Field(default_factory=list, max_length=20000)
    bulk: str | None = Field(None, pattern="^(accept_safe|reject_all|reset)$")


@router.put("/systems/{system_id}/emass-imports/{import_id}/decisions")
def decisions(system_id: uuid.UUID, import_id: uuid.UUID, body: EmassImportDecideIn, request: Request, db: Session = Depends(get_db),
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


# ---------- generic eMASS report import (all types; in-system and no-system entry points) ----------
from app.security.rbac import effective_permissions, has_permission  # noqa: E402
from app.services import emass_reports as er  # noqa: E402


def _allowed(current: CurrentUser, system_id) -> set:
    return {sec for sec, perm in er.SECTION_PERM.items() if has_permission(current.assignments, perm, current.user.org_id, system_id)}


def _org_imp(db: Session, import_id: uuid.UUID, current: CurrentUser, request: Request) -> EmassImport:
    imp = db.get(EmassImport, import_id)
    if imp is None or imp.org_id != current.user.org_id:
        raise HTTPException(404, "Import not found")
    if imp.system_id:
        enforce(request, current, "system.read", imp.system_id)
    return imp


def _view(imp: EmassImport, current: CurrentUser) -> dict:
    allowed = _allowed(current, imp.system_id) if imp.system_id else set()
    secs = sorted({i.get("section", "Controls") for i in imp.items or []})
    return {**ei.out(imp, full=True), "allowed_sections": sorted(allowed), "can_apply": bool(allowed & set(secs)),
            "read_only_sections": {s: f"Needs the {er.SECTION_PERM[s]} permission (your role cannot apply {s} changes)" for s in secs if s not in allowed}}


@router.post("/emass-imports", status_code=201)
async def generic_upload(request: Request, file: UploadFile = File(...), system_id: uuid.UUID | None = Form(None), db: Session = Depends(get_db),
                         current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    """Upload any eMASS export: detect the report type + system identity and return the context prompt. Nothing is built or saved yet."""
    ctx = None
    if system_id:
        enforce(request, current, "system.read", system_id)
        ctx = get_system(db, system_id)
    writable = set(er.SECTION_PERM.values()) | {"system.register"}
    if not ((_allowed(current, system_id) if system_id else set()) or has_permission(current.assignments, "system.register", current.user.org_id, None)
            or (not system_id and writable & set(effective_permissions(current.assignments)))):
        raise HTTPException(403, "Your role is read-only – importing an eMASS file needs a write permission (e.g. system.write, implementation.write, poam.manage)")
    data = await file.read(ei.MAX_BYTES + 1)
    name = file.filename or "upload.xlsx"
    sheets = er.read_sheets(data, name)
    det = er.detect(sheets)
    ident = er.identity(sheets)
    det.update(identity=ident, context_system_id=str(ctx.id) if ctx else None, context_system=(ctx.acronym or ctx.name) if ctx else None,
               mismatch=er.mismatch(ident, ctx), labels={t: er.label(t) for t in er.TYPES})
    imp = ei.store(db, current.user.org_id, None, name, data, current.user, det["type"] or "control_information", det)
    audit.record(db, action="emass.import_uploaded", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="emass_import",
                 entity_id=str(imp.id), after={"file_name": imp.file_name, "sha256": imp.sha256, "detected_type": det["type"], "confidence": det["confidence"]},
                 **audit.request_meta(request))
    db.commit()
    return _view(imp, current)


class TargetIn(BaseModel):
    action: str = Field(pattern="^(update|register|cancel)$")
    system_id: uuid.UUID | None = None
    report_type: str | None = Field(None, pattern="^(system_details|control_information|test_results|poam|hwsw)$")


@router.post("/emass-imports/{import_id}/target")
def generic_target(import_id: uuid.UUID, body: TargetIn, request: Request, db: Session = Depends(get_db),
                   current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    imp = _org_imp(db, import_id, current, request)
    if imp.status not in ("detected", "review"):
        raise HTTPException(409, f"This import is already {imp.status}")
    from app.services.storage.base import get_storage
    data = get_storage().get(imp.storage_key)
    typ = body.report_type or (imp.detected or {}).get("type")
    from datetime import datetime, timezone
    if body.action == "cancel":
        imp.status, imp.finished_at, imp.applied_by_email = "discarded", datetime.now(timezone.utc), current.user.email
        audit.record(db, action="emass.import_discarded", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="emass_import",
                     entity_id=str(imp.id), details={"file_name": imp.file_name, "sha256": imp.sha256, "reason": "cancelled at the prompt"}, **audit.request_meta(request))
        db.commit()
        return _view(imp, current)
    if not typ:
        raise HTTPException(422, "The report type could not be detected – choose it explicitly")
    if body.action == "register":
        if not has_permission(current.assignments, "system.register", current.user.org_id, None):
            raise HTTPException(403, "Registering a system needs the system.register permission")
        pre = er.prefill(imp, er.read_sheets(data, imp.file_name))
        imp.status, imp.finished_at, imp.applied_by_email = "to_registration", datetime.now(timezone.utc), current.user.email
        audit.record(db, action="emass.import_to_registration", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="emass_import",
                     entity_id=str(imp.id), details={"file_name": imp.file_name, "sha256": imp.sha256, "report_type": typ, "prefill": pre["system"]},
                     **audit.request_meta(request))
        db.commit()
        return {**_view(imp, current), "prefill": pre, "report_type": typ}
    if not body.system_id:
        raise HTTPException(422, "Pick the system to update")
    enforce(request, current, "system.read", body.system_id)
    s = get_system(db, body.system_id)
    if typ != imp.report_type and imp.detected:
        imp.detected = {**imp.detected, "overridden_from": imp.detected.get("type")}
    ei.target(db, imp, s, typ, data)
    imp.detected = {**(imp.detected or {}), "mismatch": er.mismatch((imp.detected or {}).get("identity") or {}, s)}
    audit.record(db, action="emass.import_targeted", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="emass_import",
                 entity_id=str(imp.id), details={"system_id": str(s.id), "report_type": typ}, **audit.request_meta(request))
    db.commit()
    return _view(imp, current)


@router.get("/emass-imports")
def generic_history(system_id: uuid.UUID | None = None, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    q = select(EmassImport).where(EmassImport.org_id == current.user.org_id)
    q = q.where(EmassImport.system_id == system_id) if system_id else q
    return {"items": [ei.out(i) for i in db.scalars(q.order_by(EmassImport.created_at.desc()).limit(200))], "types": er.TYPES}


@router.get("/emass-imports/samples/{report_type}")
def generic_sample(report_type: str, system_id: uuid.UUID | None = None, request: Request = None, db: Session = Depends(get_db),
                   current: CurrentUser = Depends(require_permission("system.read"))):
    if report_type not in er.TYPES:
        raise HTTPException(404, "Unknown report type")
    rows = None
    if system_id:
        enforce(request, current, "system.read", system_id)
        rows = ef.rows(db, get_system(db, system_id))
    ext = "xlsm" if report_type == "hwsw" else "xlsx"
    return Response(er.sample_xlsx(report_type, rows), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="SYNTHETIC_eMASS_{report_type}_sample.{ext}"'})


@router.get("/emass-imports/{import_id}")
def generic_detail(import_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    return _view(_org_imp(db, import_id, current, request), current)


@router.put("/emass-imports/{import_id}/decisions")
def generic_decisions(import_id: uuid.UUID, body: EmassImportDecideIn, request: Request, db: Session = Depends(get_db),
                      current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    imp = _org_imp(db, import_id, current, request)
    allowed = _allowed(current, imp.system_id) if imp.system_id else set()
    if not allowed:
        raise HTTPException(403, "Your role cannot apply any section of this import (view only)")
    ei.decide(db, imp, [d.model_dump() for d in body.decisions], body.bulk, allowed)
    db.commit()
    return _view(imp, current)


@router.post("/emass-imports/{import_id}/apply")
def generic_apply(import_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    imp = _org_imp(db, import_id, current, request)
    allowed = _allowed(current, imp.system_id) if imp.system_id else set()
    if not imp.system_id or not allowed:
        raise HTTPException(403, "Your role cannot apply this import")
    bad = {i["section"] for i in imp.items or [] for f in i["fields"].values() if f.get("decision") == "accept" and i.get("section", "Controls") not in allowed}
    if bad:
        raise HTTPException(403, f"Accepted changes in sections you cannot apply: {', '.join(sorted(bad))}")
    res = ei.apply(db, imp, current, audit.request_meta(request))
    audit.record(db, action="emass.import_applied", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="emass_import",
                 entity_id=str(imp.id), after={"counts": imp.counts}, details={"file_name": imp.file_name, "sha256": imp.sha256, "report_type": imp.report_type},
                 **audit.request_meta(request))
    from app.services.evaluation import evaluate_system
    db.flush()
    evaluate_system(db, imp.system_id)
    db.commit()
    return {**_view(imp, current), **res}


@router.post("/emass-imports/{import_id}/discard")
def generic_discard(import_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    imp = _org_imp(db, import_id, current, request)
    if imp.status not in ("detected", "review"):
        raise HTTPException(409, f"This import is already {imp.status}")
    from datetime import datetime, timezone
    imp.status, imp.finished_at, imp.applied_by_email = "discarded", datetime.now(timezone.utc), current.user.email
    audit.record(db, action="emass.import_discarded", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="emass_import",
                 entity_id=str(imp.id), details={"file_name": imp.file_name, "sha256": imp.sha256}, **audit.request_meta(request))
    db.commit()
    return ei.out(imp)
