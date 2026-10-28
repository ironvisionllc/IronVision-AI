"""Score stored Policy Auditor results against a gold set (docs/perf/corpus/*.gold.json).
recall    = gold "language present" (met|partial) requirements the auditor did NOT call missing  (missed language = silent miss)
precision = auditor met|partial requirements whose gold label is met|partial
exact     = identical label (met / partial / missing)
Usage: python3 scripts/score_policy_gold.py <gold.json> <policy-id> [...]   (exit 1 if recall < --min-recall, default 1.0 for paragraph language)"""
import json
import os
import sys
from collections import defaultdict

sys.path.insert(0, "/app/backend")
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/app/backend/.env")
from sqlalchemy import create_engine, text  # noqa: E402

PRESENT = {"met", "partial"}


def score(gold: dict, rows: dict) -> dict:
    fam = defaultdict(lambda: {"gold_present": 0, "found": 0, "pred_present": 0, "pred_correct": 0, "exact": 0, "n": 0, "missed": []})
    for g in gold["requirements"]:
        key = (g["control_id"], g["requirement_id"])
        if key not in rows:
            continue
        p, f = rows[key], fam[g["control_id"].split("-")[0]]
        f["n"] += 1
        f["exact"] += p == {"not_addressed": "missing"}.get(g["label"], g["label"])
        if g["label"] in PRESENT:
            f["gold_present"] += 1
            if p in PRESENT:
                f["found"] += 1
            else:
                f["missed"].append(f"{g['control_id']} {g['requirement_id']}")
        if p in PRESENT:
            f["pred_present"] += 1
            f["pred_correct"] += g["label"] in PRESENT
    return {k: {"recall": round(v["found"] / v["gold_present"], 3) if v["gold_present"] else None,
                "precision": round(v["pred_correct"] / v["pred_present"], 3) if v["pred_present"] else None,
                "exact": round(v["exact"] / v["n"], 3) if v["n"] else None, "scored": v["n"], "missed": v["missed"]} for k, v in fam.items()}


def rows_for(policy_id: str, history: bool = False) -> dict:
    """Current coverage rows, or (history=True) the snapshot kept before the last re-analysis."""
    e = create_engine(os.environ.get("DATABASE_URL") or os.environ["POSTGRES_URL"])
    with e.connect() as c:
        if history:
            h = (c.execute(text("select analysis->'history' from policies where id=:p"), {"p": policy_id}).scalar() or [])
            return {(r["control_id"], r["requirement_id"]): r["status"] for r in (h[-1]["rows"] if h else [])}
        return {(r[0], r[1]): r[2] for r in c.execute(text("select control_id, requirement_id, status from policy_requirement_coverage where policy_id=:p"), {"p": policy_id})}


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    min_recall = float(next((a.split("=")[1] for a in sys.argv if a.startswith("--min-recall=")), "1.0"))
    gold = json.load(open(args[0]))
    worst = 1.0
    for pid in args[1:]:
        res = score(gold, rows_for(pid, "--before" in sys.argv))
        print(pid[:8], json.dumps(res))
        worst = min([worst] + [v["recall"] for v in res.values() if v["recall"] is not None])
    sys.exit(0 if worst >= min_recall else 1)
