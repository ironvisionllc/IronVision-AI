from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import LoginAttempt

MAX_FAILURES = 5
LOCKOUT = timedelta(minutes=15)


def is_locked(db: Session, identifier: str) -> bool:
    row = db.scalar(select(LoginAttempt).where(LoginAttempt.identifier == identifier))
    return bool(row and row.locked_until and row.locked_until > datetime.now(timezone.utc))


def register_failure(db: Session, identifier: str) -> None:
    row = db.scalar(select(LoginAttempt).where(LoginAttempt.identifier == identifier))
    if row is None:
        row = LoginAttempt(identifier=identifier, failed_count=0)
        db.add(row)
    row.failed_count += 1
    if row.failed_count >= MAX_FAILURES:
        row.locked_until = datetime.now(timezone.utc) + LOCKOUT
        row.failed_count = 0


def clear(db: Session, identifier: str) -> None:
    db.execute(delete(LoginAttempt).where(LoginAttempt.identifier == identifier))
