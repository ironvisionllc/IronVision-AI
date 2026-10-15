"""Explicit, auditable OIDC identity mappings (issuer|sub → app user). Never links by email at login time.

Invariants: one Keycloak subject → one app user (DB unique constraint); one app user → at most one identity per issuer.
"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuthIdentity, User
from app.services import audit

PROVIDER = "oidc"


class MappingConflict(ValueError):
    pass


def subject(issuer: str, sub: str) -> str:
    return f"{issuer.rstrip('/')}|{sub}"


def identity_for(db: Session, user_id, issuer: str) -> AuthIdentity | None:
    return db.scalar(select(AuthIdentity).where(AuthIdentity.user_id == user_id, AuthIdentity.provider == PROVIDER,
                                                AuthIdentity.subject.startswith(f"{issuer.rstrip('/')}|")))


def by_subject(db: Session, issuer: str, sub: str) -> AuthIdentity | None:
    return db.scalar(select(AuthIdentity).where(AuthIdentity.provider == PROVIDER, AuthIdentity.subject == subject(issuer, sub)))


def map_identity(db: Session, *, user: User, issuer: str, sub: str, reason: str, actor: str, username: str | None = None) -> tuple[AuthIdentity, bool]:
    """Create the mapping (idempotent). Raises MappingConflict on any ambiguity. Caller commits."""
    if not reason.strip():
        raise MappingConflict("a reason is required for every identity mapping")
    taken = by_subject(db, issuer, sub)
    if taken is not None:
        if taken.user_id == user.id:
            return taken, False
        raise MappingConflict(f"keycloak user {sub} is already mapped to another app user ({taken.user_id})")
    mine = identity_for(db, user.id, issuer)
    if mine is not None:
        raise MappingConflict(f"{user.email} already has a different identity for this issuer ({mine.subject.rsplit('|', 1)[-1]})")
    ident = AuthIdentity(user_id=user.id, provider=PROVIDER, subject=subject(issuer, sub),
                         attributes={"issuer": issuer.rstrip("/"), "keycloak_user_id": sub, "keycloak_username": username,
                                     "mapped_by": actor, "mapped_at": datetime.now(timezone.utc).isoformat(), "reason": reason})
    db.add(ident)
    db.flush()
    audit.record(db, action="identity.mapped", actor_email=actor, entity_type="user", entity_id=str(user.id),
                 details={"email": user.email, "issuer": issuer, "keycloak_user_id": sub, "reason": reason})
    return ident, True


def list_mappings(db: Session, org_id=None) -> list[dict]:
    q = (select(AuthIdentity, User.email, User.is_active).join(User, User.id == AuthIdentity.user_id)
         .where(AuthIdentity.provider == PROVIDER).order_by(User.email))
    rows = db.execute(q.where(User.org_id == org_id) if org_id else q).all()
    out = []
    for ident, email, active in rows:
        a = ident.attributes or {}
        out.append({"user_id": str(ident.user_id), "email": email, "user_active": active, "issuer": a.get("issuer") or ident.subject.rsplit("|", 1)[0],
                    "keycloak_user_id": ident.subject.rsplit("|", 1)[-1], "keycloak_username": a.get("keycloak_username"),
                    "mapped_by": a.get("mapped_by"), "mapped_at": a.get("mapped_at"), "reason": a.get("reason"),
                    "last_used_at": ident.last_used_at.isoformat() if ident.last_used_at else None})
    return out
