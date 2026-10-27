import uuid
from datetime import date
from typing import Literal

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
OperatingEnvironment = Literal["on_prem_gov", "contractor", "cloud_iaas", "cloud_paas", "cloud_saas", "hybrid", "tactical", "other"]  # = rmf_steps.ENVIRONMENTS


def to_dict(obj, exclude: tuple = ()) -> dict:
    return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs if c.key not in exclude}


def visible_systems(db: Session, current: CurrentUser, include_archived: bool = False) -> list[System]:
    q = select(System).where(System.org_id == current.user.org_id).order_by(System.name)
    if not include_archived:
        q = q.where(System.archived_at.is_(None))
    return [s for s in db.scalars(q) if has_permission(current.assignments, "system.read", current.user.org_id, s.id)]


def get_system(db: Session, system_id: uuid.UUID) -> System:
    s = db.get(System, system_id)
    if s is None:
        raise HTTPException(404, "System not found")
    return s


class AuthStrategyIn(BaseModel):
    authorization_type: str | None = Field(None, max_length=50, description="Authorization type sought (ATO, IATT, ATO with conditions …); null clears it.")
    justification: str = Field(min_length=5, max_length=2000)


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
    operating_environment: OperatingEnvironment | None = Field(None, description="Hosting environment; SRG impact levels apply only to cloud_iaas, cloud_paas, cloud_saas and hybrid.")
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
    nss_determination: str | None = Field(None, pattern="^(yes|no|unsure)$")
    classified_information: str | None = Field(None, pattern="^(yes|no|unknown)$")


def _registration_role_errors(roles: dict | None) -> list[str]:
    from app.services.rmf_steps import NOT_AT_REGISTRATION, ROLE_ALIASES, ROLE_KEYS, unknown_role_keys

    roles = roles or {}
    out = [REMOVED_ROLE_MSG[c] for c in NOT_AT_REGISTRATION
           if any(ROLE_ALIASES.get(k, k) == c and (v or k in ROLE_ALIASES) for k, v in roles.items())]
    unknown = unknown_role_keys(roles)
    if unknown:
        out.append(f"Unknown role key(s): {', '.join(unknown)}.")
    if out:
        out.append(f"Allowed at registration: {', '.join(k for k in ROLE_KEYS if k not in NOT_AT_REGISTRATION)}.")
    return out


REMOVED_ROLE_MSG = {"aodr": "AODR cannot be assigned at system registration – assign AODR under Authorize.",
                    "ccp": "Common Control Provider (CCP) cannot be assigned at system registration – assign CCP under Inheritance providers.",
                    "user_rep": "User Representative isn't assigned in this app's registration."}


def _check_impact_level(env, detail, framework, classified) -> None:
    from app.services.rmf_accuracy import validate_environment

    try:
        validate_environment(env, detail, framework, classified)
    except ValueError as exc:
        raise HTTPException(422, str(exc))


def _system_out(db, s: System) -> dict:
    d = to_dict(s)
    for f in ("system_owner_id", "isso_id", "issm_id", "ao_id"):
        u = db.get(User, d[f]) if d[f] else None
        d[f.replace("_id", "_name")] = u.display_name if u else None
    d["metrics"] = system_metrics(db, s)
    return d


