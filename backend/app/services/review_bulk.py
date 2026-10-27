"""Server-side bulk review-queue decisions (no 500-item request limit): items are chosen by filter on the server ("select all matching"),
processed by the worker in batches of BATCH with one transaction per batch, per-item audit, result = succeeded / failed (reason) / skipped
(already decided – no longer open). Idempotency key prevents double submit; retry re-runs only the failed items."""
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Job, RoleAssignment, System, User

BATCH = 100
JOB = "review.bulk"


def current_queue(db: Session, system: System) -> list[dict]:
    from app.services import policy_coverage as pc
    from app.services import review_queue as rq
    return rq.status_suggestions(db, system) + pc.suggestions(db, system, [], []) + rq.policy_proposals(db, system) + rq.automated_maps(db, system.id)


def _item(q: dict) -> dict:
    return {"key": q["key"], "kind": q["kind"], "ids": q["ids"], "control_id": q["control_id"], "evidence_fp": q.get("evidence_fp")}


def select_items(db: Session, system: System, keys: list[str] | None, kind: str, sca: bool) -> list[dict]:
    q = current_queue(db, system)
    if keys is not None:
        want = set(keys)
        return [_item(x) for x in q if x["key"] in want]
    return [_item(x) for x in q if (bool(x.get("awaiting_sca")) == sca) and (sca or not kind or x["kind"] == kind)]


def view(job: Job, db: Session | None = None) -> dict:
    r = job.result or {}
    ahead = None
    if db is not None and job.status == "queued":
        from sqlalchemy import func
        ahead = db.scalar(select(func.count()).select_from(Job).where(Job.job_type == JOB, Job.status.in_(("queued", "running")),
                                                                     Job.created_at < job.created_at, Job.id != job.id))
    return {"id": str(job.id), "status": job.status, "total": job.payload.get("total", 0), "processed": r.get("processed", 0),
            "succeeded": r.get("succeeded", 0), "failed": r.get("failed", []), "skipped": r.get("skipped", []), "batches": r.get("batches", 0),
            "action": job.payload.get("action"), "retry_of": job.payload.get("retry_of"), "error": (job.error or "")[:300] or None,
            "finished_at": job.finished_at.isoformat() if job.finished_at else None, "queued_behind": ahead,
            "lane": "interactive (separate from policy/AI analysis)"}


def start(db: Session, system: System, current, action: str, just: str, edit: list[str], items: list[dict], idem: str, retry_of: str | None = None) -> Job:
    from app.services import audit, jobs
    if (j := db.scalar(select(Job).where(Job.job_type == JOB, Job.correlation_id == idem))) is not None:
        return j  # double submit / refresh → same job
    if not items:
        raise HTTPException(422, "Nothing matches – the selected items are no longer open")
    if action in ("reject", "edit") and len(just) < 10:
        raise HTTPException(422, "Please give a reason (at least 10 characters) – it is required to reject or edit and is kept in the audit history.")
    job = jobs.enqueue(db, JOB, {}, requested_by=current.user.id)
    job.correlation_id, job.max_attempts = idem, 3
    job.payload = {"job_id": str(job.id), "system_id": str(system.id), "user_id": str(current.user.id),
                   "operator_id": str(current.operator.id) if current.operator else None, "action": action, "justification": just, "edit": edit,
                   "items": items, "total": len(items), "retry_of": retry_of}
    job.result = {"processed": 0, "succeeded": 0, "failed": [], "skipped": [], "batches": 0}
    audit.record(db, action="mapping_review.bulk_started", actor_user_id=current.user.id, actor_email=current.user.email, entity_type="system",
                 entity_id=str(system.id), after={"job_id": str(job.id), "action": action, "total": len(items), "retry_of": retry_of, "justification": just})
    return job


def _still_open(db: Session, system: System, items: list[dict]) -> set[str]:
    """Keys of items that are still undecided. Cheap per-row checks; the full queue is only rebuilt for status suggestions."""
    from app.models import FindingControlMap, PolicyControlMap
    out = set()
    for it in items:
        if it["kind"] == "policy_map":
            m = db.get(PolicyControlMap, uuid.UUID(it["ids"][0]))
            if m is not None and m.valid_to is None and m.status == "proposed":
                out.add(it["key"])
        elif it["kind"] == "finding_map":
            if any((m := db.get(FindingControlMap, uuid.UUID(i))) is not None and m.valid_to is None and m.review_status == "auto_from_authoritative_source"
                   for i in it["ids"]):
                out.add(it["key"])
    if any(it["kind"] in ("status", "policy_status") for it in items):
        out |= {q["key"] for q in current_queue(db, system)}
    return out


