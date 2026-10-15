"""Keycloak self-registration (DEMO deployment, realm ironvision-demo): just-in-time clean sandbox for brand-new registrants.

A registrant is recognised by Keycloak's own REGISTER event (admin-/migration-created users never have one) and stamped with the
admin-only attribute self_registered=true. Existing app accounts are never auto-linked. Refused registrants (reserved identifier,
e-mail of an existing app account, sign-up rate limit) are deleted from Keycloak at once, so nothing stays squatted.
Env: KEYCLOAK_ALLOW_REGISTRATION, KEYCLOAK_URL, KEYCLOAK_REALM, KEYCLOAK_BACKEND_CLIENT_ID, KEYCLOAK_BACKEND_CLIENT_SECRET.
"""
import os

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User
from app.services import audit
from app.services import sandbox as sbx
from app.services.keycloak_admin import KeycloakAdmin, KeycloakError

SELF_ATTR = "self_registered"
RESERVED_ATTR = "reserved"
RESERVED_SUFFIXES = ("@aegisrmf.demo", ".invalid")


class Refused(Exception):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code, self.reason = code, reason


def _true(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def realm() -> str:
    return os.environ.get("KEYCLOAK_REALM") or "ironvision-demo"


def service_configured() -> bool:
    return bool(os.environ.get("KEYCLOAK_URL") and os.environ.get("KEYCLOAK_BACKEND_CLIENT_SECRET"))


def enabled() -> bool:
    from app.security import sessions
    return _true(os.environ.get("KEYCLOAK_ALLOW_REGISTRATION")) and "oidc" in sessions.enabled_providers() and service_configured()


def service() -> KeycloakAdmin:
    """Least-privilege service account of the app realm (view/query/manage users, view events) – not the configurator."""
    return KeycloakAdmin().login_service(realm(), os.environ.get("KEYCLOAK_BACKEND_CLIENT_ID") or "ironvision-backend",
                                         os.environ["KEYCLOAK_BACKEND_CLIENT_SECRET"])


def reserved(*idents: str | None) -> bool:
    handle = (os.environ.get("KEYCLOAK_DEMO_USERNAME") or "").lower()
    for v in (x.strip().lower() for x in idents if x):
        if v == sbx.DEMO_EMAIL or v.endswith(RESERVED_SUFFIXES) or (handle and handle in (v, v.split("@")[0])):
            return True
    return False


def is_self_registered(kc: KeycloakAdmin, u: dict) -> bool:
    a = u.get("attributes") or {}
    if a.get("demo_launcher") == ["true"] or a.get(RESERVED_ATTR) == ["true"]:
        return False
    if a.get(SELF_ATTR) == ["true"]:
        return True
    return bool(kc.get(f"/{realm()}/events", params={"type": "REGISTER", "user": u["id"], "max": 1}))


def _delete(kc: KeycloakAdmin, uid: str) -> bool:
    try:
        kc.delete(f"/{realm()}/users/{uid}")
        return True
    except KeycloakError:
        return False


def jit(db: Session, request: Request, claims: dict) -> User | None:
    """None → not a self-registrant (normal 'not mapped' path). Raises Refused. Creates tenant + user + mapping otherwise."""
    from app.api.v1.sandbox import signup_exempt, signup_limit, signups_from
    from app.services import identity_map

    kc = service()
    u = kc.user(realm(), claims["sub"])
    if u is None or not is_self_registered(kc, u):
        return None
    meta = audit.request_meta(request)
    email = (u.get("email") or claims.get("email") or "").strip().lower()
    base = {"provider": "oidc", "keycloak_user_id": u["id"], "keycloak_username": u.get("username")}

    def refuse(code: str, reason: str):
        removed = _delete(kc, u["id"])
        audit.record_now(action="auth.signup", outcome="denied", actor_email=email[:320] or None,
                         details={**base, "reason": reason, "keycloak_user_removed": removed}, **meta)
        raise Refused(code, reason)

    if not email:
        refuse("registration_invalid", "no_email")
    if reserved(email, u.get("username")):
        refuse("registration_reserved", "reserved_identifier")
    if db.scalar(select(User.id).where(func.lower(User.email) == email)):
        refuse("registration_email_exists", "email_exists")
    limit, window = signup_limit()
    if not signup_exempt(meta.get("ip")) and signups_from(db, meta.get("ip"), window)[0] >= limit:
        refuse("registration_rate_limited", "rate_limited")
    name = claims.get("name") or " ".join(x for x in (u.get("firstName"), u.get("lastName")) if x) or email.split("@")[0]
    user, org = sbx.create_owner(db, email, name, None)
    identity_map.map_identity(db, user=user, issuer=claims["subject"].rsplit("|", 1)[0], sub=u["id"], reason="self-registration",
                              actor="jit", username=u.get("username"), action="identity.mapped.jit")
    audit.record(db, action="auth.signup", actor_user_id=user.id, actor_email=email, entity_type="organization", entity_id=str(org.id),
                 details={**base, "sandbox": True, "jit": True}, **meta)
    db.commit()
    sbx.provision(db, org.id)  # clean workspace = tenant configuration only (fast): the first login lands in persona mode
    try:
        kc.put(f"/{realm()}/users/{u['id']}", {**u, "attributes": {**(u.get("attributes") or {}), SELF_ATTR: ["true"]}})
    except KeycloakError:
        pass  # the REGISTER event stays authoritative
    return user


def offboard(identities: list[tuple[str, str]]) -> dict:
    """Sandbox purge: delete self-registered Keycloak users, disable any other mapped one. Never raises."""
    out = {"deleted": 0, "disabled": 0, "failed": 0}
    issuer = (os.environ.get("OIDC_ISSUER") or "").rstrip("/")
    mine = [sub for iss, sub in identities if iss.rstrip("/") == issuer]
    if not mine or not service_configured():
        return out
    try:
        kc = service()
    except KeycloakError:
        return {**out, "failed": len(mine)}
    for sub in mine:
        try:
            u = kc.user(realm(), sub)
            if u is None:
                continue
            if is_self_registered(kc, u):
                kc.delete(f"/{realm()}/users/{sub}")
                out["deleted"] += 1
            else:
                kc.put(f"/{realm()}/users/{sub}", {**u, "enabled": False})
                out["disabled"] += 1
        except KeycloakError:
            out["failed"] += 1
    return out
