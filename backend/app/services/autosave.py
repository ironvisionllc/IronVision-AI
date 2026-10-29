"""Auto-save support: request flag (X-Autosave: 1), optimistic concurrency (X-Base-Version = record updated_at), locks, and audit coalescing.
While a request is an auto-save, audit.record() diverts its event into an open AutosaveSession (first before + merged after). The session
is written as ONE audit event when it closes: 5 min idle, the user leaves the page/record (POST /autosave/close), or any explicit action."""
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AutosaveSession

IDLE = timedelta(minutes=5)
autosave_var: ContextVar[bool] = ContextVar("autosave", default=False)


def active() -> bool:
    return autosave_var.get()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def lock_if(cond: bool, message: str) -> None:
    """Locked items (pending approval, approved/signed …) are never auto-saved – only the explicit action may change them."""
    if cond and active():
        raise HTTPException(423, {"code": "locked", "message": message})


def check_base(request: Request, updated_at: datetime | None, theirs: Callable[[], Any] | Any = None) -> None:
    base = request.headers.get("x-base-version")
    if not base or updated_at is None:
        return
    try:
        same = datetime.fromisoformat(base.replace("Z", "+00:00")) == updated_at
    except ValueError:
        same = False
    if not same:
        from fastapi.encoders import jsonable_encoder

        raise HTTPException(409, {"code": "conflict", "message": "Someone else changed this record since you started editing",
                                  "version": updated_at.isoformat(), "theirs": jsonable_encoder(theirs() if callable(theirs) else theirs)})


def _js(v):
    return v if v is None or isinstance(v, (bool, int, float, str)) else ([_js(x) for x in v] if isinstance(v, (list, tuple)) else
                                                                           ({str(k): _js(x) for k, x in v.items()} if isinstance(v, dict) else str(v)))


def divert(db: Session, *, action: str, actor_user_id, actor_email, entity_type, entity_id, before, after, details) -> AutosaveSession | None:
    if actor_user_id is None:
        return None
    now = _now()
    s = db.scalar(select(AutosaveSession).where(AutosaveSession.user_id == actor_user_id, AutosaveSession.entity_type == entity_type,
                                                AutosaveSession.entity_id == entity_id, AutosaveSession.closed_at.is_(None)).with_for_update())
    if s is not None and now - s.last_at > IDLE:
        close(db, s, "idle")
        s = None
    if s is None:
        s = AutosaveSession(user_id=actor_user_id, actor_email=actor_email, entity_type=entity_type, entity_id=entity_id, action=action,
                            before=_js(before), after=_js(after), details=_js({**(details or {}), "actions": [action]}), saves=1, started_at=now, last_at=now)
        db.add(s)
    else:
        s.before = {**_js(before or {}), **(s.before or {})}   # keep the value at session start
        s.after = {**(s.after or {}), **_js(after or {})}
        d = dict(s.details or {})
        d["actions"] = sorted(set(d.get("actions", [])) | {action})
        s.details, s.saves, s.last_at = d, s.saves + 1, now
    db.flush()
    return s


def close(db: Session, s: AutosaveSession, reason: str) -> None:
    from app.services import audit

    if s.closed_at is not None:
        return
    s.closed_at = _now()
    tok = autosave_var.set(False)
    try:
        audit.record(db, action=s.action, actor_user_id=s.user_id, actor_email=s.actor_email, entity_type=s.entity_type, entity_id=s.entity_id,
                     before=s.before, after=s.after, details={**(s.details or {}), "autosave": True, "saves": s.saves, "closed_by": reason,
                                                             "session_started": s.started_at.isoformat(), "last_saved": s.last_at.isoformat()},
                     _coalesced=True)
    finally:
        autosave_var.reset(tok)


def close_for(db: Session, user_id, reason: str, entity_type: str | None = None, entity_id: str | None = None) -> int:
    q = select(AutosaveSession).where(AutosaveSession.user_id == user_id, AutosaveSession.closed_at.is_(None))
    if entity_type:
        q = q.where(AutosaveSession.entity_type == entity_type)
    if entity_id:
        q = q.where(AutosaveSession.entity_id == entity_id)
    n = 0
    for s in db.scalars(q.with_for_update(skip_locked=True)):
        close(db, s, reason)
        n += 1
    return n


def close_idle(db: Session) -> dict:
    n = 0
    for s in db.scalars(select(AutosaveSession).where(AutosaveSession.closed_at.is_(None), AutosaveSession.last_at < _now() - IDLE)
                        .with_for_update(skip_locked=True)):
        close(db, s, "idle")
        n += 1
    db.commit()
    return {"closed": n}