def run(db: Session, payload: dict) -> dict:
    """Worker handler. Re-runnable: items already decided are no longer in the open queue → skipped, never decided twice."""
    from app.api.v1.phase4 import decide_item
    from app.security.deps import CurrentUser
    from app.security.rbac import has_permission
    from app.services.evaluation import evaluate_system

    job = db.get(Job, uuid.UUID(payload["job_id"]))
    system = db.get(System, uuid.UUID(payload["system_id"]))
    user = db.get(User, uuid.UUID(payload["user_id"]))
    op = db.get(User, uuid.UUID(payload["operator_id"])) if payload.get("operator_id") else None
    cur = CurrentUser(user=user, assignments=list(db.scalars(select(RoleAssignment).where(RoleAssignment.user_id == user.id))), auth_provider="bulk-job", operator=op)
    can = lambda p: has_permission(cur.assignments, p, user.org_id, system.id)  # noqa: E731
    action, just, edit = payload["action"], payload["justification"], payload["edit"]
    res = dict(job.result or {"processed": 0, "succeeded": 0, "failed": [], "skipped": [], "batches": 0})
    done = {x["key"] for x in res["failed"] + res["skipped"]} | set(res.get("succeeded_keys", []))
    todo = [i for i in payload["items"] if i["key"] not in done]
    meta = {"user_agent": f"bulk-job:{job.id}"}
    from app.services import policy_coverage as pc
    from app.services import policy_mapping as pm
    for b in range(0, len(todo), BATCH):
        batch = todo[b:b + BATCH]
        open_keys = _still_open(db, system, batch)
        ok_keys, failed, skipped = [], [], []
        pending: dict = {}
        tok = pm.DEFER_ANALYZE.set(pending)
        for it in batch:
            if it["key"] not in open_keys:
                skipped.append({"key": it["key"], "control_id": it["control_id"], "reason": "Already decided – no longer in the open queue"})
                continue
            if not (can("finding.map") or (it["kind"] == "status" and can("assessment.perform"))) or (
                    action == "approve" and it["kind"] in ("status", "policy_status") and not (can("implementation.write") or can("assessment.perform"))):
                failed.append({"key": it["key"], "control_id": it["control_id"], "reason": "Your role cannot approve this item (permission)"})
                continue
            sp = db.begin_nested()
            try:
                r = {"approved": 0, "rejected": 0, "edited": 0, "partial": []}
                decide_item(db, system, SimpleNamespace(**it), action, just, edit, cur, can("assessment.perform"), r, meta)
                sp.commit()
                ok_keys.append(it["key"])
            except Exception as exc:  # noqa: BLE001 – recorded per item, never silently dropped
                sp.rollback()
                failed.append({"key": it["key"], "control_id": it["control_id"], "reason": getattr(exc, "detail", None) or str(exc)[:300]})
        pm.DEFER_ANALYZE.reset(tok)
        for pol in pending.values():
            pc.analyze(db, pol)
        evaluate_system(db, system.id)
        res = {**res, "processed": res["processed"] + len(batch), "succeeded": res["succeeded"] + len(ok_keys),
               "succeeded_keys": res.get("succeeded_keys", []) + ok_keys, "failed": res["failed"] + failed, "skipped": res["skipped"] + skipped,
               "batches": res["batches"] + 1}
        job.result = res
        db.commit()  # one transaction per batch – partial success is durable and visible as progress
    from app.services import audit
    audit.record(db, action="mapping_review.bulk_finished", actor_user_id=user.id, actor_email=user.email, entity_type="system", entity_id=str(system.id),
                 after={"job_id": str(job.id), "succeeded": res["succeeded"], "failed": len(res["failed"]), "skipped": len(res["skipped"]),
                        "finished_at": datetime.now(timezone.utc).isoformat()})
    return res
