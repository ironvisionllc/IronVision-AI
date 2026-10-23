import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import (Asset, CommonControlProvider, ControlAssignment, Overlay, RoleAssignment, System, TailoringDecision, User)
from app.security.deps import CurrentUser, enforce, get_current_user, require_permission
from app.security.rbac import ROLES, has_permission
from app.services import audit
from app.services.evaluation import system_metrics
from app.services.systems import high_water_mark, register_system

router = APIRouter(tags=["systems"])
Impact = Field(None, pattern="^(Low|Moderate|High)$")


def to_dict(obj, exclude: tuple = ()) -> dict:
    return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs if c.key not in exclude}


def visible_systems(db: Session, current: CurrentUser) -> list[System]:
    rows = db.scalars(select(System).where(System.org_id == current.user.org_id).order_by(System.name))
    return [s for s in rows if has_permission(current.assignments, "system.read", current.user.org_id, s.id)]


def get_system(db: Session, system_id: uuid.UUID) -> System:
    s = db.get(System, system_id)
    if s is None:
        raise HTTPException(404, "System not found")
    return s


class Tailor(BaseModel):
    control_id: str = Field(max_length=50)
    action: str = Field(pattern="^(add|remove)$")
    justification: str = Field(min_length=5, max_length=2000)


class SystemBase(BaseModel):
    name: str | None = Field(None, min_length=2, max_length=255)
    acronym: str | None = Field(None, max_length=50)
    emass_id: str | None = Field(None, max_length=50)
    description: str | None = Field(None, max_length=5000)
    organization_name: str | None = Field(None, max_length=255)
    mission_owner: str | None = Field(None, max_length=255)
    system_owner_id: uuid.UUID | None = None
    isso_id: uuid.UUID | None = None
    issm_id: uuid.UUID | None = None
    ao_id: uuid.UUID | None = None
    operating_environment: str | None = Field(None, max_length=100)
    deployment_type: str | None = Field(None, max_length=100)
    boundary_description: str | None = Field(None, max_length=5000)
    lifecycle_phase: str | None = Field(None, pattern="^(Design|Build|Test|Onboard|Operations)$")
    authorization_status: str | None = Field(None, max_length=50)
    authorization_date: date | None = None
    authorization_expiration: date | None = None
    confidentiality_impact: str | None = Impact
    integrity_impact: str | None = Impact
    availability_impact: str | None = Impact
    information_types: list[dict] | None = None
    mission_criticality: str | None = Field(None, max_length=50)
    system_type: str | None = Field(None, max_length=80)
    acquisition_category: str | None = Field(None, max_length=40)
    authorization_type: str | None = Field(None, max_length=50)
    categorization_mode: str | None = Field(None, pattern="^(fips199|cnssi1253)$")
    environment_detail: dict | None = None
    processes_pii: bool | None = None
    pta: dict | None = None
    key_roles: dict | None = None


class SystemCreate(SystemBase):
    name: str = Field(min_length=2, max_length=255)
    baseline_key: str = Field(pattern="^(low|moderate|high)$")
    include_privacy: bool = False
    overlay_keys: list[str] = []
    tailoring: list[Tailor] = []
    provider_ids: list[uuid.UUID] | None = None


def _system_out(db, s: System) -> dict:
    d = to_dict(s)
    for f in ("system_owner_id", "isso_id", "issm_id", "ao_id"):
        u = db.get(User, d[f]) if d[f] else None
        d[f.replace("_id", "_name")] = u.display_name if u else None
    d["metrics"] = system_metrics(db, s)
    return d


