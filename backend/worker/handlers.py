import os
import uuid
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.services.content.loader import load_reference_content
from app.services.jobs import JOB_CONTENT_LOAD


def handle_content_load(db: Session, payload: dict) -> dict:
    result = load_reference_content(db, force=bool(payload.get("force")))
    if os.environ.get("SAMPLES_DIR") and os.environ.get("SEED_DEMO_DATA", "").lower() == "true":
        from app.seed import seed_demo

        db.flush()
        seed_demo(db, os.environ["DEMO_USER_PASSWORD"])
    return result


def handle_ingest(db: Session, payload: dict) -> dict:
    from app.services.ingest.pipeline import process_run

    return process_run(db, uuid.UUID(payload["run_id"]))


def handle_integrity(db: Session, payload: dict) -> dict:
    from app.services.evaluation import verify_integrity

    sid = payload.get("system_id")
    return verify_integrity(db, uuid.UUID(sid) if sid else None)


def handle_freshness(db: Session, payload: dict) -> dict:
    from app.services.evaluation import evaluate_freshness, snapshot_due, take_snapshots

    from app.services.rmf import expire_attestations, generate_deadline_notifications

    res = evaluate_freshness(db)
    if not payload.get("scheduled"):
        res["attestations"], res["notifications_created"] = expire_attestations(db), generate_deadline_notifications(db)
        if snapshot_due(db):
            take_snapshots(db, trigger="daily")
            res["snapshot"] = True
    return res


def handle_attestations(db: Session, payload: dict) -> dict:
    from app.services.rmf import expire_attestations
    return expire_attestations(db)


def handle_notifications(db: Session, payload: dict) -> dict:
    from app.services.rmf import generate_deadline_notifications
    return {"created": generate_deadline_notifications(db)}


def handle_risk_snapshot(db: Session, payload: dict) -> dict:
    from app.services.evaluation import snapshot_due, take_snapshots
    from app.services.risk import recompute
    n = recompute(db)
    snap = snapshot_due(db) or not payload.get("scheduled")
    if snap:
        take_snapshots(db, trigger="daily")
    return {"findings_scored": n, "snapshot": bool(snap)}


def handle_connectors(db: Session, payload: dict) -> dict:
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import select

    from app.models import EvidenceSource
    from app.services.connectors import SOURCE_TYPES, adapter_for
    from app.services.evaluation import evaluate_system

    t, out, systems = datetime.now(timezone.utc), [], set()
    for src in db.scalars(select(EvidenceSource).where(EvidenceSource.enabled.is_(True), EvidenceSource.schedule_hours.is_not(None),
                                                       EvidenceSource.adapter == "mock", EvidenceSource.source_type != "emass")):
        if src.next_run_at and src.next_run_at > t or SOURCE_TYPES.get(src.source_type, ("", ""))[1] != "mock":
            continue
        r = adapter_for(src.source_type).collect(db, src)
        src.last_run_at, src.next_run_at, src.health = t, t + timedelta(hours=src.schedule_hours), "ok"
        systems.add(src.system_id)
        out.append({"source": src.name, **r})
    db.flush()
    for sid in systems:
        evaluate_system(db, sid)
    return {"collected_sources": len(out), "details": out[:20]}


def handle_kev(db: Session, payload: dict) -> dict:
    from app.services.kev import reevaluate
    return reevaluate(db, trigger="scheduled" if payload.get("scheduled") else "manual")


def handle_emass_retry(db: Session, payload: dict) -> dict:
    from app.services.emass import retry_due
    return retry_due(db)


def handle_policy_analyze(db: Session, payload: dict) -> dict:

    from app.models import Policy

    pol = db.get(Policy, uuid.UUID(payload["policy_id"]))
    try:
        return _policy_analyze(db, pol)
    except Exception as exc:  # no silent failures: the policy shows "Failed (reason)" with a Retry button
        db.rollback()
        pol = db.get(Policy, uuid.UUID(payload["policy_id"]))
        pol.analysis_status = "failed"
        pol.analysis = {**(pol.analysis or {}), "error": f"{type(exc).__name__}: {exc}"[:500]}
        db.commit()
        raise


def _policy_analyze(db: Session, pol) -> dict:
    import asyncio

    from app.services.ai.service import get_ai_service
    from app.services.rmf import analyze_policy, get_setting, AI_DEFAULTS

    ai_out, iid, ai_note = None, None, "AI not configured – deterministic extractor only"
    svc = get_ai_service()
    if svc.configured and get_setting(db, pol.org_id, "ai", AI_DEFAULTS)["use_cases"].get("policy.audit"):
        try:
            r = asyncio.run(svc.run("policy.audit", "1.0.0", {"text": (pol.text_content or "")[:12000]}))
            ai_out, iid, ai_note = r.output.model_dump(), r.interaction_id, f"AI {r.model}"
        except Exception as exc:  # AI failure must not block deterministic findings
            ai_note = f"AI step failed: {exc}"[:300]
    import os

    use_ai = svc.configured and get_setting(db, pol.org_id, "ai", AI_DEFAULTS)["use_cases"].get("policy.audit") and not os.environ.get("PYTEST_CURRENT_TEST")
    found = analyze_policy(db, pol, ai_out, iid, use_ai=bool(use_ai))
    pol.analysis = {**(pol.analysis or {}), "ai_note": ai_note}
    from app.services import audit
    audit.record(db, action="policy.analyzed", actor_email="worker", entity_type="policy", entity_id=str(pol.id),
                 details={"proposed_findings": len(found), "ai": ai_note})
    return {"proposed_findings": len(found), "ai": ai_note}


HANDLERS: dict[str, Callable[[Session, dict], dict]] = {
    JOB_CONTENT_LOAD: handle_content_load,
    "ingest.process": handle_ingest,
    "evidence.verify_integrity": handle_integrity,
    "evidence.evaluate_freshness": handle_freshness,
    "policy.analyze": handle_policy_analyze,
    "attestations.evaluate": handle_attestations,
    "notifications.deadlines": handle_notifications,
    "risk.snapshot": handle_risk_snapshot,
    "connectors.collect": handle_connectors,
    "kev.reevaluate": handle_kev,
    "emass.retry": handle_emass_retry,
    "sandbox.provision": lambda db, payload: __import__("app.services.sandbox", fromlist=["provision"]).provision(db, __import__("uuid").UUID(payload["org_id"])),
    "sandbox.expiry": lambda db, payload: __import__("app.services.sandbox", fromlist=["run_expiry"]).run_expiry(db),
    "sandbox.demo_reset": lambda db, payload: __import__("app.services.sandbox", fromlist=["reset_demo_account"]).reset_demo_account(db),
    "retention.purge": lambda db, payload: __import__("app.services.retention", fromlist=["purge"]).purge(db),
}
