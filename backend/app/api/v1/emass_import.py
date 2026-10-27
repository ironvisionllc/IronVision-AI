"""eMASS Control Information import: upload → review (per-field accept/reject) → apply / discard; history per system."""
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
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
    key: str | None = Field(None, max_length=220)
    field: str | None = Field(None, max_length=40)
    decision: str | None = Field(None, pattern="^(accept|reject)$")


class EmassImportDecideIn(BaseModel):
    decisions: list[Decision] = Field(default_factory=list, max_length=20000)
    bulk: str | None = Field(None, pattern="^(accept_safe|reject_all|reset|keep_existing|use_imported)$")
    section: str | None = Field(None, max_length=40, description="keep_existing / use_imported for one section; omitted = every section")


@router.put("/systems/{system_id}/emass-imports/{import_id}/decisions")
def decisions(system_id: uuid.UUID, import_id: uuid.UUID, body: EmassImportDecideIn, request: Request, db: Session = Depends(get_db),
              current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    enforce(request, current, "implementation.write", system_id)
    imp = _imp(db, system_id, import_id)
    ei.decide(db, imp, [d.model_dump() for d in body.decisions], body.bulk)
    db.commit()
    return {**ei.out(imp, full=True), "can_apply": True}


@router.post("/systems/{system_id}/emass-imports/{import_id}/apply")
def apply(system_id: uuid.UUID, import_id: uuid.UUID, request: Request, slcm_mode: str = Query("strategy", pattern="^(strategy|per_control)$"),
          db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("implementation.write"))) -> dict:
    enforce(request, current, "implementation.write", system_id)
    imp = _imp(db, system_id, import_id)
    allowed = _allowed(current, system_id)
    bad = {i.get("section", "Controls") for i in imp.items or [] for f in i["fields"].values() if f.get("decision") == "accept" and i.get("section", "Controls") not in allowed}
    if bad:
        raise HTTPException(403, f"Accepted changes in sections you cannot apply: {', '.join(sorted(bad))}")
    imp.report = {**(imp.report or {}), "slcm_mode": slcm_mode}
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
from app.services import emass_migration as em  # noqa: E402


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
    imp = ei.store(db, current.user.org_id, None, name, data, current.user, er.route_type(det), det)
    audit.record(db, action="emass.import_uploaded", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="emass_import",
                 entity_id=str(imp.id), after={"file_name": imp.file_name, "sha256": imp.sha256, "detected_type": det["type"], "confidence": det["confidence"]},
                 **audit.request_meta(request))
    db.commit()
    return _view(imp, current)


class TargetIn(BaseModel):
    action: str = Field(pattern="^(update|register|cancel)$")
    system_id: uuid.UUID | None = None
    report_type: str | None = Field(None, pattern="^(system_details|control_information|test_results|poam|hwsw|slcm|categorization|ppsm)$")


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
    return {"items": [ei.out(i) for i in db.scalars(q.order_by(EmassImport.created_at.desc()).limit(200))], "types": er.TYPES,
            "migration_types": er.MIGRATION_TYPES, "deferred": em.DEFERRED, "ai_enabled": em.ai_enabled(db, current.user.org_id)}


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
    if report_type in em.TYPES:
        rows = None
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
    ei.decide(db, imp, [d.model_dump() for d in body.decisions], body.bulk, allowed, body.section)
    db.commit()
    return _view(imp, current)


