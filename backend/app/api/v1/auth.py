import os
import uuid
from datetime import datetime, timezone

from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.seed import SEED_SOURCE
from app.config import get_settings
from app.models import AuthIdentity, Organization, RoleAssignment, User
from app.schemas import AuthProviderInfo, DevAccount, LoginRequest, RoleOut, TokenResponse, UserOut
from app.security import login_guard, sessions
from app.security.deps import CurrentUser, get_current_user
from app.security.providers import AuthenticationError, get_auth_provider
from app.security.rbac import ROLES, effective_permissions
from app.security.tokens import create_access_token
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


def build_user_out(db: Session, user: User, assignments: list[RoleAssignment], provider_name: str) -> UserOut:
    org = db.get(Organization, user.org_id)
    provider = get_auth_provider()
    return UserOut(
        id=user.id, email=user.email, display_name=user.display_name, title=user.title, org_id=user.org_id,
        org_name=org.name if org else "", roles=[RoleOut.model_validate(a) for a in assignments],
        permissions=effective_permissions(assignments), auth_provider=provider_name,
        auth_is_simulated=provider.is_simulated, persona_role=user.persona_role, is_sandbox=bool(org and org.is_sandbox),
    )


def _issue(db: Session, user: User, provider: str, request: Request, operator: User | None = None) -> TokenResponse:
    meta = audit.request_meta(request)
    org = db.get(Organization, user.org_id)
    if operator is None and org is not None and org.is_sandbox and org.sandbox_personas and user.persona_role is None and org.sandbox_status == "ready":
        from app.services.sandbox import persona

        user.acting_role = "isso"  # fresh login always starts as the ISSO persona
        p = persona(db, org.id, "isso")
        if p is not None and p.operator_id == user.id:
            user.last_login_at = datetime.now(timezone.utc)
            user, operator = p, user
    sess, refresh = sessions.create(db, user.id, provider, meta.get("ip"), request.headers.get("user-agent"))
    user.last_login_at = datetime.now(timezone.utc)
    audit.record(db, action="auth.login", outcome="success", actor_user_id=user.id, actor_email=user.email, entity_type="user", entity_id=str(user.id),
                 details={"provider": provider, "session_id": str(sess.id), **({"operated_by": operator.email, "sandbox_persona": True} if operator else {})},
                 **meta)
    db.commit()
    assignments = list(db.scalars(select(RoleAssignment).where(RoleAssignment.user_id == user.id)))
    token, ttl = create_access_token(user.id, provider, sess.id, operator.id if operator else None)
    return TokenResponse(access_token=token, expires_in=ttl, refresh_token=refresh, idle_timeout_minutes=sessions.IDLE_MINUTES,
                         user=build_user_out(db, user, assignments, provider))


@router.get("/provider", response_model=AuthProviderInfo)
def provider_info(db: Session = Depends(get_db)) -> AuthProviderInfo:
    provider = get_auth_provider()
    accounts: list[DevAccount] = []
    enabled = sessions.enabled_providers()
    if provider.is_simulated and "dev_password" in enabled and os.environ.get("DEV_USER_PICKER", "true").lower() not in ("0", "false", "no", "off"):
        rows = db.execute(
            select(User.email, User.display_name, RoleAssignment.role)
            .join(AuthIdentity, AuthIdentity.user_id == User.id)
            .join(RoleAssignment, RoleAssignment.user_id == User.id)
            .where(AuthIdentity.provider == provider.name, User.is_active.is_(True), RoleAssignment.scope_type == "org",
                   User.source == SEED_SOURCE)
            .order_by(User.email)
        ).all()
        accounts = []  # no public account picker: one shared demo account (docs only) + self sign-up
        _ = rows
    return AuthProviderInfo(provider=provider.name, label=provider.display_label, is_simulated=provider.is_simulated,
                            dev_accounts=accounts, enabled_providers=enabled, dev_password_enabled="dev_password" in enabled, signup_enabled=get_settings().allow_signup and "dev_password" in enabled,
                            oidc_enabled="oidc" in enabled)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    if "dev_password" not in sessions.enabled_providers():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Password sign-in is disabled (AUTH_PROVIDERS)")
    provider = get_auth_provider()
    meta = audit.request_meta(request)
    email = body.email.strip().lower()
    identifier = f"{meta.get('ip')}:{email}"
    if login_guard.is_locked(db, identifier):
        audit.record_now(action="auth.login", outcome="locked", actor_email=email,
                         details={"provider": provider.name, "reason": "too_many_attempts"}, **meta)
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many failed attempts. Try again in 15 minutes.")
    try:
        principal = provider.authenticate(db, {"email": email, "password": body.password})
        identity = db.scalar(select(AuthIdentity).where(AuthIdentity.provider == principal.provider,
                                                        AuthIdentity.subject == principal.subject))
        user = db.get(User, identity.user_id) if identity else None
        if user is None or not user.is_active:
            raise AuthenticationError("no_active_user")
    except AuthenticationError as exc:
        db.rollback()
        login_guard.register_failure(db, identifier)
        db.commit()
        audit.record_now(action="auth.login", outcome="failure", actor_email=email,
                         details={"provider": provider.name, "reason": exc.reason}, **meta)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    login_guard.clear(db, identifier)
    return _issue(db, user, provider.name, request)


