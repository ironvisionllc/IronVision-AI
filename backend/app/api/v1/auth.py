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
from app.security.rbac import effective_permissions
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


def _issue(db: Session, user: User, provider: str, request: Request, operator: User | None = None,
           id_token_hint: str | None = None) -> TokenResponse:
    meta = audit.request_meta(request)
    org = db.get(Organization, user.org_id)
    if operator is None and org is not None and org.is_sandbox and org.sandbox_personas and user.persona_role is None and org.sandbox_status == "ready":
        from app.services.sandbox import persona

        user.acting_role = "isso"  # fresh login always starts as the ISSO persona
        p = persona(db, org.id, "isso")
        if p is not None and p.operator_id == user.id:
            user.last_login_at = datetime.now(timezone.utc)
            user, operator = p, user
    sess, refresh = sessions.create(db, user.id, provider, meta.get("ip"), request.headers.get("user-agent"), id_token_hint)
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
                            demo_login_enabled=demo_login_available(), registration_enabled=_registration_enabled(),
                            oidc_enabled="oidc" in enabled)


def _registration_enabled() -> bool:
    from app.security import registration
    return registration.enabled()


def demo_login_mode() -> str | None:
    """'keycloak' = Option B launcher (oidc enabled + launcher configured); 'dev_password' = local preview/dev; None = 404."""
    from app.security import demo_launcher
    if not get_settings().allow_demo_login:
        return None
    prov = sessions.enabled_providers()
    if "oidc" in prov and demo_launcher.configured():
        return "keycloak"
    return "dev_password" if "dev_password" in prov else None


def demo_login_available() -> bool:
    return demo_login_mode() is not None


def demo_login_global_limit() -> tuple[int, int]:
    n, _, w = os.environ.get("DEMO_LOGIN_GLOBAL_RATE_LIMIT", "300/3600").partition("/")
    return int(n), int(w or 3600)


def demo_login_limit() -> tuple[int, int]:
    n, _, w = os.environ.get("DEMO_LOGIN_RATE_LIMIT", "30/3600").partition("/")
    return int(n), int(w or 3600)


@router.post("/demo-login", response_model=TokenResponse)
def demo_login(request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    """One-click entry to the shared, synthetic demo workspace. No password travels from the browser; gated by ALLOW_DEMO_LOGIN."""
    from datetime import timedelta

    from sqlalchemy import func

    from app.models import AuditEvent
    from app.services.sandbox import DEMO_EMAIL

    mode = demo_login_mode()
    if mode is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")
    meta = audit.request_meta(request)

    def window_count(seconds: int, per_ip: bool) -> int:
        since = datetime.now(timezone.utc) - timedelta(seconds=seconds)
        q = select(func.count()).select_from(AuditEvent).where(AuditEvent.action == "auth.demo_login", AuditEvent.outcome == "success",
                                                               AuditEvent.occurred_at > since)
        return db.scalar(q.where(AuditEvent.ip == meta.get("ip")) if per_ip else q)

    for (limit, window), per_ip, scope in ((demo_login_limit(), True, "this network"), (demo_login_global_limit(), False, "all visitors")):
        if window_count(window, per_ip) >= limit:
            audit.record_now(action="auth.demo_login", outcome="denied", actor_email=DEMO_EMAIL,
                             details={"reason": "rate_limited" if per_ip else "global_rate_limited", "client_ip": meta.get("ip")}, **meta)
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, f"Too many demo sign-ins from {scope} ({limit} per {window // 60} min). Try again later.",
                                headers={"Retry-After": str(window)})
    provider = "dev_password"
    if mode == "keycloak":
        from app.security import demo_launcher
        from app.services import identity_map
        try:
            claims = demo_launcher.login()
        except Exception as exc:  # noqa: BLE001 - Keycloak down / misconfigured: never fall back to a bypass
            audit.record_now(action="auth.demo_login", outcome="failure", actor_email=DEMO_EMAIL,
                             details={"reason": str(exc)[:120], "client_ip": meta.get("ip")}, **meta)
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The demo is temporarily unavailable. Try again in a minute.")
        issuer, sub = claims["subject"].rsplit("|", 1)
        ident = identity_map.by_subject(db, issuer, sub)
        if ident is None:
            audit.record_now(action="auth.demo_login", outcome="denied", actor_email=DEMO_EMAIL,
                             details={"reason": "identity_not_mapped", "subject": claims["subject"], "client_ip": meta.get("ip")}, **meta)
            raise HTTPException(status.HTTP_403_FORBIDDEN, "The demo account is not mapped yet (operator: scripts/keycloak.sh migrate).")
        user = db.get(User, ident.user_id)
        if user is None or user.email != DEMO_EMAIL:  # the launcher may only ever open the demo tenant
            audit.record_now(action="auth.demo_login", outcome="denied", actor_email=DEMO_EMAIL,
                             details={"reason": "mapped_to_non_demo_user", "client_ip": meta.get("ip")}, **meta)
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Demo launcher misconfigured")
        ident.last_used_at = datetime.now(timezone.utc)
        provider = "oidc-demo"
    user = db.scalar(select(User).where(User.email == DEMO_EMAIL, User.is_active.is_(True)))
    org = db.get(Organization, user.org_id) if user else None
    if user is None or org is None or org.sandbox_status != "ready":
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "The demo workspace is being prepared. Try again in a minute.")
    audit.record(db, action="auth.demo_login", outcome="success", actor_user_id=user.id, actor_email=DEMO_EMAIL, entity_type="user",
                 entity_id=str(user.id), details={"client_ip": meta.get("ip"), "mode": mode}, **meta)
    return _issue(db, user, provider, request)


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