@router.get("/systems")
def list_systems(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return [_system_out(db, s) for s in visible_systems(db, current)]


@router.post("/systems", status_code=201)
def create_system(body: SystemCreate, request: Request, db: Session = Depends(get_db),
                  current: CurrentUser = Depends(require_permission("system.register"))) -> dict:
    data = body.model_dump(exclude={"tailoring", "provider_ids", "key_roles"}, exclude_none=True)
    data.setdefault("lifecycle_phase", "Design")
    if body.information_types:
        from app.services.rmf_steps import categorize

        calc = categorize(body.categorization_mode or "fips199", body.information_types,
                          {"c": body.confidentiality_impact, "i": body.integrity_impact, "a": body.availability_impact})
        if calc["errors"]:
            raise HTTPException(422, "; ".join(calc["errors"]))
        data.update(information_types=[{k: r[k] for k in ("id", "name", "c", "i", "a", "rationale", "adjusted")} for r in calc["rows"]],
                    confidentiality_impact=calc["c"], integrity_impact=calc["i"], availability_impact=calc["a"],
                    categorization_detail={"steps": calc["steps"], "security_category": calc["security_category"], "baseline": calc["baseline"]})
    try:
        s = register_system(db, {**data, "org_id": current.user.org_id, "is_synthetic": True, "source": "ui"},
                            [t.model_dump() for t in body.tailoring], body.provider_ids, current.user.id, current.user.email)
        if body.key_roles:
            from app.services.rmf_steps import save_roles

            save_roles(db, s, body.key_roles, current.user)
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc))
    db.commit()
    return _system_out(db, s)