@router.post("/emass-imports/{import_id}/apply")
def generic_apply(import_id: uuid.UUID, request: Request, slcm_mode: str = Query("strategy", pattern="^(strategy|per_control)$"),
                  db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    imp = _org_imp(db, import_id, current, request)
    allowed = _allowed(current, imp.system_id) if imp.system_id else set()
    if not imp.system_id or not allowed:
        raise HTTPException(403, "Your role cannot apply this import")
    bad = {i["section"] for i in imp.items or [] for f in i["fields"].values() if f.get("decision") == "accept" and i.get("section", "Controls") not in allowed}
    if bad:
        raise HTTPException(403, f"Accepted changes in sections you cannot apply: {', '.join(sorted(bad))}")
    imp.report = {**(imp.report or {}), "slcm_mode": slcm_mode}
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


class RevertIn(BaseModel):
    keys: list[str] | None = Field(None, max_length=20000, description="Item keys to revert; omitted = the whole session")


@router.post("/emass-imports/{import_id}/revert")
def generic_revert(import_id: uuid.UUID, body: RevertIn, request: Request, db: Session = Depends(get_db),
                   current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    """Undo applied SLCM / Categorization / PPSM changes of one session (or some items): before values restored, audited."""
    imp = _org_imp(db, import_id, current, request)
    if imp.status != "applied" or imp.report_type not in em.TYPES:
        raise HTTPException(409, "Only an applied SLCM, Categorization or PPSM import can be reverted")
    allowed = _allowed(current, imp.system_id)
    if not {i.get("section") for i in imp.items or []} <= allowed:
        raise HTTPException(403, "Your role cannot revert this import")
    done = em.revert(db, imp, current, audit.request_meta(request), body.keys)
    audit.record(db, action="emass.import_reverted", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="emass_import",
                 entity_id=str(imp.id), after={"reverted": len(done), "status": imp.status}, details={"file_name": imp.file_name, "sha256": imp.sha256},
                 **audit.request_meta(request))
    db.commit()
    return {**_view(imp, current), "reverted": done}


class AiIn(BaseModel):
    enabled: bool


@router.get("/emass-import-settings/ai")
def ai_get(db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    from app.services.ai.service import get_ai_service
    return {"enabled": em.ai_enabled(db, current.user.org_id), "provider_configured": get_ai_service().configured,
            "notice": "When on, unrecognised column headers and up to 3 redacted sample values per column may be sent to the configured "
                      "OpenRouter AI provider. Names, e-mails, phone numbers, IP addresses and host names are removed first. AI only suggests "
                      "column mappings – it never creates assessments, statuses or evidence and never approves anything."}


@router.put("/emass-import-settings/ai")
def ai_put(body: AiIn, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("emass.admin"))) -> dict:
    from app.services import rmf
    before = em.ai_enabled(db, current.user.org_id)
    rmf.set_setting(db, current.user.org_id, "emass_ai", {"enabled": body.enabled})
    audit.record(db, action="admin.emass_ai_updated", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="setting",
                 entity_id="emass_ai", before={"enabled": before}, after={"enabled": body.enabled}, **audit.request_meta(request))
    db.commit()
    return ai_get(db, current)


@router.get("/systems/{system_id}/ppsm")
def ppsm(system_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    enforce(request, current, "system.read", system_id)
    return {"items": em.ppsm_list(db, get_system(db, system_id))}


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@router.get("/systems/{system_id}/emass-exports/{kind}")
def export(system_id: uuid.UUID, kind: str, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))):
    """eMASS-layout exports for round trips (formula injection neutralized)."""
    if kind not in ("slcm", "ppsm"):
        raise HTTPException(404, "Unknown export")
    enforce(request, current, "system.read", system_id)
    s = get_system(db, system_id)
    data = em.slcm_export(db, s) if kind == "slcm" else em.ppsm_export(db, s)
    audit.record(db, action="emass.exported", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system", entity_id=str(s.id),
                 after={"kind": kind, "bytes": len(data)}, **audit.request_meta(request))
    db.commit()
    name = "SLCM_Final_Results" if kind == "slcm" else "PPSMBoundariesInformationExport"
    return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{s.acronym or "system"}_{name}.xlsx"'})


@router.get("/systems/{system_id}/setup-template")
def setup_template(system_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    enforce(request, current, "system.read", system_id)
    s = get_system(db, system_id)
    if s.org_id != current.user.org_id:
        raise HTTPException(404, "System not found")
    return em.setup_template(s)


class CopyIn(BaseModel):
    source_system_id: uuid.UUID


@router.post("/systems/{system_id}/copy-setup")
def copy_setup(system_id: uuid.UUID, body: CopyIn, request: Request, db: Session = Depends(get_db),
               current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    """Copy baseline-related setup (overlays, tailoring, ODPs, ISCM strategy/profiles, policy links) from a same-org system the user can read.
    Never copies assessments, evidence, POA&Ms, test results, approvals or inventory."""
    enforce(request, current, "system.write", system_id)
    enforce(request, current, "system.read", body.source_system_id)
    dst, src = get_system(db, system_id), get_system(db, body.source_system_id)
    if src.org_id != current.user.org_id or dst.org_id != current.user.org_id or src.id == dst.id:
        raise HTTPException(404, "System not found")
    out = em.copy_setup(db, src, dst, current.user)
    db.commit()
    return out


def _steps(t: str, sid) -> list[dict]:
    m = {"system_details": [("Prepare", "/rmf/prepare"), ("Categorize", "/rmf/categorize")],
         "categorization": [("Categorize", "/rmf/categorize"), ("Select", "/rmf/select")],
         "slcm": [("Select – S-5 monitoring strategy", "/rmf/select"), ("Monitor", "/rmf/monitor")],
         "test_results": [("Assess", "/rmf/assess"), ("Test Results", "/test-results")],
         "hwsw": [("Inventory", "/inventory"), ("Prepare – boundary", "/rmf/prepare")],
         "ppsm": [("PPSM boundary table", f"/systems/{sid}/emass-import#ppsm"), ("Prepare – boundary", "/rmf/prepare")]}
    return [{"label": a, "to": b} for a, b in m.get(t, [])]


@router.get("/systems/{system_id}/migration-report")
def migration_report(system_id: uuid.UUID, request: Request, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    """Completion report of an eMASS migration: every import session of the system, what was applied, what is left in the exception queue."""
    enforce(request, current, "system.read", system_id)
    s = get_system(db, system_id)
    rows = list(db.scalars(select(EmassImport).where(EmassImport.system_id == system_id).order_by(EmassImport.created_at.desc())))
    sessions = []
    for i in rows:
        r = i.report or {}
        exc = {k: len(r.get(k) or []) for k in ("not_in_system", "invalid", "duplicates", "exceptions", "required_issues")}
        sessions.append({**ei.out(i), "exceptions": exc, "exception_total": sum(exc.values()),
                         "failed": sum(1 for x in r.get("apply_results") or [] if x.get("failed")), "reverted": len(r.get("reverted_keys") or []),
                         "deferred": i.report_type in em.DEFERRED, "steps": _steps(i.report_type, system_id)})
    cover = []
    for t in er.MIGRATION_TYPES:
        mine = [x for x in sessions if x["report_type"] == t]
        st = "applied" if any(x["status"] == "applied" for x in mine) else ("in review" if any(x["status"] == "review" for x in mine) else "not imported")
        cover.append({"type": t, "label": er.TYPES[t], "status": st, "steps": _steps(t, system_id),
                      "applied_fields": sum((x["counts"] or {}).get("applied_fields") or 0 for x in mine if x["status"] == "applied")})
    base = f"/api/v1/systems/{system_id}"
    exports = [{"type": "control_information", "label": "eMASS Implementation Plan (.xlsx)", "href": f"{base}/emass/implementation-plan.xlsx"},
               {"type": "slcm", "label": "eMASS SLCM worksheet – Final Results (.xlsx)", "href": f"{base}/emass-exports/slcm"},
               {"type": "ppsm", "label": "eMASS PPSM Boundaries export (.xlsx)", "href": f"{base}/emass-exports/ppsm"}]
    return {"system": {"id": str(s.id), "name": s.name, "acronym": s.acronym}, "coverage": cover, "sessions": sessions, "exports": exports,
            "deferred": [{"type": k, "label": v, "note": "Deferred – existing parser kept working; not part of the migration wizard yet"} for k, v in em.DEFERRED.items()]}
