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
    from app.models import IngestRun
    from app.services import jobs
    from app.services.ingest.pipeline import process_run

    res = process_run(db, uuid.UUID(payload["run_id"]))
    run = db.get(IngestRun, uuid.UUID(payload["run_id"]))
    if run is not None and not payload.get("skip_inventory_check"):
        jobs.enqueue(db, "inventory.check", {"system_id": str(run.system_id)})  # scans change inventory consistency
    return res


def handle_inventory_import(db: Session, payload: dict) -> dict:
    from app.models import InventoryImport
    from app.services.inventory import hwsw

    imp = db.get(InventoryImport, uuid.UUID(payload["import_id"]))
    imp.status = "processing"
    db.commit()
    try:
        counts = hwsw.run_import(db, imp, payload.get("actor_email"))
    except Exception as exc:  # visible "Failed (reason)"
        db.rollback()
        imp = db.get(InventoryImport, uuid.UUID(payload["import_id"]))
        imp.status, imp.error = "failed", f"{exc}"[:500]
        db.commit()
        raise
    return counts


def handle_inventory_check(db: Session, payload: dict) -> dict:
    from app.services.inventory import consistency

    return consistency.run(db, uuid.UUID(payload["system_id"]))


def handle_inventory_ai(db: Session, payload: dict) -> dict:
    from app.services.inventory import ai

    return ai.run(db, payload["kind"], uuid.UUID(payload["id"]), uuid.UUID(payload["actor_id"]) if payload.get("actor_id") else None)


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


def handle_tr_detect(db: Session, payload: dict) -> dict:
    from app.models import TrWorkbook
    from app.services.tr import service as trs

    wb = db.get(TrWorkbook, uuid.UUID(payload["workbook_id"]))
    wb.status = "processing"
    db.commit()
    try:
        trs.detect_and_match(db, wb)
    except Exception as exc:  # visible "Failed (reason)"
        db.rollback()
        wb = db.get(TrWorkbook, uuid.UUID(payload["workbook_id"]))
        wb.status, wb.error = "failed", f"{exc}"[:500]
        db.commit()
        raise
    return wb.counts


def handle_tr_generate(db: Session, payload: dict) -> dict:
    from app.models import TrWorkbook
    from app.services.tr import service as trs

    wb = db.get(TrWorkbook, uuid.UUID(payload["workbook_id"]))
    return trs.generate(db, wb, populate=bool(payload.get("populate")))


def handle_tr_analyze(db: Session, payload: dict) -> dict:
    from sqlalchemy import select

    from app.models import TrRow, TrWorkbook
    from app.services.tr import analysis

    wb = db.get(TrWorkbook, uuid.UUID(payload["workbook_id"]))
    actor = uuid.UUID(payload["actor_id"]) if payload.get("actor_id") else None
    modes: dict = {}
    for r in db.scalars(select(TrRow).where(TrRow.workbook_id == wb.id, TrRow.id.in_([uuid.UUID(i) for i in payload["row_ids"]]))):
        a = analysis.analyze_row(db, wb, r, actor)
        modes[a.mode] = modes.get(a.mode, 0) + 1
        db.commit()
    return modes


