#!/usr/bin/env python3
"""Policy Auditor benchmark: runs the REAL analysis (same handler the worker runs, real OpenRouter calls) in-process on a corpus policy
inside a SYNTHETIC bench org and records wall-clock, per-stage timing, AI calls (p50/p95 latency, tokens), retries, DB query count/time,
pool checkouts and idle-in-transaction sessions, plus the resulting coverage rows for accuracy scoring.
Usage: python scripts/perf/policy_bench.py <corpus-name> <label> [--analyzer v-current|v2] [--workers N] [--reuse-policy]"""
import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/app/backend")
from sqlalchemy import event, select, text  # noqa: E402

from app.db import SessionLocal, get_engine  # noqa: E402
from app.models import AIInteraction, Organization, Policy, PolicyRequirementCoverage  # noqa: E402

CORPUS, RUNS = Path("/app/docs/perf/corpus"), Path("/app/docs/perf/runs")
STATS = {"queries": 0, "query_s": 0.0, "checkouts": 0}


def _instrument():
    eng = get_engine()

    @event.listens_for(eng, "before_cursor_execute")
    def _b(conn, cur, stmt, params, ctx, many):
        conn.info["t0"] = time.perf_counter()

    @event.listens_for(eng, "after_cursor_execute")
    def _a(conn, cur, stmt, params, ctx, many):
        STATS["queries"] += 1
        STATS["query_s"] += time.perf_counter() - conn.info.get("t0", time.perf_counter())

    @event.listens_for(eng.pool, "checkout")
    def _c(*a):
        STATS["checkouts"] += 1


def _bench_org(db, fresh: bool = False) -> uuid.UUID:
    org = None if fresh else db.scalar(select(Organization).where(Organization.name == "PERF BENCH – SYNTHETIC"))
    if org is None:
        org = Organization(name="PERF BENCH – SYNTHETIC" + (f" {uuid.uuid4().hex[:6]}" if fresh else ""), slug=f"perf-bench-{uuid.uuid4().hex[:6]}", is_synthetic=True, is_sandbox=True)
        db.add(org)
        db.commit()
    return org.id


def _idle_in_txn() -> int:
    with get_engine().connect() as c:
        return c.execute(text("select count(*) from pg_stat_activity where datname=current_database() and state like 'idle in transaction%' "
                              "and pid<>pg_backend_pid() and application_name='ironvision-app'")).scalar()


def _pct(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, int(len(v) * p))] if v else None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus")
    ap.add_argument("label")
    ap.add_argument("--analyzer", default=os.environ.get("POLICY_ANALYZER", "v-current"))
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--policy-id", default=None, help="re-run an existing bench policy (cache / incremental runs)")
    ap.add_argument("--fresh-org", action="store_true", help="new SYNTHETIC org → guaranteed cold tenant cache")
    ap.add_argument("--docx", default=None, help="use the text extracted from this DOCX/PDF (same extractor as upload) instead of a corpus .txt")
    ap.add_argument("--with-system", action="store_true", help="attach a SYNTHETIC system so policy-audit findings are stored (as in UAT)")
    ap.add_argument("--edit-section", default=None, help="append a sentence to this heading before re-running (incremental)")
    a = ap.parse_args()
    os.environ["POLICY_ANALYZER"] = a.analyzer
    if a.workers:
        os.environ["POLICY_AI_WORKERS"] = str(a.workers)
    from worker.handlers import handle_policy_analyze
    _instrument()
    if a.docx:
        from app.services.rmf import extract_text
        body = extract_text(a.docx, Path(a.docx).read_bytes())
    else:
        body = None if a.policy_id else (CORPUS / f"{a.corpus}.txt").read_text()
    with SessionLocal() as db:
        org = _bench_org(db, a.fresh_org)
        if a.policy_id:
            pol = db.get(Policy, uuid.UUID(a.policy_id))
            if a.edit_section:
                t = pol.text_content
                i = t.index(a.edit_section) + len(a.edit_section)
                pol.text_content = t[:i] + "\nThe organization reviews this section after every significant change." + t[i:]
                pol.version += 1
        else:
            sids = None
            if a.with_system:
                from app.models import System
                sysm = System(id=uuid.uuid4(), org_id=org, name=f"SYNTHETIC bench system {a.corpus}")
                db.add(sysm)
                db.flush()
                sids = [str(sysm.id)]
            pol = Policy(org_id=org, policy_key=f"BENCH-{a.corpus}-{uuid.uuid4().hex[:4]}", title=f"SYNTHETIC bench {a.corpus}", version=1,
                         status="current", text_content=body, analysis_status="queued", system_ids=sids)
            db.add(pol)
        db.commit()
        pid = pol.id
    idle0 = _idle_in_txn()
    t0w = datetime.now(timezone.utc)
    t0 = time.perf_counter()
    with SessionLocal() as db:
        res = handle_policy_analyze(db, {"policy_id": str(pid)})
        db.commit()
    wall = time.perf_counter() - t0
    t1w = datetime.now(timezone.utc)
    with SessionLocal() as db:
        pol = db.get(Policy, pid)
        ai = db.execute(select(AIInteraction.prompt_id, AIInteraction.latency_ms, AIInteraction.input_tokens, AIInteraction.output_tokens,
                               AIInteraction.status, AIInteraction.model)
                        .where(AIInteraction.created_at >= t0w, AIInteraction.created_at <= t1w)).all()
        cov = db.scalars(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id == pid)).all()
        rows = [{"control_id": c.control_id, "requirement_id": c.requirement_id, "status": c.status, "source": c.source, "confidence": c.confidence,
                 "quote": (c.snippets or [{}])[0].get("text") if c.snippets else None, "location": (c.snippets or [{}])[0].get("location") if c.snippets else None,
                 "reason": c.reason, "needs": c.needs} for c in cov]
        analysis = pol.analysis or {}
    by: dict = {}
    for r in ai:
        by.setdefault(r.prompt_id, []).append(r)
    calls = {k: {"n": len(v), "p50_ms": _pct([x.latency_ms or 0 for x in v], .5), "p95_ms": _pct([x.latency_ms or 0 for x in v], .95),
                 "input_tokens": sum(x.input_tokens or 0 for x in v), "output_tokens": sum(x.output_tokens or 0 for x in v),
                 "status": {s: sum(1 for x in v if x.status == s) for s in {x.status for x in v}}, "model": v[0].model} for k, v in by.items()}
    out = {"label": a.label, "corpus": a.corpus, "analyzer": a.analyzer, "workers": a.workers, "policy_id": str(pid), "started": t0w.isoformat(),
           "wall_s": round(wall, 1), "result": res, "timing_s": analysis.get("timing_s"), "v2": analysis.get("v2"), "ai_calls": calls,
           "db": {"queries": STATS["queries"], "query_s": round(STATS["query_s"], 2), "pool_checkouts": STATS["checkouts"]},
           "idle_in_transaction_before_after": [idle0, _idle_in_txn()], "coverage_rows": len(rows),
           "status_counts": {s: sum(1 for r in rows if r["status"] == s) for s in {r["status"] for r in rows}}}
    RUNS.mkdir(parents=True, exist_ok=True)
    (RUNS / f"{a.label}.json").write_text(json.dumps({**out, "rows": rows}, indent=0, default=str))
    print(json.dumps(out, default=str))


if __name__ == "__main__":
    main()