@router.get("/systems/{system_id}")
def system_detail(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> dict:
    s = get_system(db, system_id)
    out = _system_out(db, s)
    out["tailoring"] = [to_dict(t) for t in db.scalars(select(TailoringDecision).where(TailoringDecision.system_id == s.id))]
    return out


@router.patch("/systems/{system_id}")
def update_system(system_id: uuid.UUID, body: SystemBase, request: Request, db: Session = Depends(get_db),
                  current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    s = get_system(db, system_id)
    changes = body.model_dump(exclude_unset=True)
    before = {k: getattr(s, k) for k in changes}
    for k, v in changes.items():
        setattr(s, k, v)
    s.categorization = high_water_mark(s.confidentiality_impact, s.integrity_impact, s.availability_impact)
    audit.record(db, action="system.updated", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system",
                 entity_id=str(s.id), before=before, after=changes, **audit.request_meta(request))
    db.commit()
    return _system_out(db, s)


class AssetIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    hostname: str | None = Field(None, max_length=255)
    ip_address: str | None = Field(None, max_length=64)
    cloud_resource_id: str | None = Field(None, max_length=500)
    os: str | None = Field(None, max_length=255)
    software_components: list[dict] | None = None
    asset_type: str | None = Field(None, max_length=100)
    criticality: str | None = Field(None, max_length=30)
    network_zone: str | None = Field(None, max_length=100)
    environment: str | None = Field(None, max_length=50)
    inventory_source: str | None = Field("manual", max_length=100)
    review_status: str | None = Field(None, pattern="^(confirmed|needs_review)$")


@router.get("/systems/{system_id}/assets")
def list_assets(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> list[dict]:
    return [to_dict(a) for a in db.scalars(select(Asset).where(Asset.system_id == system_id).order_by(Asset.is_unmatched.desc(), Asset.name))]


@router.post("/systems/{system_id}/assets", status_code=201)
def create_asset(system_id: uuid.UUID, body: AssetIn, db: Session = Depends(get_db),
                 current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    a = Asset(system_id=get_system(db, system_id).id, **body.model_dump(exclude_none=True))
    db.add(a)
    db.flush()
    audit.record(db, action="asset.created", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="asset",
                 entity_id=str(a.id), after=body.model_dump(mode="json"))
    db.commit()
    return to_dict(a)


@router.patch("/systems/{system_id}/assets/{asset_id}")
def update_asset(system_id: uuid.UUID, asset_id: uuid.UUID, body: AssetIn, db: Session = Depends(get_db),
                 current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    a = db.get(Asset, asset_id)
    if a is None or a.system_id != system_id:
        raise HTTPException(404, "Asset not found")
    changes = body.model_dump(exclude_unset=True)
    for k, v in changes.items():
        setattr(a, k, v)
    if a.review_status == "confirmed":
        a.is_unmatched = False
    audit.record(db, action="asset.updated", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="asset",
                 entity_id=str(a.id), after=body.model_dump(mode="json", exclude_unset=True))
    db.commit()
    return to_dict(a)


@router.delete("/systems/{system_id}/assets/{asset_id}", status_code=204)
def delete_asset(system_id: uuid.UUID, asset_id: uuid.UUID, db: Session = Depends(get_db),
                 current: CurrentUser = Depends(require_permission("system.write"))) -> None:
    a = db.get(Asset, asset_id)
    if a is None or a.system_id != system_id:
        raise HTTPException(404, "Asset not found")
    audit.record(db, action="asset.deleted", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="asset",
                 entity_id=str(a.id), before={"name": a.name, "hostname": a.hostname})
    db.delete(a)
    db.commit()


class RoleIn(BaseModel):
    user_id: uuid.UUID
    role: str = Field(max_length=50)


@router.get("/systems/{system_id}/roles")
def list_roles(system_id: uuid.UUID, db: Session = Depends(get_db), _: CurrentUser = Depends(require_permission("system.read"))) -> list[dict]:
    rows = db.execute(select(RoleAssignment, User.email, User.display_name).join(User, User.id == RoleAssignment.user_id)
                      .where(RoleAssignment.scope_type == "system", RoleAssignment.scope_id == system_id)).all()
    return [{**to_dict(r), "email": e, "display_name": n} for r, e, n in rows]


@router.post("/systems/{system_id}/roles", status_code=201)
def grant_role(system_id: uuid.UUID, body: RoleIn, request: Request, db: Session = Depends(get_db),
               current: CurrentUser = Depends(require_permission("system.roles.manage"))) -> dict:
    if body.role not in ROLES:
        raise HTTPException(422, "Unknown role")
    get_system(db, system_id)
    if db.scalar(select(RoleAssignment.id).where(RoleAssignment.user_id == body.user_id, RoleAssignment.role == body.role,
                                                 RoleAssignment.scope_type == "system", RoleAssignment.scope_id == system_id)):
        raise HTTPException(409, "Role already assigned")
    ra = RoleAssignment(user_id=body.user_id, role=body.role, scope_type="system", scope_id=system_id, granted_by=current.user.id, source="ui")
    db.add(ra)
    db.flush()
    audit.record(db, action="role.granted", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="role_assignment",
                 entity_id=str(ra.id), after={"user_id": str(body.user_id), "role": body.role, "system_id": str(system_id)},
                 **audit.request_meta(request))
    db.commit()
    return to_dict(ra)


@router.delete("/systems/{system_id}/roles/{assignment_id}", status_code=204)
def revoke_role(system_id: uuid.UUID, assignment_id: uuid.UUID, request: Request, db: Session = Depends(get_db),
                current: CurrentUser = Depends(require_permission("system.roles.manage"))) -> None:
    ra = db.get(RoleAssignment, assignment_id)
    if ra is None or ra.scope_id != system_id:
        raise HTTPException(404, "Role assignment not found")
    audit.record(db, action="role.revoked", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="role_assignment",
                 entity_id=str(ra.id), before={"user_id": str(ra.user_id), "role": ra.role, "system_id": str(system_id)},
                 **audit.request_meta(request))
    db.delete(ra)
    db.commit()


@router.get("/reference/registration")
def registration_reference(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    users = db.scalars(select(User).where(User.org_id == current.user.org_id).order_by(User.display_name))
    return {
        "users": [{"id": u.id, "display_name": u.display_name, "email": u.email} for u in users],
        "overlays": [to_dict(o) for o in db.scalars(select(Overlay).where(Overlay.is_active.is_(True)))],
        "providers": [to_dict(p) for p in db.scalars(select(CommonControlProvider).where(CommonControlProvider.org_id == current.user.org_id))],
        "roles": ROLES,
    }


def assignment_for(db: Session, system_id: uuid.UUID, control_id: str) -> ControlAssignment:
    a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == system_id, ControlAssignment.control_id == control_id.lower()))
    if a is None:
        raise HTTPException(404, "Control not assigned to this system")
    return a


__all__ = ["router", "to_dict", "get_system", "assignment_for", "enforce", "visible_systems"]
