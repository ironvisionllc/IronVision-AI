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
    return CurrentUser(user=user, assignments=assignments, auth_provider=(payload.get("amr") or ["unknown"])[0])


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
        raise HTTPException(status.HTTP_403_FORBIDDEN, f"Missing permission: {permission}")


def require_permission(permission: str, system_id_param: str = "system_id"):
    """Dependency factory. Scope: org-level assignments, or system-level when `system_id` is in path/query."""

    def dependency(request: Request, current: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        raw = request.path_params.get(system_id_param) or request.query_params.get(system_id_param)
        enforce(request, current, permission, _parse_uuid(raw))
        return current

    return dependency
