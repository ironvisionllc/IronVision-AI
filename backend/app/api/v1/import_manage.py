"""Manage imported data (Import Center): view and selectively restore / clear / delete what an applied eMASS import changed."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
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
SECTION_OF = {"Implementation Plan": "Controls", "Risk Assessment": "Controls", "Implementation statement": "Controls",
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
    rows = db.scalars(select(EmassImport).where(EmassImport.system_id == s.id, EmassImport.status.in_(("applied", "reverted")))
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
    if imp.status not in ("applied", "reverted"):
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
