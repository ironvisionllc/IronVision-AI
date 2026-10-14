import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import Request
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db import SessionLocal
from contextvars import ContextVar

from app.logging_setup import correlation_id_var

operator_var: ContextVar[dict | None] = ContextVar("operator", default=None)  # per-request holder, mutated by auth dependency
from app.models import AuditEvent

GENESIS_HASH = "0" * 64
_LOCK_KEY = 7340001


def _canonical(body: dict) -> str:
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)


def _body(ev: AuditEvent) -> dict:
    return {
        "occurred_at": ev.occurred_at.astimezone(timezone.utc).isoformat(),
        "actor_user_id": str(ev.actor_user_id) if ev.actor_user_id else None,
        "actor_email": ev.actor_email,
        "action": ev.action,
        "entity_type": ev.entity_type,
        "entity_id": ev.entity_id,
        "before": ev.before,
        "after": ev.after,
        "outcome": ev.outcome,
        "correlation_id": ev.correlation_id,
        "ip": ev.ip,
        "details": ev.details,
    }


def compute_hash(prev_hash: str, ev: AuditEvent) -> str:
    return hashlib.sha256((prev_hash + _canonical(_body(ev))).encode("utf-8")).hexdigest()


def request_meta(request: Request | None) -> dict:
    if request is None:
        return {}
    from app.security.web import client_ip

    return {"ip": client_ip(request), "user_agent": (request.headers.get("user-agent") or "")[:500]}


def record(
    db: Session,
    *,
    action: str,
    outcome: str = "success",
    actor_user_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    before: dict | None = None,
    after: dict | None = None,
    details: dict | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    correlation_id: str | None = None,
) -> AuditEvent:
    op = (operator_var.get() or {}).get("email")
    if op:
        details = {**(details or {}), "operated_by": op, "sandbox_persona": True}
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})
    prev = db.scalar(select(AuditEvent.hash).order_by(AuditEvent.seq.desc()).limit(1)) or GENESIS_HASH
    ev = AuditEvent(
        occurred_at=datetime.now(timezone.utc),
        actor_user_id=actor_user_id,
        actor_email=actor_email,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        before=before,
        after=after,
        outcome=outcome,
        correlation_id=correlation_id or correlation_id_var.get(),
        ip=ip,
        user_agent=user_agent,
        details=details,
        prev_hash=prev,
    )
    ev.hash = compute_hash(prev, ev)
    db.add(ev)
    db.flush()
    return ev


def record_now(**kwargs: Any) -> None:
    with SessionLocal() as db:
        record(db, **kwargs)
        db.commit()


def verify_chain(db: Session) -> dict:
    prev = GENESIS_HASH
    count = 0
    for ev in db.scalars(select(AuditEvent).order_by(AuditEvent.seq)).yield_per(500):
        count += 1
        if ev.prev_hash != prev or compute_hash(prev, ev) != ev.hash:
            return {"valid": False, "checked": count, "first_invalid_seq": ev.seq}
        prev = ev.hash
    return {"valid": True, "checked": count, "first_invalid_seq": None, "head_hash": prev}
