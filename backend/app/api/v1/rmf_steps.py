"""RMF 7-step API: step status + next action, Prepare roles, Categorize (FIPS 199 / CNSSI 1253), Select (baseline/overlays/tailoring)."""
import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.records import get_system, to_dict
from app.db import get_db
from app.models import Overlay, TailoringDecision, User
from app.security.deps import CurrentUser, get_current_user, require_permission
from app.services import audit
from app.services import rmf_steps as rs
from app.services.counts import system_counts

router = APIRouter(tags=["rmf-steps"])


def _err(fn, *a):
    try:
        return fn(*a)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


@router.get("/reference/rmf")
def rmf_reference(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    users = db.scalars(select(User).where(User.org_id == current.user.org_id).order_by(User.display_name))
    return {"key_roles": [{"key": k, "label": l, "help": h, "required": r} for k, l, h, r in rs.KEY_ROLES],
            "users": [{"id": str(u.id), "display_name": u.display_name, "email": u.email} for u in users],
            "emass_note": rs.EMASS,
            "mission_criticality": [{"value": v, "label": l, "help": h} for v, l, h in rs.MISSION_CRITICALITY],
            "system_types": [{"value": v, "help": h} for v, h in rs.SYSTEM_TYPES],
            "acquisition_categories": [{"value": v, "help": h} for v, h in rs.ACQUISITION_CATEGORIES],
            "authorization_types": [{"value": v, "help": h} for v, h in rs.AUTHORIZATION_TYPES],
            "environments": [{"value": v, "label": l, "cloud": c} for v, l, c in rs.ENVIRONMENTS]}


@router.get("/reference/role-matrix")
def role_matrix(_: CurrentUser = Depends(get_current_user)) -> dict:
    from app.security.rbac import PERMISSIONS, ROLE_PERMISSIONS, ROLES

    return {"roles": [{"key": k, "label": v} for k, v in ROLES.items()],
            "actions": [{"permission": p, "action": rs.ACTION_LABELS.get(p, d), "description": d,
                         "roles": [r for r in ROLES if p in ROLE_PERMISSIONS.get(r, set())]} for p, d in PERMISSIONS.items()]}


@router.get("/reference/info-types")
def info_types(_: CurrentUser = Depends(get_current_user)) -> dict:
    return rs.info_type_catalog()


class CategorizeIn(BaseModel):
    mode: str = Field("fips199", pattern="^(fips199|cnssi1253)$")
    information_types: list[dict] = []
    cia: dict | None = None


@router.post("/reference/categorize")
def categorize_preview(body: CategorizeIn, _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    return rs.categorize(body.mode, body.information_types, body.cia)


@router.get("/systems/{system_id}/rmf-steps")
def rmf_steps(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    return rs.steps(db, get_system(db, system_id))


class RolesIn(BaseModel):
    roles: dict


@router.get("/systems/{system_id}/prepare")
def prepare_view(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    return {"roles": rs.role_holders(db, get_system(db, system_id))}


@router.put("/systems/{system_id}/prepare")
def prepare_save(system_id: uuid.UUID, body: RolesIn, db: Session = Depends(get_db),
                 current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    out = _err(rs.save_roles, db, get_system(db, system_id), body.roles, current.user)
    db.commit()
    return {"roles": out}


class CategorizationIn(CategorizeIn):
    mission_criticality: str | None = Field(None, max_length=50)
    system_type: str | None = Field(None, max_length=80)
    acquisition_category: str | None = Field(None, max_length=40)
    authorization_type: str | None = Field(None, max_length=50)
    operating_environment: str | None = Field(None, max_length=100)
    environment_detail: dict | None = None
    processes_pii: bool | None = None
    pta: dict | None = None


def apply_categorization(s, body: CategorizationIn) -> dict:
    calc = rs.categorize(body.mode, body.information_types, body.cia)
    if calc["errors"]:
        raise ValueError("; ".join(calc["errors"]))
    if not calc["rows"]:
        raise ValueError("Pick at least one information type from the SP 800-60 catalog")
    s.categorization_mode = body.mode
    s.information_types = [{k: r[k] for k in ("id", "name", "c", "i", "a", "rationale", "adjusted")} for r in calc["rows"]]
    s.confidentiality_impact, s.integrity_impact, s.availability_impact = calc["c"], calc["i"], calc["a"]
    s.categorization = calc["overall"].lower() if calc["overall"] else None
    s.categorization_detail = {"steps": calc["steps"], "security_category": calc["security_category"], "baseline": calc["baseline"]}
    for f in ("mission_criticality", "system_type", "acquisition_category", "authorization_type", "operating_environment", "environment_detail",
              "processes_pii", "pta"):
        v = getattr(body, f)
        if v is not None:
            setattr(s, f, v)
    return calc


@router.get("/systems/{system_id}/categorization")
def categorization_view(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    s = get_system(db, system_id)
    keep = ("categorization_mode", "information_types", "confidentiality_impact", "integrity_impact", "availability_impact", "categorization",
            "categorization_detail", "mission_criticality", "system_type", "acquisition_category", "authorization_type", "operating_environment",
            "environment_detail", "processes_pii", "pta", "baseline_key", "include_privacy")
    return {k: getattr(s, k) for k in keep}


@router.put("/systems/{system_id}/categorization")
def categorization_save(system_id: uuid.UUID, body: CategorizationIn, db: Session = Depends(get_db),
                        current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    s = get_system(db, system_id)
    before = {"categorization": s.categorization, "c": s.confidentiality_impact, "i": s.integrity_impact, "a": s.availability_impact}
    calc = _err(apply_categorization, s, body)
    audit.record(db, action="system.categorized", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system",
                 entity_id=str(s.id), before=before, after={"mode": body.mode, "c": calc["c"], "i": calc["i"], "a": calc["a"],
                                                            "information_types": [r["id"] for r in calc["rows"]], "processes_pii": s.processes_pii})
    db.commit()
    needs = []
    if calc["baseline"] and rs.LEVEL.get(calc["baseline"], 0) > rs.LEVEL.get(s.baseline_key or "", 0):
        needs.append(f"raise the baseline from {s.baseline_key} to {calc['baseline']}")
    if s.processes_pii and not s.include_privacy:
        needs.append("apply the privacy baseline")
    return {"calculation": calc, "select_actions": needs}


@router.get("/systems/{system_id}/select")
def select_view(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    s = get_system(db, system_id)
    rs.ensure_overlays(db)
    db.commit()
    ovs = {}
    for o in db.scalars(select(Overlay).where(Overlay.is_active.is_(True)).order_by(Overlay.overlay_key, Overlay.created_at)):
        ovs[o.overlay_key] = o
    return {"baseline_key": s.baseline_key, "recommended_baseline": (s.categorization or "").lower() or None, "include_privacy": s.include_privacy,
            "processes_pii": s.processes_pii, "overlay_keys": s.overlay_keys or [], "counts": system_counts(db, s),
            "overlays": [{"key": o.overlay_key, "title": o.title, "version": o.version, "structure_only": o.structure_only, "description": o.description,
                          "add": len(o.controls_add), "remove": len(o.controls_remove), "synthetic": o.is_synthetic,
                          "applied": o.overlay_key in (s.overlay_keys or [])} for o in ovs.values()],
            "tailoring": [to_dict(t) for t in db.scalars(select(TailoringDecision).where(TailoringDecision.system_id == s.id)
                                                         .order_by(TailoringDecision.created_at.desc()))]}


class BaselineIn(BaseModel):
    baseline_key: str = Field(pattern="^(low|moderate|high)$")
    include_privacy: bool = False


@router.post("/systems/{system_id}/select/baseline")
def select_baseline(system_id: uuid.UUID, body: BaselineIn, db: Session = Depends(get_db),
                    current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    s = get_system(db, system_id)
    out = _err(rs.apply_baseline, db, s, body.baseline_key, body.include_privacy, current.user)
    db.commit()
    return {**out, "counts": system_counts(db, s)}


class OverlayIn(BaseModel):
    overlay_key: str = Field(max_length=100)
    apply: bool


@router.post("/systems/{system_id}/select/overlay")
def select_overlay(system_id: uuid.UUID, body: OverlayIn, db: Session = Depends(get_db),
                   current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    s = get_system(db, system_id)
    out = _err(rs.set_overlay, db, s, body.overlay_key, body.apply, current.user)
    db.commit()
    return {**out, "counts": system_counts(db, s)}


class TailorIn(BaseModel):
    action: str = Field(pattern="^(add|remove)$")
    control_ids: list[str] = Field(min_length=1, max_length=1500)
    justification: str = Field("", max_length=4000)


@router.post("/systems/{system_id}/select/tailor")
def select_tailor(system_id: uuid.UUID, body: TailorIn, db: Session = Depends(get_db),
                  current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    s = get_system(db, system_id)
    out = _err(rs.tailor, db, s, body.action, body.control_ids, body.justification, current.user)
    db.commit()
    return {**out, "counts": system_counts(db, s)}


@router.post("/overlays/{overlay_key}/import", status_code=201)
async def overlay_import(overlay_key: str, version: str = Form(..., min_length=1, max_length=20), file: UploadFile = File(...),
                         db: Session = Depends(get_db), current: CurrentUser = Depends(require_permission("admin.content.load"))) -> dict:
    ov = _err(rs.import_overlay_csv, db, overlay_key, version, await file.read(), current.user)
    db.commit()
    return {"overlay_key": ov.overlay_key, "version": ov.version, "add": len(ov.controls_add), "remove": len(ov.controls_remove)}


@router.get("/systems/{system_id}/authorize")
def authorize_view(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    s = get_system(db, system_id)
    return {"checklist": rs.authorization_checklist(db, s), "authorization_status": s.authorization_status,
            "authorization_type": s.authorization_type, "authorization_expiration": s.authorization_expiration}


@router.get("/systems/{system_id}/traceability")
def traceability(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> list[dict]:
    return rs.traceability(db, get_system(db, system_id))
