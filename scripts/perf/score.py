#!/usr/bin/env python3
"""Score a policy_bench run against builder-authored gold labels (NOT SME reviewed).
Usage: python scripts/perf/score.py <run-label> [...]  → prints JSON metrics per run"""
import json
import re
import sys
from pathlib import Path

RUNS, CORPUS = Path("/app/docs/perf/runs"), Path("/app/docs/perf/corpus")
SALAD = re.compile(r"(?:\b\w+\b,\s*){4,}")


def readable(s: str) -> bool:
    s = (s or "").strip()
    return len(s.split()) >= 6 and not SALAD.search(s) and bool(re.search(r"\b(is|are|does|do|states?|requires?|must|shall|missing|not|no|has|have)\b", s, re.I))


def score(label: str) -> dict:
    run = json.loads((RUNS / f"{label}.json").read_text())
    gold = json.loads((CORPUS / f"{run['corpus']}.gold.json").read_text())
    text = (CORPUS / f"{run['corpus']}.txt").read_text()
    g = gold["requirements"]
    rows = {f"{r['control_id']}|{r['requirement_id']}": r for r in run["rows"]}
    gold_ctl = set(gold["controls"])
    got_ctl = {r["control_id"] for r in run["rows"]}
    tp = fp = fn = tn = 0
    cit_ok = cit_n = exact = 0
    for k, lab in g.items():
        r = rows.get(k)
        pos = lab["label"] in ("addressed", "partial")
        pred = bool(r) and r["status"] in ("met", "partial")
        tp += pos and pred
        fp += (not pos) and pred
        fn += pos and not pred
        tn += (not pos) and not pred
        if r:
            exact += {"addressed": "met", "partial": "partial", "not_addressed": "missing"}[lab["label"]] == r["status"]
        if pred and r.get("quote"):
            cit_n += 1
            q = r["quote"].strip()[:120]
            pos = text.find(q)
            span = lab.get("span") or [0, len(text)]
            cit_ok += pos >= 0 and span[0] <= pos < span[1]  # verbatim AND inside the gold section (correct section/page)
    spurious = [r for k, r in rows.items() if k not in g and r["status"] in ("met", "partial")]
    gaps = [r for r in run["rows"] if r["status"] in ("missing", "partial")]
    guid = [r.get("reason") or "" for r in gaps]
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    return {"label": label, "corpus": run["corpus"], "analyzer": run["analyzer"], "wall_s": run["wall_s"],
            "gold_requirements": len(g), "rows": len(rows), "control_coverage": f"{len(got_ctl & gold_ctl)}/{len(gold_ctl)}",
            "requirement_coverage": f"{sum(1 for k in g if k in rows)}/{len(g)}",
            "precision": round(prec, 3) if prec is not None else None, "recall": round(rec, 3) if rec is not None else None,
            "false_positives": fp, "false_negatives": fn, "exact_label_agreement": round(exact / max(1, sum(1 for k in g if k in rows)), 3),
            "citation_validity": round(cit_ok / cit_n, 3) if cit_n else None, "citations_checked": cit_n,
            "spurious_positive_rows_outside_gold": len(spurious), "gap_guidance_readable": round(sum(map(readable, guid)) / len(guid), 3) if guid else None,
            "structured_complete": round(sum(1 for r in run["rows"] if r["status"] and r["requirement_id"] and (r["status"] == "missing" or r.get("quote")))
                                         / max(1, len(run["rows"])), 3),
            "ac17_rows": sum(1 for r in run["rows"] if r["control_id"].startswith("ac-17")),
            "samples": [{"req": f"{r['control_id']} {r['requirement_id']}", "status": r["status"], "guidance": (r.get("reason") or "")[:240]} for r in gaps[:10]]}


if __name__ == "__main__":
    print(json.dumps([score(x) for x in sys.argv[1:]], indent=1))
