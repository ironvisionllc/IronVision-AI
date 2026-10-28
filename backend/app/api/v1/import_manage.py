"""Manage imported data (Import Center): view and selectively restore / clear / delete what an applied eMASS import changed."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.emass_import import _allowed, _org_imp
from app.api.v1.records import get_system
from app.db import get_db
from app.models import EmassImport
from app.security.deps import CurrentUser, require_permission
from app.services import audit
from app.services import import_manage as im

router = APIRouter(tags=["import-manage"])
SECTION_OF = {"Registration (System Details)": "System details", "Implementation Plan": "Controls", "Risk Assessment": "Controls", "Implementation statement": "Controls",
              "SLCM (Continuous Monitoring)": "SLCM", "Continuous Monitoring Strategy": "SLCM", "PPSM": "PPSM", "Categorization": "Categorization"}


def _view(db: Session, imp: EmassImport, current: CurrentUser) -> dict:
    from app.services import emass_import as ei
    allowed = _allowed(current, imp.system_id) if imp.system_id else set()
    es = im.entries(db, imp)
    for e in es:
        if SECTION_OF.get(e["destination"]) not in allowed:
            e["actions"], e["read_only"] = [], f"Your role cannot change {e['destination']}"
    groups: dict[str, int] = {}
    for e in es:
        groups[e["destination"]] = groups.get(e["destination"], 0) + 1
    return {"import": ei.out(imp), "entries": es, "groups": groups, "log": (imp.report or {}).get("manage_log") or [], "undo_days": im.UNDO_DAYS}


@router.get("/systems/{system_id}/imported-data")
def list_imports(system_id: uuid.UUID, db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    from app.services import emass_import as ei
    s = get_system(db, system_id)
    rows = db.scalars(select(EmassImport).where(EmassImport.system_id == s.id, EmassImport.status.in_(("applied", "reverted", "registered")))
                      .order_by(EmassImport.created_at.desc()).limit(200)).all()
    return {"items": [{**ei.out(i), "manageable": len(im.entries(db, i))} for i in rows]}


@router.get("/emass-imports/{import_id}/manage")
def manage_view(import_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    return _view(db, _org_imp(db, import_id, current, request), current)


class ManageIn(BaseModel):
    action: str = Field(pattern="^(restore|clear|delete)$")
    ids: list[str] | None = Field(None, max_length=20000, description="Entry ids (key|field); omitted with all=true = the whole import")
    all: bool = False
    exclude: list[str] = Field(default_factory=list, max_length=20000)
    force: bool = Field(False, description="Overwrite fields that were changed after the import")


@router.post("/emass-imports/{import_id}/manage")
def manage_act(import_id: uuid.UUID, body: ManageIn, request: Request, db: Session = Depends(get_db),
               current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    imp = _org_imp(db, import_id, current, request)
    if imp.status not in ("applied", "reverted", "registered"):
        raise HTTPException(409, "Only an applied import has imported data to manage")
    v = _view(db, imp, current)
    pick = set(body.ids or [])
    pool = [e for e in v["entries"] if not e.get("read_only") and (body.action in e["actions"] if body.all else e["id"] in pick)]
    ro = [e for e in v["entries"] if e.get("read_only") and (body.all or e["id"] in pick)]
    if ro and not pool:
        raise HTTPException(403, ro[0]["read_only"])
    ids = [e["id"] for e in pool if e["id"] not in set(body.exclude)]
    if not ids:
        raise HTTPException(422, "Nothing selected")
    res = im.act(db, imp, current, audit.request_meta(request), ids, body.action, body.force)
    from app.services.evaluation import evaluate_system
    db.flush()
    evaluate_system(db, imp.system_id)
    db.commit()
    return {**_view(db, imp, current), **res}


@router.post("/emass-imports/{import_id}/manage/{op_id}/undo")
def manage_undo(import_id: uuid.UUID, op_id: str, request: Request, db: Session = Depends(get_db),
                current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    imp = _org_imp(db, import_id, current, request)
    if not _allowed(current, imp.system_id):
        raise HTTPException(403, "Your role cannot change imported data")
    res = im.undo(db, imp, current, audit.request_meta(request), op_id)
    from app.services.evaluation import evaluate_system
    db.flush()
    evaluate_system(db, imp.system_id)
    db.commit()
    return {**_view(db, imp, current), **res}


# ---------- every import type (Import Center history) ----------
from datetime import UTC, datetime

from app.models import ReviewFlag
from app.security.rbac import has_permission
from app.services import import_data as idm

KINDS = ("emass", "tr", "inventory", "ingest", "policy")


def _generic(db: Session, kind: str, import_id: uuid.UUID, current: CurrentUser, request: Request):
    if kind not in KINDS:
        raise HTTPException(404, "Unknown import type")
    if kind == "emass":
        return _org_imp(db, import_id, current, request)
    obj = idm.load(db, kind, import_id, current.user.org_id)
    sid = idm.system_of(obj)
    if sid:
        from app.api.v1.records import enforce
        enforce(request, current, "system.read", sid)
    return obj


def _gview(db: Session, kind: str, obj, current: CurrentUser) -> dict:
    if kind == "emass":
        v = _view(db, obj, current)
        return {**v, "kind": "emass", "flags": idm.flags(db, current.user.org_id, import_id=obj.id)}
    sid = idm.system_of(obj)
    can = has_permission(current.assignments, idm.KIND_PERM[kind], current.user.org_id, sid)
    es = idm.entries(db, kind, obj)
    if not can:
        for e in es:
            e["actions"], e["read_only"] = [], f"Your role cannot change {idm.KIND_LABEL[kind]} data"
    for t in idm.trashed(db, kind, obj.id):
        if t.restored_at is None and t.action == "delete":
            rec, _, lab = (t.label or "").partition(" – ")
            es.append({"id": t.entry_id, "record": rec, "label": lab, "destination": "Deleted", "field": "*", "prior": None, "imported": None,
                       "current": None, "created": True, "state": "deleted", "changed_since_import": False, "actions": []})
    groups: dict[str, int] = {}
    for e in es:
        groups[e["destination"]] = groups.get(e["destination"], 0) + 1
    return {"kind": kind, "import": idm.header(kind, obj), "entries": es, "groups": groups, "log": idm.log(db, kind, obj.id), "undo_days": idm.UNDO_DAYS,
            "flags": idm.flags(db, current.user.org_id, import_id=obj.id), "can_change": can}


@router.get("/imported-data/{import_kind}/{import_id}")
def any_view(import_kind: str, import_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
             current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    """One view of everything one import populated, grouped by section (any import type)."""
    return _gview(db, import_kind, _generic(db, import_kind, import_id, current, request), current)


class AnyIn(ManageIn):
    confirm_file: bool = Field(False, description="Second, explicit confirmation to remove an evidence FILE (links are removed without it)")


@router.post("/imported-data/{import_kind}/{import_id}")
def any_act(import_kind: str, import_id: uuid.UUID, body: AnyIn, request: Request, db: Session = Depends(get_db),
            current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    obj = _generic(db, import_kind, import_id, current, request)
    if import_kind == "emass":
        res = manage_act(import_id, body, request, db, current)
        return {**res, "kind": "emass", "flags": idm.flags(db, current.user.org_id, import_id=obj.id)}
    sid = idm.system_of(obj)
    if not has_permission(current.assignments, idm.KIND_PERM[import_kind], current.user.org_id, sid):
        raise HTTPException(403, f"Your role cannot change {idm.KIND_LABEL[import_kind]} data")
    es = idm.entries(db, import_kind, obj)
    pick = set(body.ids or [])
    ids = [e["id"] for e in es if (body.action in e["actions"] if body.all else e["id"] in pick) and e["id"] not in set(body.exclude)]
    if body.all and body.action == "delete" and import_kind == "policy":
        ids = [e["id"] for e in es if e["id"].startswith("policy|")]  # the whole policy (its mappings/coverage go with it)
    if body.all and not body.confirm_file:
        ids = [i for i in ids if not i.startswith("evidence_file|")]
    if not ids:
        raise HTTPException(422, "Nothing selected")
    res = idm.act(db, import_kind, obj, current, audit.request_meta(request), ids, body.action, body.force, body.confirm_file)
    if sid:
        from app.services.evaluation import evaluate_system
        db.flush()
        evaluate_system(db, sid)
    db.commit()
    return {**_gview(db, import_kind, obj, current), **res}


@router.post("/imported-data/{import_kind}/{import_id}/undo/{op_id}")
def any_undo(import_kind: str, import_id: uuid.UUID, op_id: str, request: Request, db: Session = Depends(get_db),
             current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    obj = _generic(db, import_kind, import_id, current, request)
    if import_kind == "emass":
        return manage_undo(import_id, op_id, request, db, current)
    sid = idm.system_of(obj)
    if not has_permission(current.assignments, idm.KIND_PERM[import_kind], current.user.org_id, sid):
        raise HTTPException(403, f"Your role cannot change {idm.KIND_LABEL[import_kind]} data")
    res = idm.undo(db, import_kind, obj, current, audit.request_meta(request), op_id)
    if sid:
        from app.services.evaluation import evaluate_system
        db.flush()
        evaluate_system(db, sid)
    db.commit()
    return {**_gview(db, import_kind, obj, current), **res}


@router.get("/systems/{system_id}/imported-data/index")
def imported_index(system_id: uuid.UUID, kind: str = Query(pattern="^(tr_row|asset|software|finding|ppsm|emass_field|strategy)$"),
                   db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    """'Imported from <file>' markers for a destination screen: entity id → import + entry id (row-level Delete)."""
    return {"items": idm.index(db, get_system(db, system_id), kind)}


@router.get("/systems/{system_id}/review-flags")
def review_flags(system_id: uuid.UUID, all: bool = False, db: Session = Depends(get_db),
                 current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    s = get_system(db, system_id)
    return {"items": idm.flags(db, current.user.org_id, system_id=s.id, open_only=not all)}


class ResolveIn(BaseModel):
    note: str = Field(min_length=3, max_length=2000)


@router.post("/review-flags/{flag_id}/resolve")
def resolve_flag(flag_id: uuid.UUID, body: ResolveIn, request: Request, db: Session = Depends(get_db),
                 current: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    f = db.get(ReviewFlag, flag_id)
    if f is None or f.org_id != current.user.org_id:
        raise HTTPException(404, "Flag not found")
    perm = idm.FLAG_PERM.get(f.entity_type, "system.write")
    if not has_permission(current.assignments, perm, current.user.org_id, f.system_id):
        raise HTTPException(403, f"Re-review needs the {perm} permission")
    if f.status != "open":
        raise HTTPException(409, "Already resolved")
    f.status, f.resolved_by, f.resolved_at, f.resolution = "resolved", current.user.email, datetime.now(UTC), body.note
    audit.record(db, action="review_flag.resolved", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="review_flag",
                 entity_id=str(f.id), after={"entity_type": f.entity_type, "entity_id": f.entity_id, "note": body.note}, **audit.request_meta(request))
    db.commit()
    return {"id": str(f.id), "status": f.status}


class RegisteredIn(BaseModel):
    system_id: uuid.UUID
    fields: dict = Field(default_factory=dict, description="Registration values pre-filled from the file (shown as imported)")


@router.post("/emass-imports/{import_id}/registered")
def registered(import_id: uuid.UUID, body: RegisteredIn, request: Request, db: Session = Depends(get_db),
               current: CurrentUser = Depends(require_permission("system.register"))) -> dict:
    """'Register a new system' path: link the import to the new system and record which registration values came from the file."""
    imp = _org_imp(db, import_id, current, request)
    s = get_system(db, body.system_id)
    if imp.status != "to_registration":
        raise HTTPException(409, f"This import is {imp.status}")
    keep = {k: v for k, v in body.fields.items() if k in ("name", "acronym", "emass_id", "description", "organization_name", "mission_owner")
            and v not in (None, "") and getattr(s, k, None) == v}
    imp.system_id, imp.status = s.id, "registered"
    imp.report = {**(imp.report or {}), "registration_prefill": keep}
    audit.record(db, action="emass.import_registered", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="emass_import",
                 entity_id=str(imp.id), after={"system_id": str(s.id), "fields": sorted(keep)}, **audit.request_meta(request))
    db.commit()
    return {"id": str(imp.id), "status": imp.status, "fields": sorted(keep)}
