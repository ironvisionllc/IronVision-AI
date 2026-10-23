import uuid
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import RoleAssignment, User
from app.security.rbac import has_permission
from app.security.tokens import decode_access_token
from app.services import audit


@dataclass
class CurrentUser:
    user: User
    assignments: list[RoleAssignment]
    auth_provider: str
    operator: User | None = None

    @property
    def roles(self) -> list[str]:
        return sorted({a.role for a in self.assignments})


def get_current_user(request: Request, db: Session = Depends(get_db)) -> CurrentUser:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated", headers={"WWW-Authenticate": "Bearer"})
    try:
        payload = decode_access_token(header[7:].strip())
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token", headers={"WWW-Authenticate": "Bearer"})
    from app.security import sessions
    if "sid" not in payload or sessions.touch(db, uuid.UUID(payload["sid"])) is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired, idle timeout reached or logged out",
                            headers={"WWW-Authenticate": "Bearer"})
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    assignments = list(db.scalars(select(RoleAssignment).where(RoleAssignment.user_id == user.id)))
    request.state.sid = payload["sid"]
    operator = None
    if payload.get("op"):
        operator = db.get(User, uuid.UUID(payload["op"]))
        if operator is None or not operator.is_active or user.operator_id != operator.id:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Persona session is no longer valid")
    holder = audit.operator_var.get()
    if holder is not None:
        holder["email"] = operator.email if operator else None
    from app.models import Organization
    org = db.get(Organization, user.org_id)
    if org is not None and org.is_sandbox:
        from datetime import datetime, timedelta, timezone
        t = datetime.now(timezone.utc)
        if not org.last_activity_at or t - org.last_activity_at > timedelta(minutes=10):
            org.last_activity_at = t
            db.commit()
    return CurrentUser(user=user, assignments=assignments, auth_provider=(payload.get("amr") or ["unknown"])[0], operator=operator)


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    try:
        return uuid.UUID(value) if value else None
    except ValueError:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "system_id must be a UUID")


def _system_org(system_id: uuid.UUID):
    from app.db import SessionLocal
    from app.models import System
    with SessionLocal() as db:
        return db.scalar(select(System.org_id).where(System.id == system_id))


def enforce(request: Request, current: CurrentUser, permission: str, system_id: uuid.UUID | None) -> None:
    if system_id is not None and _system_org(system_id) not in (None, current.user.org_id):
        audit.record_now(action="authz.denied", outcome="denied", actor_user_id=current.user.id, actor_email=current.user.email,
                         entity_type="system", entity_id=str(system_id), details={"reason": "cross_tenant", "path": request.url.path},
                         **audit.request_meta(request))
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
    if not has_permission(current.assignments, permission, current.user.org_id, system_id):
        audit.record_now(
            action="authz.denied", outcome="denied", actor_user_id=current.user.id,
            actor_email=current.user.email, entity_type="permission", entity_id=permission,
            details={"path": request.url.path, "method": request.method, "roles": current.roles,
                     "system_id": str(system_id) if system_id else None},
            **audit.request_meta(request),
        )
        from app.security.rbac import ROLE_PERMISSIONS, ROLES

        raise HTTPException(status.HTTP_403_FORBIDDEN, {
            "code": "missing_permission", "permission": permission, "message": f"Missing permission: {permission}",
            "roles": [r for r in ROLES if permission in ROLE_PERMISSIONS.get(r, set())]})


def require_permission(permission: str, system_id_param: str = "system_id"):
    """Dependency factory. Scope: org-level assignments, or system-level when `system_id` is in path/query."""

    def dependency(request: Request, current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        raw = request.path_params.get(system_id_param) or request.query_params.get(system_id_param)
        enforce(request, current, permission, _parse_uuid(raw))
        return current

    dependency.permission = permission
    return dependency


SYSTEM_SCOPED = {"TrExport", "InventoryDiscrepancy", "AssetCorrelation", "InventoryExport"}


def _object_system(model_name: str, raw: str | None, org_id) -> uuid.UUID:
    """System that owns the addressed object (tenant-scoped; 404 when missing or in another tenant)."""
    from app.db import SessionLocal
    from app import models

    model = getattr(models, model_name)
    with SessionLocal() as db:
        if model_name == "Poam" and raw and raw.upper().startswith("P-"):
            obj = db.scalar(select(model).where(model.human_id == raw.upper(), model.org_id == org_id))
        else:
            obj = db.get(model, _parse_uuid(raw)) if raw else None
        if model_name == "PoamMilestone" and obj is not None:
            obj = db.get(models.Poam, obj.poam_id)
        elif model_name == "FindingControlMap" and obj is not None:
            obj = db.get(models.Finding, obj.finding_id)
        if obj is None or getattr(obj, "org_id", org_id) != org_id and getattr(obj, "org_id", None) is not None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        if model_name in SYSTEM_SCOPED and db.get(models.System, obj.system_id).org_id != org_id:  # tenant check via the owning system
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")
        return obj.system_id


def require_object_permission(permission: str, model_name: str, param: str):
    """Dependency factory for object routes (/findings/{id}, /poams/{id} …): enforce `permission` on the object's system."""

    def dependency(request: Request, current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        enforce(request, current, permission, _object_system(model_name, request.path_params.get(param), current.user.org_id))
        return current

    dependency.permission = permission
    return dependency


def require_body_permission(permission: str, field: str = "system_id"):
    """Dependency factory for routes whose target system is in the JSON body."""

    async def dependency(request: Request, current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        try:
            raw = (await request.json()).get(field)
        except Exception:
            raw = None
        if not raw:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"{field} is required")
        enforce(request, current, permission, _parse_uuid(str(raw)))
        return current

    dependency.permission = permission
    return dependency


def self_scoped(current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Marker dependency: the route only mutates the caller's own records (notifications, prefs, own sandbox)."""
    return current


self_scoped.self_scoped = True
