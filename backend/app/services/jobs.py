import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging_setup import correlation_id_var
from app.models import Job

JOB_CONTENT_LOAD = "content.load_reference"


def enqueue(db: Session, job_type: str, payload: dict | None = None, requested_by: uuid.UUID | None = None) -> Job:
    job = Job(job_type=job_type, payload=payload or {}, requested_by=requested_by, correlation_id=correlation_id_var.get())
    db.add(job)
    db.flush()
    return job


def has_pending(db: Session, job_type: str) -> bool:
    return db.scalar(select(Job.id).where(Job.job_type == job_type, Job.status.in_(("queued", "running"))).limit(1)) is not None