class RefreshIn(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenResponse)
def refresh(body: RefreshIn, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    r = sessions.rotate(db, body.refresh_token)
    if r is None:
        db.rollback()
        audit.record_now(action="auth.refresh", outcome="failure", details={"reason": "invalid_or_expired"}, **audit.request_meta(request))
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token invalid, rotated, expired or revoked")
    sess, raw = r
    user = db.get(User, sess.user_id)
    db.commit()
    assignments = list(db.scalars(select(RoleAssignment).where(RoleAssignment.user_id == user.id)))
    token, ttl = create_access_token(user.id, sess.provider, sess.id)
    return TokenResponse(access_token=token, expires_in=ttl, refresh_token=raw, idle_timeout_minutes=sessions.IDLE_MINUTES,
                         user=build_user_out(db, user, assignments, sess.provider))


def _external_login(db: Session, request: Request, provider: str, subject: str, email: str | None) -> User:
    ident = db.scalar(select(AuthIdentity).where(AuthIdentity.provider == provider, AuthIdentity.subject == subject))
    user = db.get(User, ident.user_id) if ident else (db.scalar(select(User).where(User.email == email)) if email else None)
    if user is None or not user.is_active:
        audit.record_now(action="auth.login", outcome="failure", actor_email=email, details={"provider": provider, "reason": "no_provisioned_user"},
                         **audit.request_meta(request))
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No active IronVision AI account is provisioned for this identity")
    if ident is None:
        db.add(AuthIdentity(user_id=user.id, provider=provider, subject=subject))
    return user


@router.get("/oidc/login")
def oidc_login() -> RedirectResponse:
    if "oidc" not in sessions.enabled_providers():
        raise HTTPException(404, "OIDC is not enabled (AUTH_PROVIDERS)")
    from app.security import oidc
    return RedirectResponse(oidc.authorization_url())


@router.get("/oidc/callback")
def oidc_callback(code: str, state: str, request: Request, db: Session = Depends(get_db)) -> RedirectResponse:
    if "oidc" not in sessions.enabled_providers():
        raise HTTPException(404, "OIDC is not enabled")
    from app.security import oidc
    try:
        claims = oidc.complete(code, state)
    except Exception as exc:
        audit.record_now(action="auth.login", outcome="failure", details={"provider": "oidc", "reason": str(exc)[:200]}, **audit.request_meta(request))
        raise HTTPException(401, "OIDC sign-in failed")
    tr = _issue(db, _external_login(db, request, "oidc", claims["subject"], claims["email"]), "oidc", request)
    # Tokens go to the SPA in the URL fragment (never sent to servers/logs); the SPA stores them and clears the hash.
    return RedirectResponse(f"{os.environ.get('FRONTEND_URL', '')}/login#access_token={tr.access_token}&refresh_token={tr.refresh_token}")


@router.post("/mtls/login", response_model=TokenResponse)
def mtls_login(request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    if "mtls_header" not in sessions.enabled_providers():
        raise HTTPException(404, "mTLS header sign-in is not enabled")
    from app.security import oidc
    try:
        p = oidc.mtls_principal(request.headers, request.client.host if request.client else None)
    except ValueError as exc:
        audit.record_now(action="auth.login", outcome="failure", details={"provider": "mtls_header", "reason": str(exc)}, **audit.request_meta(request))
        raise HTTPException(401, "Client certificate identity not accepted")
    return _issue(db, _external_login(db, request, "mtls_header", p["subject"], None), "mtls_header", request)


@router.get("/me", response_model=UserOut)
def me(current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    return build_user_out(db, current.user, current.assignments, current.auth_provider)


@router.post("/logout", status_code=204)
def logout(request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    sessions.revoke(db, uuid.UUID(request.state.sid), "logout")
    audit.record(db, action="auth.logout", actor_user_id=current.user.id, actor_email=current.user.email,
                 entity_type="user", entity_id=str(current.user.id), details={"session_revoked": request.state.sid}, **audit.request_meta(request))
    db.commit()
