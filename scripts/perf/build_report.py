#!/usr/bin/env python3
"""Builds docs/perf/policy_auditor_baseline.json, policy_auditor_benchmarks.json and the tables in policy_auditor_results.md
from docs/perf/runs/*.json + scripts/perf/score.py. Cost uses OpenRouter list price for anthropic/claude-sonnet-5.5
($2.00 / M input, $10.00 / M output – https://openrouter.ai/anthropic/claude-sonnet-5.5, checked 2026-10-27)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from score import score  # noqa: E402

RUNS, OUT = Path("/app/docs/perf/runs"), Path("/app/docs/perf")
PIN, POUT = 2.00, 10.00


def summ(label: str) -> dict | None:
    f = RUNS / f"{label}.json"
    if not f.exists():
        return None
    r = json.loads(f.read_text())
    calls = r["ai_calls"]
    tin = sum(v["input_tokens"] for v in calls.values())
    tout = sum(v["output_tokens"] for v in calls.values())
    cov = calls.get("policy.coverage_refine", {})
    s = score(label)
    v2 = r.get("v2") or {}
    return {"label": label, "corpus": r["corpus"], "analyzer": r["analyzer"], "workers": r.get("workers") or (r.get("timing_s") or {}).get("ai_workers"),
            "wall_s": r["wall_s"], "ai_calls": sum(v["n"] for v in calls.values()), "coverage_calls": cov.get("n", 0),
            "p50_ms": cov.get("p50_ms"), "p95_ms": cov.get("p95_ms"), "input_tokens": tin, "output_tokens": tout,
            "cost_usd": round(tin / 1e6 * PIN + tout / 1e6 * POUT, 3), "retries": v2.get("retries"), "cache_hits": v2.get("cache_hits"),
            "batches": v2.get("batches"), "rate_limit_wait_s": v2.get("rate_limit_wait_s"), "failed_batches": v2.get("failed_batches"),
            "not_examined": v2.get("not_examined"), "verification_sample": v2.get("verification_sample"), "verification_found": v2.get("verification_found"),
            "timing_s": r.get("timing_s"), "db": r["db"], "idle_in_txn_before_after": r["idle_in_transaction_before_after"],
            "precision": s["precision"], "recall": s["recall"], "fp": s["false_positives"], "fn": s["false_negatives"],
            "control_coverage": s["control_coverage"], "requirement_coverage": s["requirement_coverage"], "citation_validity": s["citation_validity"],
            "gap_guidance_readable": s["gap_guidance_readable"], "structured_complete": s["structured_complete"], "ac17_rows": s["ac17_rows"],
            "samples": s["samples"]}


def table(rows: list[dict]) -> str:
    cols = ["label", "analyzer", "workers", "wall_s", "ai_calls", "p50_ms", "p95_ms", "input_tokens", "output_tokens", "cost_usd", "cache_hits",
            "retries", "precision", "recall", "fp", "fn", "citation_validity", "gap_guidance_readable"]
    out = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for r in rows:
        out.append("| " + " | ".join(str(r.get(c, "")) for c in cols) + " |")
    return "\n".join(out)


if __name__ == "__main__":
    base = [x for x in (summ(f"base_{n}") for n in ("p20", "p100", "p284", "neg_ra", "neg_unrel")) if x]
    v2 = [x for x in (summ(f.stem) for f in sorted(RUNS.glob("v2_*.json"))) if x]
    (OUT / "policy_auditor_baseline.json").write_text(json.dumps(base, indent=1))
    (OUT / "policy_auditor_benchmarks.json").write_text(json.dumps(v2, indent=1))
    print("## Baseline (analyzer v-current)\n\n" + table(base) + "\n\n## Analyzer v2\n\n" + table(v2))
