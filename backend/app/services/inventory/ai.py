"""AI only explains/ranks ambiguous inventory items. Every reference is validated against the input; nothing is linked, created or changed."""
import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import AssetCorrelation, InventoryDiscrepancy
from app.services.ai.service import get_ai_service

P_CORR, P_DISC = ("inventory.correlation_rank", "1.0.0"), ("inventory.discrepancy_explain", "1.0.0")
DET_LABEL = "Deterministic analysis (no AI)"
STRONG = {"mac", "serial", "fqdn", "hostname"}


def _ts():
    return datetime.now(timezone.utc).isoformat()


def det_rank(cands: list[dict]) -> list[dict]:
    out = []
    for c in cands:
        s = len(set(c["matched"]) & STRONG)
        conf = max(0.05, min(0.9, 0.35 * s + (0.1 if "ip" in c["matched"] else 0) - 0.3 * len(c["conflicts"])))
        out.append({"asset_id": c["asset_id"], "confidence": round(conf, 2), "identifiers": c["matched"],
                    "explanation": f"Matches {', '.join(c['matched'])}" + (f"; conflicts on {', '.join(c['conflicts'])}" if c["conflicts"] else "")})
    return sorted(out, key=lambda x: -x["confidence"])


def rank_correlation(c: AssetCorrelation, actor_id=None) -> dict:
    cands = {x["asset_id"]: x for x in c.candidates}
    out = {"mode": "deterministic", "label": DET_LABEL, "prompt_version": "deterministic@1.0.0", "ranking": det_rank(c.candidates), "summary": c.reason, "dropped": []}
    svc = get_ai_service()
    if svc.configured and cands:
        try:
            res = asyncio.run(svc.run(*P_CORR, {"observed": json.dumps(c.facts, default=str), "candidates": json.dumps(c.candidates, default=str)}, actor_user_id=actor_id))
            ranking, drops = [], []
            for r in res.output.ranking:
                if r.asset_id not in cands:
                    drops.append({"field": "ranking", "id": r.asset_id, "reason": "candidate not in input"})
                    continue
                ok = set(cands[r.asset_id]["matched"]) | set(cands[r.asset_id]["conflicts"])
                bad = [i for i in r.identifiers if i not in ok]
                drops += [{"field": "identifiers", "id": r.asset_id, "value": i, "reason": "identifier not present in the data for this candidate"} for i in bad]
                ranking.append({"asset_id": r.asset_id, "confidence": round(max(0.0, min(1.0, r.confidence)), 2), "explanation": r.explanation,
                                "identifiers": [i for i in r.identifiers if i in ok]})
            out = {"mode": "ai", "label": "AI suggestion", "provider": res.provider, "model": res.model, "prompt_version": "@".join(P_CORR),
                   "ranking": ranking, "summary": res.output.summary, "dropped": drops}
        except Exception as exc:  # deterministic stands
            out["error"] = f"AI output not used: {exc}"[:400]
    return {**out, "input_ids": sorted(cands), "created_at": _ts()}


def explain_discrepancy(d: InventoryDiscrepancy, actor_id=None) -> dict:
    ids = {r["id"] for r in d.records}
    out = {"mode": "deterministic", "label": DET_LABEL, "prompt_version": "deterministic@1.0.0", "explanation": f"{d.title}. {d.recommendation or ''}".strip(),
           "ranking": [], "refs": sorted(ids), "dropped": []}
    svc = get_ai_service()
    if svc.configured:
        try:
            res = asyncio.run(svc.run(*P_DISC, {"title": d.title, "recommendation": d.recommendation or "", "records": json.dumps(d.records, default=str)},
                                      actor_user_id=actor_id))
            o = res.output
            drops = [{"field": "ranking", "id": r.record_id, "reason": "record not in input"} for r in o.ranking if r.record_id not in ids]
            drops += [{"field": "refs", "id": i, "reason": "record not in input"} for i in o.refs if i not in ids]
            out = {"mode": "ai", "label": "AI suggestion", "provider": res.provider, "model": res.model, "prompt_version": "@".join(P_DISC),
                   "explanation": o.explanation, "ranking": [{"record_id": r.record_id, "score": round(max(0.0, min(1.0, r.score)), 2), "reason": r.reason}
                                                            for r in o.ranking if r.record_id in ids],
                   "refs": [i for i in o.refs if i in ids], "dropped": drops}
        except Exception as exc:
            out["error"] = f"AI output not used: {exc}"[:400]
    return {**out, "input_ids": sorted(ids), "created_at": _ts()}


def run(db: Session, kind: str, oid, actor_id=None) -> dict:
    if kind == "correlation":
        c = db.get(AssetCorrelation, oid)
        c.ai = rank_correlation(c, actor_id)
        return {"mode": c.ai["mode"]}
    d = db.get(InventoryDiscrepancy, oid)
    d.ai = explain_discrepancy(d, actor_id)
    return {"mode": d.ai["mode"]}