def _email_linking_allowed() -> bool:
    """Dev/test-only escape hatch; production never links an IdP identity by email."""
    return os.environ.get("OIDC_ALLOW_EMAIL_LINKING", "").lower() == "true" and get_settings().environment in ("development", "test")


def _external_login(db: Session, request: Request, provider: str, subject: str, email: str | None, allow_email_link: bool = True) -> User:
    ident = db.scalar(select(AuthIdentity).where(AuthIdentity.provider == provider, AuthIdentity.subject == subject))
    if ident is None and not allow_email_link:
        audit.record_now(action="auth.login", outcome="denied", actor_email=email or None, entity_type="auth_identity",
                         details={"provider": provider, "reason": "identity_not_mapped", "subject": subject}, **audit.request_meta(request))
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This sign-in identity is not mapped to an IronVision AI account. Ask an administrator.")
    user = db.get(User, ident.user_id) if ident else (db.scalar(select(User).where(User.email == email)) if email else None)
    if user is None or not user.is_active:
        audit.record_now(action="auth.login", outcome="failure", actor_email=email, details={"provider": provider, "reason": "no_provisioned_user"},
                         **audit.request_meta(request))
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No active IronVision AI account is provisioned for this identity")
    if ident is None:
        db.add(AuthIdentity(user_id=user.id, provider=provider, subject=subject,
                            attributes={"mapped_by": "email-link(dev-only)", "mapped_at": datetime.now(timezone.utc).isoformat()}))
    else:
        ident.last_used_at = datetime.now(timezone.utc)
    return user


def _require_oidc() -> None:
    if "oidc" not in sessions.enabled_providers():
        raise HTTPException(404, "OIDC is not enabled (AUTH_PROVIDERS)")


@router.get("/oidc/login")
def oidc_login(login_hint: str | None = None, db: Session = Depends(get_db)) -> RedirectResponse:
    _require_oidc()
    from app.security import oidc
    return RedirectResponse(oidc.authorization_url(db, (login_hint or "").strip()[:255] or None))


@router.get("/oidc/register")
def oidc_register(db: Session = Depends(get_db)) -> RedirectResponse:
    """Keycloak registration page with the same PKCE/state/nonce flow (DEMO deployment, KEYCLOAK_ALLOW_REGISTRATION)."""
    _require_oidc()
    if not _registration_enabled():
        raise HTTPException(404, "Self-registration is disabled")
    from app.security import oidc
    return RedirectResponse(oidc.authorization_url(db, None, register=True))


LOGIN_CODE_TTL = 60


