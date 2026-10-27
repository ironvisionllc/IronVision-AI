"""DB-backed scheduler for continuous monitoring jobs.

Each tick locks due rows in scheduled_jobs (FOR UPDATE SKIP LOCKED), so two workers never enqueue the same job twice.
A job is not enqueued again while one of the same type is still queued or running. Stale running jobs are requeued, and
the result of every run is written back to its schedule row.
"""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Job, ScheduledJob
from app.services import jobs as jobsvc

DEFAULT_SCHEDULES = [
    ("evidence.evaluate_freshness", "Evidence freshness evaluation", 15),
    ("attestations.evaluate", "Attestation expiry evaluation", 60),
    ("evidence.verify_integrity", "Evidence integrity verification (re-hash)", 1440),
    ("risk.snapshot", "Daily risk snapshot + score recompute", 1440),
    ("notifications.deadlines", "Deadline notifications", 60),
    ("connectors.collect", "Mock connector collection (per source frequency)", 30),
    ("kev.reevaluate", "KEV re-evaluation of findings", 1440),
    ("emass.retry", "eMASS outbound retry (backoff)", 5),
    ("conmon.slcm_due", "SLCM due/overdue per Continuous Monitoring Strategy (Monitor)", 1440),
    ("retention.purge", "Data retention purge (dry-run by default; never audit/legal-hold)", 1440),
    ("sandbox.expiry", "Sandbox inactivity warnings + purge (sandbox tenants only)", 1440),
    ("sandbox.demo_reset", "Nightly reset of the shared demo account sandbox", 1440),
]
STALE_MINUTES = 30


def now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_defaults(db: Session) -> None:
    for jt, label, mins in DEFAULT_SCHEDULES:
        if not db.scalar(select(ScheduledJob.id).where(ScheduledJob.job_type == jt)):
            db.add(ScheduledJob(job_type=jt, label=label, interval_minutes=mins, next_run_at=now()))
    db.flush()


def _retry_due(db: Session) -> bool:
    from app.models import EmassChange

    return db.scalar(select(EmassChange.id).where(EmassChange.status == "pending_retry").limit(1)) is not None


def tick(db: Session) -> list[str]:
    db.execute(update(Job).where(Job.status == "running", Job.locked_at < now() - timedelta(minutes=STALE_MINUTES))
               .values(status="queued", locked_by=None, error="requeued: worker lost (stale lock)"))
    enqueued = []
    for sj in db.scalars(select(ScheduledJob).where(ScheduledJob.enabled.is_(True), ScheduledJob.next_run_at <= now()).with_for_update(skip_locked=True)):
        sj.next_run_at = now() + timedelta(minutes=sj.interval_minutes)
        if jobsvc.has_pending(db, sj.job_type):
            sj.last_status = "skipped_already_pending"
            continue
        if sj.job_type == "emass.retry" and not _retry_due(db):
            sj.last_status = "idle_queue_empty"
            continue
        job = jobsvc.enqueue(db, sj.job_type, {"scheduled": True, "schedule_id": str(sj.id)})
        sj.last_job_id, sj.last_enqueued_at, sj.last_status = job.id, now(), "queued"
        enqueued.append(sj.job_type)
    db.commit()
    return enqueued


def run_now(db: Session, sj: ScheduledJob, user_id) -> Job | None:
    if jobsvc.has_pending(db, sj.job_type):
        return None
    job = jobsvc.enqueue(db, sj.job_type, {"scheduled": False, "schedule_id": str(sj.id)}, requested_by=user_id)
    sj.last_job_id, sj.last_enqueued_at, sj.last_status = job.id, now(), "queued"
    return job


def record_result(db: Session, job: Job) -> None:
    sj = db.scalar(select(ScheduledJob).where(ScheduledJob.job_type == job.job_type))
    if sj is None:
        return
    sj.last_run_at, sj.last_status, sj.last_job_id = now(), job.status, job.id
    sj.last_error = (job.error or "")[:1000] if job.status != "succeeded" else None
    sj.last_result = job.result if job.status == "succeeded" else None
    sj.run_count += job.status == "succeeded"
