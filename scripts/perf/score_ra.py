#!/usr/bin/env python3
"""Score a policy_bench run of the RA UAT fixture against docs/perf/corpus/ra_raven.gold.json (requirement-level labels RA-1..RA-10,
not-selected, withdrawn and a negative control set). Usage: python scripts/perf/score_ra.py <run-label> [...]"""
import json
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, "/app/backend")
GOLD = json.loads(Path(__import__("os").environ.get("GOLD") or "/app/docs/perf/corpus/ra_raven.gold.json").read_text())
RUNS = Path("/app/docs/perf/runs")


def score(label: str) -> dict:
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Policy, PolicyControlMap, PolicyFinding
    run = json.loads((RUNS / f"{label}.json").read_text())
    pid = uuid.UUID(run["policy_id"])
    with SessionLocal() as db:
        pol = db.get(Policy, pid)
        text, analysis = pol.text_content, pol.analysis or {}
        maps = {m.control_id: m.status for m in db.scalars(select(PolicyControlMap).where(PolicyControlMap.policy_id == pid, PolicyControlMap.valid_to.is_(None)))}
        finds = [(f.control_id, f.description) for f in db.scalars(select(PolicyFinding).where(PolicyFinding.policy_id == pid))]
    rows = {(r["control_id"], r["requirement_id"]): r for r in run["rows"]}
    from app.models import Control, PolicyRequirementCoverage
    from app.services.policy_coverage import relevant
    with SessionLocal() as db:
        req_text = {(c.control_id, c.requirement_id): c.text for c in db.scalars(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id == pid))}
        titles = dict(db.execute(select(Control.control_id, Control.title).where(Control.control_id.in_({c for c, _ in req_text}))).all())
    tp = fp = fn = exact = false_gap = true_gap = n = cited = valid = off = 0
    for g in GOLD["requirements"]:
        r = rows.get((g["control_id"], g["requirement_id"]))
        n += 1
        if r is None:
            fn += g["label"] != "not_addressed"
            continue
        pred_pos, gold_pos = r["status"] in ("met", "partial"), g["label"] in ("met", "partial")
        tp += pred_pos and gold_pos
        fp += pred_pos and not gold_pos
        fn += gold_pos and not pred_pos
        exact += {"met": "met", "partial": "partial", "missing": "not_addressed"}.get(r["status"]) == g["label"]
        false_gap += r["status"] == "missing" and g["label"] == "met"
        true_gap += r["status"] in ("missing", "partial") and g["label"] != "met"
        if r.get("quote") and pred_pos:
            cited += 1
            valid += r["quote"] in text
        if r["status"] == "met" and r.get("quote") and not re.fullmatch(r"[a-z]{2}-1", g["control_id"]) and not relevant(r["quote"], req_text.get((g["control_id"], g["requirement_id"]), ""), titles.get(g["control_id"], "")):
            off += 1
    neg = set(GOLD["negative_controls"])
    rowctl = {c for c, _ in rows}
    violations = {
        "negative_maps": sorted(neg & {c for c, s in maps.items() if s == "proposed"}),
        "negative_rows": sorted(neg & rowctl),
        "negative_findings": sorted({c for c, _ in finds if c in neg}),
        "remote_access_mentions": sum(bool(re.search(r"remote access|\bac-17\b", (d or "") + " " + (r.get("reason") or ""), re.I))
                                      for d, r in [(d, {}) for _, d in finds] + [("", r) for r in run["rows"]]),
        "not_selected_gap_rows": sorted({c for c in GOLD["not_selected"] if c in rowctl}),
        "not_selected_missing_flag": sorted(set(GOLD["not_selected"]) - set(analysis.get("not_selected") or {})),
        "withdrawn_mapped": sorted(set(GOLD["withdrawn"]) & set(maps)),
    }
    gaps = sum(1 for g in GOLD["requirements"] if g["label"] != "met")
    return {"label": label, "analyzer": run["analyzer"], "wall_s": run["wall_s"], "requirements": n,
            "precision_addressed": round(tp / max(tp + fp, 1), 3), "recall_addressed": round(tp / max(tp + fn, 1), 3),
            "exact_label_agreement": round(exact / n, 3), "false_gaps_on_met": false_gap, "gold_gaps_flagged": f"{true_gap}/{gaps}",
            "citation_validity": round(valid / max(cited, 1), 3), "met_quotes_off_subject": off, "review_items": sum(1 for s in maps.values() if s == "proposed"),
            "possible_related_not_proposed": len(analysis.get("possible_related_controls") or []), "violations": violations,
            "violation_free": not any(v for v in violations.values())}


if __name__ == "__main__":
    print(json.dumps([score(x) for x in sys.argv[1:]], indent=1))