@router.get("/oidc/callback")
def oidc_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None,
                  db: Session = Depends(get_db)) -> RedirectResponse:
    _require_oidc()
    import hashlib
    import secrets
    from datetime import timedelta

    from app.models import OidcLoginCode
    from app.security import oidc
    front = os.environ.get("FRONTEND_URL", "")
    if error or not code or not state:
        audit.record_now(action="auth.login", outcome="failure", details={"provider": "oidc", "reason": f"idp_error:{(error or 'missing_code')[:80]}"},
                         **audit.request_meta(request))
        return RedirectResponse(f"{front}/login?oidc_error=idp")
    try:
        claims = oidc.complete(db, code, state)
    except Exception as exc:
        audit.record_now(action="auth.login", outcome="failure", details={"provider": "oidc", "reason": str(exc)[:200]}, **audit.request_meta(request))
        raise HTTPException(401, "OIDC sign-in failed")
    from app.services import identity_map
    if identity_map.by_subject(db, claims["subject"].rsplit("|", 1)[0], claims["sub"]) is None and _registration_enabled():
        from app.security import registration
        try:
            registration.jit(db, request, claims)  # brand-new self-registrant → clean sandbox + explicit mapping
        except registration.Refused as r:
            return RedirectResponse(f"{front}/login?oidc_error={r.code}")
        except Exception as exc:  # noqa: BLE001 - Keycloak admin API unreachable: refuse, never fall back to e-mail linking
            db.rollback()
            audit.record_now(action="auth.signup", outcome="failure", details={"provider": "oidc", "reason": f"jit_failed:{str(exc)[:120]}"},
                             **audit.request_meta(request))
            return RedirectResponse(f"{front}/login?oidc_error=registration_unavailable")
    user = _external_login(db, request, "oidc", claims["subject"], claims["email"], allow_email_link=_email_linking_allowed())
    raw = secrets.token_urlsafe(32)
    db.add(OidcLoginCode(code_sha256=hashlib.sha256(raw.encode()).hexdigest(), user_id=user.id, id_token=claims["id_token"],
                         expires_at=datetime.now(timezone.utc) + timedelta(seconds=LOGIN_CODE_TTL)))
    db.commit()
    # Only an opaque one-time code (60 s, single use) reaches the browser URL; the SPA exchanges it by POST for app tokens.
    return RedirectResponse(f"{front}/login?oidc_code={raw}")


class OidcExchangeIn(BaseModel):
    code: str


@router.post("/oidc/exchange", response_model=TokenResponse)
def oidc_exchange(body: OidcExchangeIn, request: Request, db: Session = Depends(get_db)) -> TokenResponse:
    _require_oidc()
    import hashlib

    from sqlalchemy import delete

    from app.models import OidcLoginCode
    row = db.execute(delete(OidcLoginCode).where(OidcLoginCode.code_sha256 == hashlib.sha256(body.code.encode()).hexdigest())
                     .returning(OidcLoginCode.user_id, OidcLoginCode.id_token, OidcLoginCode.expires_at)).first()
    db.commit()
    user = db.get(User, row.user_id) if row and row.expires_at > datetime.now(timezone.utc) else None
    if user is None or not user.is_active:
        audit.record_now(action="auth.login", outcome="failure", details={"provider": "oidc", "reason": "invalid_login_code"}, **audit.request_meta(request))
        raise HTTPException(401, "Sign-in code invalid, expired or already used")
    return _issue(db, user, "oidc", request, id_token_hint=row.id_token)


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


@router.post("/logout")
def logout(request: Request, current: CurrentUser = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    from app.models import AuthSession
    sess = db.get(AuthSession, uuid.UUID(request.state.sid))
    end_url = None
    if sess is not None and sess.provider == "oidc" and "oidc" in sessions.enabled_providers():
        from app.security import oidc
        try:
            end_url = oidc.end_session_url(sess.id_token_hint)
        except Exception:  # IdP unreachable: app session is still revoked
            end_url = None
        sess.id_token_hint = None
    sessions.revoke(db, uuid.UUID(request.state.sid), "logout")
    audit.record(db, action="auth.logout", actor_user_id=current.user.id, actor_email=current.user.email,
                 entity_type="user", entity_id=str(current.user.id), details={"session_revoked": request.state.sid, "idp_logout": bool(end_url)},
                 **audit.request_meta(request))
    db.commit()
    return {"end_session_url": end_url}
