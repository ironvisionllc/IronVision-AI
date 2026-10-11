"""Data retention purge. Policies live in retention_policies (disabled + dry-run by default).
Hard guarantees: audit_events are never deleted and evidence under legal hold is never deleted; evidence referenced by
findings, controls, POA&Ms or attestations is never deleted."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from app.models import Job, Notification, RetentionPolicy
from app.services import audit

NEVER = {"audit_events"}
DEFAULTS = [
    ("notifications", 365, "Acknowledged in-app notifications older than N days"),
    ("jobs", 90, "Finished worker jobs (succeeded/failed) older than N days"),
    ("evidence_unreferenced", 2555, "Superseded evidence not referenced by any record and not on legal hold (7 years)"),
    ("audit_events", 0, "NEVER purged – listed for transparency; the purge job refuses this type"),
]


def ensure_defaults(db: Session) -> None:
    for rt, days, d in DEFAULTS:
        if not db.scalar(select(RetentionPolicy.id).where(RetentionPolicy.record_type == rt)):
            db.add(RetentionPolicy(record_type=rt, retain_days=days, description=d))
    db.flush()


def _candidates(db: Session, rt: str, cutoff: datetime):
    if rt == "notifications":
        return select(Notification.id).where(Notification.created_at < cutoff, Notification.read_at.is_not(None))
    if rt == "jobs":
        return select(Job.id).where(Job.finished_at < cutoff, Job.status.in_(("succeeded", "failed")))
    if rt == "evidence_unreferenced":
        return text("""select e.id from evidence e where e.collected_at < :cutoff and not e.legal_hold
            and not exists (select 1 from evidence_controls x where x.evidence_id=e.id)
            and not exists (select 1 from findings f where f.latest_evidence_id=e.id)
            and not exists (select 1 from finding_observations o where o.evidence_id=e.id)
            and not exists (select 1 from attestations a where a.evidence_id=e.id)""").bindparams(cutoff=cutoff)
    raise ValueError(rt)


def purge(db: Session, force_dry_run: bool = False) -> dict:
    ensure_defaults(db)
    out = {}
    for p in db.scalars(select(RetentionPolicy).order_by(RetentionPolicy.record_type)):
        if p.record_type in NEVER:
            out[p.record_type] = {"skipped": "never purged"}
            continue
        if not p.enabled:
            out[p.record_type] = {"skipped": "disabled"}
            continue
        cutoff = datetime.now(timezone.utc) - timedelta(days=p.retain_days)
        q = _candidates(db, p.record_type, cutoff)
        ids = [r[0] for r in db.execute(q)]
        dry = p.dry_run or force_dry_run
        if ids and not dry:
            if p.record_type == "evidence_unreferenced":
                from app.models import Evidence
                from app.services.storage import get_storage
                st = get_storage()
                for e in db.scalars(select(Evidence).where(Evidence.id.in_(ids))):
                    st.delete(e.storage_key) if hasattr(st, "delete") else None
                    db.delete(e)
            else:
                model = Notification if p.record_type == "notifications" else Job
                db.execute(delete(model).where(model.id.in_(ids)))
        p.last_run_at, p.last_result = datetime.now(timezone.utc), {"candidates": len(ids), "deleted": 0 if dry else len(ids), "dry_run": dry}
        out[p.record_type] = p.last_result
    audit.record(db, action="retention.purge", actor_email="system", details=out)
    return out


_ = func
