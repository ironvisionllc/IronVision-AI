"""Postgres-backed job worker: claims jobs with FOR UPDATE SKIP LOCKED, writes heartbeats."""
import logging
import os
import signal
import socket
import time
import traceback
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.db import SessionLocal
from app.logging_setup import configure_logging, correlation_id_var
from app.models import Job, WorkerHeartbeat
from app.services import audit
from app.services import scheduler
from worker.handlers import HANDLERS

log = logging.getLogger("aegis.worker")
WORKER_ID = os.environ.get("WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}"
_running = True

CLAIM_SQL = text("""
UPDATE jobs SET status='running', locked_by=:worker, locked_at=now(), started_at=now(),
       attempts=attempts+1, updated_at=now()
WHERE id = (
  SELECT id FROM jobs WHERE status='queued' AND run_after <= now()
  ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
) RETURNING id
""")


def _stop(*_):
    global _running
    _running = False


def heartbeat() -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        stmt = pg_insert(WorkerHeartbeat).values(worker_id=WORKER_ID, last_seen_at=now,
                                                 info={"handlers": sorted(HANDLERS), "pid": os.getpid()})
        db.execute(stmt.on_conflict_do_update(index_elements=["worker_id"],
                                              set_={"last_seen_at": now, "updated_at": now, "info": stmt.excluded.info}))
        db.commit()


def run_once() -> bool:
    with SessionLocal() as db:
        job_id = db.scalar(CLAIM_SQL, {"worker": WORKER_ID})
        db.commit()
    if job_id is None:
        return False
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        correlation_id_var.set(job.correlation_id or str(job.id))
        handler = HANDLERS.get(job.job_type)
        log.info("Job started", extra={"job_id": str(job.id), "job_type": job.job_type})
        try:
            if handler is None:
                raise RuntimeError(f"No handler for job type {job.job_type}")
            result = handler(db, job.payload or {})
            job.status, job.result, job.error = "succeeded", result, None
            job.finished_at = datetime.now(timezone.utc)
            scheduler.record_result(db, job)
            audit.record(db, action="job.succeeded", entity_type="job", entity_id=str(job.id),
                         actor_email=f"worker:{WORKER_ID}", details={"job_type": job.job_type})
            db.commit()
            log.info("Job succeeded", extra={"job_id": str(job.id), "result": result})
        except Exception as exc:
            db.rollback()
            job = db.get(Job, job_id)
            job.error = f"{exc}\n{traceback.format_exc()}"[:8000]
            if job.attempts < job.max_attempts:
                job.status = "queued"
                job.run_after = datetime.now(timezone.utc) + timedelta(seconds=30 * job.attempts)
            else:
                job.status = "failed"
                job.finished_at = datetime.now(timezone.utc)
            scheduler.record_result(db, job)
            audit.record(db, action="job.failed", outcome="failure", entity_type="job", entity_id=str(job.id),
                         actor_email=f"worker:{WORKER_ID}", details={"job_type": job.job_type, "error": str(exc)[:500]})
            db.commit()
            log.exception("Job failed", extra={"job_id": str(job_id)})
    return True


def main() -> None:
    s = get_settings()
    configure_logging(s.log_level)
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    log.info("Worker starting", extra={"worker_id": WORKER_ID, "handlers": sorted(HANDLERS)})
    last_beat = 0.0
    last_sched = 0.0
    interval = float(os.environ.get("SCHEDULER_TICK_SECONDS", "30"))
    while _running:
        try:
            if time.monotonic() - last_beat > 5:
                heartbeat()
                last_beat = time.monotonic()
            if time.monotonic() - last_sched > interval:
                with SessionLocal() as db:
                    scheduler.ensure_defaults(db)
                    scheduler.tick(db)
                last_sched = time.monotonic()
            if not run_once():
                time.sleep(s.worker_poll_seconds)
        except Exception:
            log.exception("Worker loop error")
            time.sleep(s.worker_poll_seconds)
    log.info("Worker stopped")


if __name__ == "__main__":
    main()