def handle_policy_analyze(db: Session, payload: dict) -> dict:

    from app.models import Policy

    pol = db.get(Policy, uuid.UUID(payload["policy_id"]))
    pol.analysis_status = "processing"  # visible as "Processing…" while the job runs
    from app.services.policy_analyzer_v2 import with_history
    pol.analysis = {**(pol.analysis or {}), "progress": with_history((pol.analysis or {}).get("progress"), {
        "phase": "extract", "stage": "1/4 reading the policy and identifying controls", "pct": 2, "label": "analysis in progress", "elapsed_s": 0})}
    db.commit()
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

    import time as _t
    t_start = _t.perf_counter()
    import os
    from concurrent.futures import ThreadPoolExecutor

    ai_out, iid, ai_note = None, None, "AI not configured – deterministic extractor only"
    svc = get_ai_service()
    audit_on = svc.configured and get_setting(db, pol.org_id, "ai", AI_DEFAULTS)["use_cases"].get("policy.audit")
    use_ai = audit_on and not os.environ.get("PYTEST_CURRENT_TEST")
    text_ = pol.text_content or ""
    db.commit()  # read-only so far: never hold a transaction open across an external AI call

    def _audit():  # no DB transaction held across the AI call; runs concurrently with the coverage AI (was strictly before it)
        import hashlib

        from app.services import policy_analyzer_v2 as v2
        from app.services import policy_coverage as pc_
        t = _t.perf_counter()
        use_cache = pc_.analyzer() == "v2"
        model = svc.provider.model if svc.provider else None
        key = hashlib.sha256(f"policy.audit|1.1.0|{pol.org_id}|{model}|{text_[:60000]}".encode()).hexdigest()  # tenant-scoped like v2 batches
        hit = v2._cache_get(pol.org_id, key) if use_cache else None
        if hit:
            return hit["output"], uuid.UUID(hit["interaction_id"]) if hit.get("interaction_id") else None, f"AI {hit.get('model')} (cached)", _t.perf_counter() - t
        try:
            r = asyncio.run(svc.run("policy.audit", "1.1.0", {"text": text_[:60000]}))  # 1.0.0 had "ac-17" as its example ID and saw only 12k chars
            if use_cache:
                v2._cache_put(pol.org_id, key, r.model, {"output": r.output.model_dump(), "interaction_id": str(r.interaction_id) if r.interaction_id else None,
                                                         "model": r.model}, {"policy_id": str(pol.id), "prompt": "policy.audit@1.1.0"})
            return r.output.model_dump(), r.interaction_id, f"AI {r.model}", _t.perf_counter() - t
        except Exception as exc:  # AI failure must not block deterministic findings
            return None, None, f"AI step failed: {exc}"[:300], _t.perf_counter() - t
    ex = ThreadPoolExecutor(max_workers=1)
    fut = ex.submit(_audit) if audit_on else None
    t_audit = _t.perf_counter()
    pre = None
    from sqlalchemy import select as _sel

    from app.models import PolicyControlMap
    from app.services import policy_coverage as pc
    from app.services import policy_mapping as pm
    cids = {m["control_id"] for m in pm.extract_mappings(db, text_) if m["confidence"] in ("High", "Medium") and not m.get("not_selected")}
    cids |= set(db.scalars(_sel(PolicyControlMap.control_id).where(PolicyControlMap.policy_id == pol.id, PolicyControlMap.valid_to.is_(None),
                                                                    PolicyControlMap.status == "mapped")))
    in_scope = pc.in_scope_requirements(db, cids)  # one denominator: live progress and the final summary count the same requirements
    db.commit()
    if use_ai:  # coverage AI runs BEFORE any analysis write, with no open transaction (was: minutes "idle in transaction" holding row locks)
        pre = pc.prefetch_ai(db, pol, cids, in_scope)
    from app.services.policy_analyzer_v2 import _progress
    if pre is None:  # AI off / v-current: the same four stages, deterministic only
        _progress(pol.id, {"phase": "screen", "stage": "2/4 screening controls (deterministic only – AI review off)", "pct": 10, "label": "analysis in progress",
                           "requirements_in_scope": in_scope, "elapsed_s": round(_t.perf_counter() - t_start, 1)})
        _progress(pol.id, {"phase": "AI review", "stage": "3/4 checking requirements (deterministic)", "pct": 50, "label": "analysis in progress",
                           "requirements_in_scope": in_scope, "elapsed_s": round(_t.perf_counter() - t_start, 1)})
    audit_s = 0.0
    if fut is not None:
        _progress(pol.id, {"phase": "audit", "stage": "4/4 waiting for the policy audit", "pct": 88, "label": "analysis in progress",
                           "elapsed_s": round(_t.perf_counter() - t_start, 1)})
        ai_out, iid, ai_note, audit_s = fut.result()
    _progress(pol.id, {"phase": "validate", "stage": "4/4 validating quotes and writing results", "pct": 92, "label": "analysis in progress",
                       "audit_suggestions": len((ai_out or {}).get("findings") or []), "requirements_in_scope": in_scope,
                       "elapsed_s": round(_t.perf_counter() - t_start, 1)})
    db.expire(pol)
    ex.shutdown()
    prog = (pol.analysis or {}).get("progress")
    t_pre = _t.perf_counter()
    found = analyze_policy(db, pol, ai_out, iid, use_ai=bool(use_ai), ai_prefetched=pre)
    tm = {**((pol.analysis or {}).get("timing_s") or {}), "policy_audit_ai_concurrent": round(audit_s, 2), "setup": round(t_audit - t_start, 2),
          "coverage_ai_prefetch_and_audit_join": round(t_pre - t_audit, 2),
          "store_and_coverage": round(_t.perf_counter() - t_pre, 2)}
    from sqlalchemy import func, select

    from app.models import PolicyRequirementCoverage as _PRC
    from app.services.policy_analyzer_v2 import with_history
    st = dict(db.execute(select(_PRC.status, func.count()).where(_PRC.policy_id == pol.id).group_by(_PRC.status)).all())
    el = round(_t.perf_counter() - t_start, 1)
    final = with_history(prog, {"phase": "done", "stage": f"Completed in {el:g} s", "pct": 100, "label": "analysis complete", "elapsed_s": el,
                                "requirements_analyzed": sum(st.values()), "requirement_gaps": st.get("missing", 0) + st.get("partial", 0),
                                "requirements_in_scope": in_scope, "audit_suggestions": len((ai_out or {}).get("findings") or []),
                                "audit_findings": len(found), "audit_note": _audit_note(pol, ai_out, found), "completed_at": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()})
    pol.analysis = {**(pol.analysis or {}), "ai_note": ai_note, "timing_s": tm, "progress": final}  # final summary kept (UI: "Completed in X s")
    from app.services import audit
    audit.record(db, action="policy.analyzed", actor_email="worker", entity_type="policy", entity_id=str(pol.id),
                 details={"proposed_findings": len(found), "ai": ai_note})
    return {"proposed_findings": len(found), "ai": ai_note}