@router.get("/systems")
def list_systems(include_archived: bool = False, db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> list[dict]:
    return [_system_out(db, s) for s in visible_systems(db, current, include_archived)]


@router.post("/systems", status_code=201)
def create_system(body: SystemCreate, request: Request, db: Session = Depends(get_db),
                  current: CurrentUser = Depends(require_permission("system.register"))) -> dict:
    errs = _registration_role_errors(body.key_roles)
    if errs:
        raise HTTPException(422, " ".join(errs))
    if body.authorization_type:
        raise HTTPException(422, "Authorization type sought is set in 6 · Authorize (authorization strategy), not at registration.")
    _check_impact_level(body.operating_environment, body.environment_detail, body.categorization_mode or "fips199", body.classified_information)
    data = body.model_dump(exclude={"tailoring", "provider_ids", "key_roles", "classified_information", "pta"}, exclude_none=True)
    if body.processes_pii is not None and (body.categorization_mode or "fips199") != "cnssi1253":
        data["include_privacy"] = body.processes_pii  # FIPS 199: Yes = SP 800-53B privacy baseline, added at registration
    if body.classified_information:
        data["applicability_flags"] = {"classified_information": body.classified_information}
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
        if body.processes_pii is not None:  # Yes adds the privacy controls now (NSS: Privacy Overlay variant for the impact level)
            from app.services import pii

            pii.set_pii(db, s, body.processes_pii, current.user, "registration")
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc))
    if s.information_types:
        from app.services import rmf_accuracy as ra
        from app.services.rmf_steps import categorize

        try:
            ra.record(db, s, categorize(s.categorization_mode or "fips199", [{k: t.get(k) for k in ("id", "c", "i", "a", "rationale")} for t in s.information_types],
                                        {"c": s.confidentiality_impact, "i": s.integrity_impact, "a": s.availability_impact}), s.categorization_mode or "fips199",
                      s.nss_determination, None, current.user.email)
        except (ValueError, KeyError):
            pass  # registration without a computable categorization: the first save in Categorize creates revision 1
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
    new_pii = changes.pop("processes_pii", None)  # PII Yes/No goes through the privacy path (adds/removes the overlay, audited)
    changes.pop("pta", None)  # PTA questionnaire retired: existing answers stay read-only
    old_env, old_il = s.operating_environment, (s.environment_detail or {}).get("impact_level")
    new_env = changes.get("operating_environment", old_env)
    new_det = changes["environment_detail"] if "environment_detail" in changes else s.environment_detail
    if (new_env, (new_det or {}).get("impact_level")) != (old_env, old_il):  # unchanged legacy values stay, flagged for review
        _check_impact_level(new_env, new_det, changes.get("categorization_mode", s.categorization_mode),
                            (s.applicability_flags or {}).get("classified_information"))
    before = {k: getattr(s, k) for k in changes}
    for k, v in changes.items():
        setattr(s, k, v)
    s.categorization = high_water_mark(s.confidentiality_impact, s.integrity_impact, s.availability_impact)
    if new_pii is not None and new_pii != s.processes_pii:
        from app.services import pii
        try:
            pii.set_pii(db, s, new_pii, current.user, "system_details")
        except ValueError as exc:
            db.rollback()
            raise HTTPException(422, str(exc))
    audit.record(db, action="system.updated", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system",
                 entity_id=str(s.id), before=before, after=changes, **audit.request_meta(request))
    db.commit()
    return _system_out(db, s)


class ArchiveIn(BaseModel):
    reason: str = Field(min_length=5, max_length=2000)


@router.post("/systems/{system_id}/archive")
def archive_system(system_id: uuid.UUID, body: ArchiveIn, request: Request, db: Session = Depends(get_db),
                   current: CurrentUser = Depends(require_permission("system.register"))) -> dict:
    """Logical archive: nothing is deleted; the system leaves active lists and can be restored."""
    s = get_system(db, system_id)
    if s.archived_at:
        raise HTTPException(409, "System is already archived")
    from datetime import datetime, timezone

    s.archived_at, s.archived_by, s.archive_reason = datetime.now(timezone.utc), current.user.email, body.reason.strip()
    audit.record(db, action="system.archived", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system",
                 entity_id=str(s.id), after={"reason": s.archive_reason, "name": s.name}, **audit.request_meta(request))
    db.commit()
    return _system_out(db, s)


@router.post("/systems/{system_id}/restore")
def restore_system(system_id: uuid.UUID, body: ArchiveIn, request: Request, db: Session = Depends(get_db),
                   current: CurrentUser = Depends(require_permission("system.register"))) -> dict:
    s = get_system(db, system_id)
    if not s.archived_at:
        raise HTTPException(409, "System is not archived")
    before = {"archived_at": s.archived_at.isoformat(), "archived_by": s.archived_by, "reason": s.archive_reason}
    s.archived_at = s.archived_by = s.archive_reason = None
    audit.record(db, action="system.restored", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system",
                 entity_id=str(s.id), before=before, after={"reason": body.reason.strip()}, **audit.request_meta(request))
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


@router.put("/systems/{system_id}/authorization-strategy")
def set_authorization_strategy(system_id: uuid.UUID, body: AuthStrategyIn, request: Request, db: Session = Depends(get_db),
                               current: CurrentUser = Depends(require_permission("system.write"))) -> dict:
    """6 · Authorize – authorization strategy/planning: the authorization type sought. Audited; existing values are preserved."""
    from app.services.rmf_steps import AUTHORIZATION_TYPES

    s = get_system(db, system_id)
    if s.org_id != current.user.org_id:
        raise HTTPException(404, "System not found")
    if body.authorization_type and body.authorization_type not in [v for v, _ in AUTHORIZATION_TYPES]:
        raise HTTPException(422, "Unknown authorization type")
    before = s.authorization_type
    s.authorization_type = body.authorization_type
    audit.record(db, action="system.authorization_strategy_updated", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system",
                 entity_id=str(s.id), before={"authorization_type": before}, after={"authorization_type": s.authorization_type},
                 details={"justification": body.justification}, **audit.request_meta(request))
    db.commit()
    return {"authorization_type": s.authorization_type}
