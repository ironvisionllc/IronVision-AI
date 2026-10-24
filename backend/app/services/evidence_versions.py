"""Evidence lifecycle: immutable versions (old objects and hashes kept), logical removal with legal-hold enforcement,
revalidation flags on dependent mappings and TR rows. Permanent deletion is not offered."""
import hashlib
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ControlAssignment, Evidence, EvidenceControl, EvidenceVersion, TrAnalysis, TrRow
from app.services.storage import get_storage

CHANGED = "Evidence changed – re-review"


def now():
    return datetime.now(timezone.utc)


def versions(db: Session, ev: Evidence) -> list[EvidenceVersion]:
    vs = list(db.scalars(select(EvidenceVersion).where(EvidenceVersion.evidence_id == ev.id).order_by(EvidenceVersion.version.desc())))
    if not vs:  # evidence created after migration but before the first version write
        vs = [_snapshot(db, ev, ev.provenance.get("received_by") if ev.provenance else None, "Initial version")]
    return vs


def _snapshot(db: Session, ev: Evidence, who: str | None, reason: str, scan: str | None = None) -> EvidenceVersion:
    v = EvidenceVersion(evidence_id=ev.id, version=ev.version, file_name=ev.file_name, storage_key=ev.storage_key, sha256=ev.sha256, size_bytes=ev.size_bytes,
                        content_type=ev.content_type, uploaded_by=who, reason=reason, scan_result=scan)
    db.add(v)
    db.flush()
    return v


def flag_dependents(db: Session, ev: Evidence, why: str) -> dict:
    links = list(db.scalars(select(EvidenceControl).where(EvidenceControl.evidence_id == ev.id, EvidenceControl.removed_at.is_(None))))
    for link in links:
        link.needs_revalidation, link.revalidation_reason = True, why
    eid = str(ev.id)
    row_ids = {a.row_id for a in db.scalars(select(TrAnalysis).where(TrAnalysis.input_ids.contains([eid])))}
    rows = [r for r in db.scalars(select(TrRow).where(TrRow.id.in_(row_ids)))] if row_ids else []
    rows += [r for r in db.scalars(select(TrRow).where(TrRow.sources.is_not(None))) if r not in rows and eid in str(r.sources)]
    for r in rows:
        r.flags = [f for f in (r.flags or []) if eid not in str(f)] + [f"{CHANGED} (evidence {eid}): {why}"]
    return {"control_mappings": len(links), "tr_rows": len(rows)}


def new_version(db: Session, ev: Evidence, file_name: str, data: bytes, reason: str, actor: str, scan: str | None) -> tuple[EvidenceVersion, dict]:
    if ev.status != "active":
        raise ValueError("This evidence was removed – it can't get a new version")
    versions(db, ev)  # make sure the current file is in the history before replacing it
    sha = hashlib.sha256(data).hexdigest()
    key = f"evidence/{ev.system_id}/{sha}/v{ev.version + 1}/{file_name}"
    store = get_storage()
    if not store.exists(key):
        store.put(key, data, "application/octet-stream")
    ev.version += 1
    ev.file_name, ev.storage_key, ev.sha256, ev.size_bytes, ev.content_type = file_name, key, sha, len(data), file_name.rsplit(".", 1)[-1]
    ev.replacement_reason, ev.uploaded_by, ev.collected_at = reason, actor, now()
    ev.integrity_status, ev.review_status = "hash_recorded", "needs_rereview"
    v = _snapshot(db, ev, actor, reason, scan)
    return v, flag_dependents(db, ev, f"New version {ev.version}: {reason}")


def remove(db: Session, ev: Evidence, reason: str, actor: str) -> dict:
    if ev.legal_hold:
        raise PermissionError("This evidence is under legal hold – it can't be removed until the hold is lifted")
    if ev.status == "removed":
        raise ValueError("Already removed")
    impact = flag_dependents(db, ev, f"Evidence removed: {reason}")
    for link in db.scalars(select(EvidenceControl).where(EvidenceControl.evidence_id == ev.id, EvidenceControl.removed_at.is_(None))):
        link.removed_at = now()
    ev.status, ev.removed_reason, ev.removed_by, ev.removed_at = "removed", reason, actor, now()
    return impact


def meta(db: Session, ev: Evidence, with_history: bool) -> dict:
    links = db.execute(select(ControlAssignment.control_id, EvidenceControl.needs_revalidation, EvidenceControl.revalidation_reason, EvidenceControl.removed_at)
                       .join(EvidenceControl, EvidenceControl.assignment_id == ControlAssignment.id).where(EvidenceControl.evidence_id == ev.id)).all()
    out = {"evidence_id": str(ev.id), "name": ev.name, "version": ev.version, "file_name": ev.file_name, "type": ev.evidence_type,
           "upload_date": ev.collected_at.isoformat() if ev.collected_at else None,
           "uploaded_by": ev.uploaded_by or (ev.provenance or {}).get("received_by"), "status": ev.status, "replacement_reason": ev.replacement_reason,
           "sha256": ev.sha256, "review_status": ev.review_status, "expiration": ev.expires_at.isoformat() if ev.expires_at else None,
           "freshness_window_days": ev.freshness_window_days, "legal_hold": ev.legal_hold, "removed_reason": ev.removed_reason, "removed_by": ev.removed_by,
           "related_controls": [{"control_id": c, "needs_revalidation": nr, "reason": rr, "removed": bool(rm)} for c, nr, rr, rm in links],
           "version_count": db.scalar(select(func.count()).select_from(EvidenceVersion).where(EvidenceVersion.evidence_id == ev.id)) or 1,
           "permanent_deletion": "Not offered – evidence is only removed logically; objects and hashes are retained for the audit trail and retention policy."}
    if with_history:
        out["versions"] = [{"version": v.version, "file_name": v.file_name, "sha256": v.sha256, "size_bytes": v.size_bytes, "uploaded_by": v.uploaded_by,
                            "reason": v.reason, "scan_result": v.scan_result, "created_at": v.created_at.isoformat() if v.created_at else None,
                            "active": v.version == ev.version and ev.status == "active"} for v in versions(db, ev)]
    return out
