"""Server-side sessions. Access JWTs carry a `sid`; every request checks that the session is active and not idle-expired.
Logout revokes; refresh rotates the refresh token (only its SHA-256 is stored; replay of an old token revokes the session)."""
import hashlib
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import AuthSession

IDLE_MINUTES = int(os.environ.get("SESSION_IDLE_MINUTES", "30"))
ABSOLUTE_HOURS = int(os.environ.get("SESSION_ABSOLUTE_HOURS", "12"))


def now() -> datetime:
    return datetime.now(timezone.utc)


def _h(v: str) -> str:
    return hashlib.sha256(v.encode()).hexdigest()


def create(db: Session, user_id: uuid.UUID, provider: str, ip: str | None, ua: str | None,
           id_token_hint: str | None = None) -> tuple[AuthSession, str]:
    raw = secrets.token_urlsafe(48)
    t = now()
    s = AuthSession(user_id=user_id, provider=provider, refresh_hash=_h(raw), last_seen_at=t, idle_expires_at=t + timedelta(minutes=IDLE_MINUTES),
                    absolute_expires_at=t + timedelta(hours=ABSOLUTE_HOURS), ip=ip, user_agent=(ua or "")[:300], id_token_hint=id_token_hint)
    db.add(s)
    db.flush()
    return s, raw


def touch(db: Session, sid: uuid.UUID) -> AuthSession | None:
    s = db.get(AuthSession, sid)
    t = now()
    if s is None or s.revoked_at or s.idle_expires_at < t or s.absolute_expires_at < t:
        return None
    if (t - s.last_seen_at).total_seconds() > 30:  # throttle writes
        db.execute(update(AuthSession).where(AuthSession.id == sid).values(last_seen_at=t, idle_expires_at=t + timedelta(minutes=IDLE_MINUTES)))
        db.commit()
    return s


def rotate(db: Session, raw: str) -> tuple[AuthSession, str] | None:
    s = db.scalar(select(AuthSession).where(AuthSession.refresh_hash == _h(raw)).with_for_update())
    t = now()
    if s is None or s.revoked_at or s.idle_expires_at < t or s.absolute_expires_at < t:
        return None
    new = secrets.token_urlsafe(48)
    s.refresh_hash, s.last_seen_at, s.idle_expires_at = _h(new), t, t + timedelta(minutes=IDLE_MINUTES)
    return s, new


def revoke(db: Session, sid: uuid.UUID, reason: str) -> None:
    db.execute(update(AuthSession).where(AuthSession.id == sid, AuthSession.revoked_at.is_(None)).values(revoked_at=now(), revoked_reason=reason))


def enabled_providers() -> list[str]:
    raw = os.environ.get("AUTH_PROVIDERS") or os.environ.get("AUTH_PROVIDER") or "dev_password"
    return [p.strip() for p in raw.split(",") if p.strip()]