def _audit_note(pol, ai_out, found) -> str | None:
    """Why the stored audit findings differ from the AI's suggestions (findings are stored per linked system)."""
    n, stored = len((ai_out or {}).get("findings") or []), len({(f.control_id, f.description) for f in found if f.origin == "ai"})
    if not n or stored >= n:
        return None
    if not pol.system_ids:
        return f"{n} policy-audit suggestion(s) were not stored as findings: the policy is not linked to a system. Link a system and re-run the analysis."
    return (f"{n} policy-audit suggestion(s), {stored} stored as findings; {n - stored} dropped (control outside this policy's families, "
            "stated as not selected, or not in the catalog).")


HANDLERS: dict[str, Callable[[Session, dict], dict]] = {
    JOB_CONTENT_LOAD: handle_content_load,
    "ingest.process": handle_ingest,
    "evidence.verify_integrity": handle_integrity,
    "evidence.evaluate_freshness": handle_freshness,
    "policy.analyze": handle_policy_analyze,
    "tr.detect": handle_tr_detect,
    "tr.generate": handle_tr_generate,
    "tr.analyze": handle_tr_analyze,
    "inventory.import": handle_inventory_import,
    "inventory.check": handle_inventory_check,
    "inventory.ai": handle_inventory_ai,
    "attestations.evaluate": handle_attestations,
    "notifications.deadlines": handle_notifications,
    "risk.snapshot": handle_risk_snapshot,
    "connectors.collect": handle_connectors,
    "kev.reevaluate": handle_kev,
    "emass.retry": handle_emass_retry,
    "review.bulk": lambda db, payload: __import__("app.services.review_bulk", fromlist=["run"]).run(db, payload),
    "conmon.slcm_due": lambda db, payload: __import__("app.services.iscm", fromlist=["run_due_job"]).run_due_job(db),
    "sandbox.provision": lambda db, payload: __import__("app.services.sandbox", fromlist=["provision"]).provision(db, __import__("uuid").UUID(payload["org_id"])),
    "autosave.close_idle": lambda db, payload: __import__("app.services.autosave", fromlist=["close_idle"]).close_idle(db),
    "sandbox.expiry": lambda db, payload: __import__("app.services.sandbox", fromlist=["run_expiry"]).run_expiry(db),
    "sandbox.demo_reset": lambda db, payload: __import__("app.services.sandbox", fromlist=["reset_demo_account"]).reset_demo_account(db),
    "retention.purge": lambda db, payload: __import__("app.services.retention", fromlist=["purge"]).purge(db),
}
