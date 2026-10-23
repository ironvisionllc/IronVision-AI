"""Evidence analysis for one TR row. AI (if configured) only explains; it can never set Compliance Status, Tested By or Date Tested.
Every AI reference/quote is validated against the input bundle server-side; anything not exact is dropped and recorded."""
import asyncio
import json
import re
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Assessment, ControlAssignment, Evidence, Finding, Implementation, Poam, TrAnalysis, TrRow, TrWorkbook
from app.services.ai.service import get_ai_service
from app.services.tr.service import RESULT_MAP

PROMPT, VERSION = "tr.evidence_analysis", "1.1.0"
DET_VERSION = "deterministic@1.0.0"
DET_LABEL = "Deterministic analysis (no AI)"
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
OK_STATES = ("pass", "not_applicable", "closed", "fixed", "not_a_finding")


def _uid(v):
    return uuid.UUID(str(v))


def bundle(db: Session, wb: TrWorkbook, row: TrRow) -> list[dict]:
    recs = []
    for s in row.sources or []:
        t, rid, text, extra = s["type"], s["id"], s["label"], {}
        if t == "assessment" and (a := db.get(Assessment, _uid(rid))):
            text += f". Result: {a.result}." + (f" Assessor notes: {a.findings_text.strip()}" if a.findings_text else "")
            extra = {"result": a.result, "determination": RESULT_MAP.get(a.result)}
        elif t == "finding" and (f := db.get(Finding, _uid(rid))):
            text += f". {f.title}"
            extra = {"state": f.current_state, "source": f.source_type}
        elif t == "evidence" and (e := db.get(Evidence, _uid(rid))):
            extra = {"freshness": e.state}
        elif t == "poam" and (p := db.get(Poam, _uid(rid))):
            extra = {"status": p.status}
        elif t == "policy":
            extra = {"coverage": text.rsplit("– ", 1)[-1].strip().lower()}
        recs.append({"id": rid, "type": t, "text": text[:1500], **extra})
    a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == wb.system_id, ControlAssignment.control_id == row.control_id))
    impl = a and db.scalar(select(Implementation).where(Implementation.assignment_id == a.id, Implementation.is_current.is_(True)))
    if impl and (impl.narrative or "").strip():
        recs.append({"id": str(impl.id), "type": "implementation", "text": impl.narrative.strip()[:2000], "status": impl.implementation_status})
    return recs


def _verdict(r: dict) -> tuple[str, str]:
    t = r["type"]
    if t == "finding":
        if r.get("state") == "open":
            return "contradicts", f"{'STIG' if r.get('source') == 'stig_checklist' else 'ACAS'} finding is Open"
        if r.get("state") in OK_STATES:
            return "supports", "Scan/checklist result is Not a Finding / Not Applicable"
        return "does_not_establish", f"Finding state “{r.get('state')}” does not establish compliance"
    if t == "assessment":
        d = r.get("determination")
        if d == "Compliant":
            return "supports", "Recorded assessment determined the control satisfied"
        if d == "Non-Compliant":
            return "contradicts", "Recorded assessment determined the control not satisfied"
        return "does_not_establish", "Assessment has no usable determination"
    if t == "policy":
        if r.get("coverage") == "met":
            return "supports", "Policy states the requirement (policy text alone cannot prove technical implementation)"
        return "does_not_establish", f"Policy coverage is {r.get('coverage', 'not met')}"
    if t == "evidence":
        if r.get("freshness") not in ("current", "near_expiration"):
            return "does_not_establish", "Evidence is stale under the freshness policy"
        return "does_not_establish", "Evidence file is linked and current; its content is not assessed here"
    if t == "poam":
        return ("contradicts", "An open POA&M tracks a weakness for this control") if r.get("status") not in ("completed", "closed") else \
            ("does_not_establish", "POA&M is closed")
    return "does_not_establish", "An implementation statement is a claim, not test evidence"


def deterministic(recs: list[dict]) -> dict:
    sources = [{"id": r["id"], "verdict": v, "reason": why, "quote": ""} for r in recs for v, why in [_verdict(r)]]
    by = {s["id"]: s["verdict"] for s in sources}
    asm = [r for r in recs if r["type"] == "assessment"]
    opn = [r["id"] for r in recs if r["type"] == "finding" and r.get("state") == "open"]
    stale = [r["id"] for r in recs if r["type"] == "evidence" and r.get("freshness") not in ("current", "near_expiration")]
    conflicts = [{"ids": [a["id"], *opn], "reason": "Recorded assessment says Compliant but scan/checklist findings are Open"}
                 for a in asm if a.get("determination") == "Compliant" and opn]
    missing = []
    if not any(r["type"] in ("finding", "assessment", "evidence") for r in recs):
        missing.append("No technical test evidence (STIG, ACAS, assessment or evidence file) is linked to this CCI/control")
    if not asm:
        missing.append("No recorded assessor determination – the SCA must decide the Compliance Status")
    unsupported = []
    impl = next((r for r in recs if r["type"] == "implementation"), None)
    if impl and impl.get("status") in ("implemented", "inherited") and opn:
        unsupported.append("Implementation statement says implemented, but open findings exist")
    if any(a.get("determination") == "Compliant" for a in asm) and not any(by[r["id"]] == "supports" for r in recs if r["type"] in ("finding", "evidence")):
        unsupported.append("Compliant determination is not backed by a passing scan/checklist result")
    sup = [r for r in recs if by[r["id"]] == "supports" and r["type"] != "implementation"]
    con = [r for r in recs if by[r["id"]] == "contradicts"]
    parts = []
    if con:
        parts.append("Contradicting evidence: " + "; ".join(r["text"].split(". ")[0] for r in con[:6]))
    if sup:
        parts.append("Supporting evidence: " + "; ".join(r["text"].split(". ")[0] for r in sup[:6]))
    if stale:
        parts.append(f"{len(stale)} evidence file(s) are stale")
    expl = ". ".join(parts) + "." if parts else "No supporting or contradicting test evidence was found for this CCI."
    return {"sources": sources, "missing": missing, "stale": stale, "conflicts": conflicts, "unsupported": unsupported,
            "explanation": expl, "explanation_refs": [r["id"] for r in con[:6] + sup[:6]]}


def validate(out: dict, recs: list[dict]) -> tuple[dict, list[dict]]:
    """Keep only references that are exact bundle IDs and quotes that are exact substrings of that record; record every drop."""
    by = {r["id"]: r for r in recs}
    drops, sources = [], []
    for s in out.get("sources", []):
        if s["id"] not in by:
            drops.append({"field": "sources", "id": s["id"], "reason": "reference not in input bundle"})
            continue
        if s.get("quote") and s["quote"] not in by[s["id"]]["text"]:
            drops.append({"field": "sources.quote", "id": s["id"], "quote": s["quote"][:200], "reason": "quote is not an exact substring of the record"})
            s = {**s, "quote": ""}
        sources.append(s)

    def keep(field, ids):
        ok = [i for i in ids if i in by]
        drops.extend({"field": field, "id": i, "reason": "reference not in input bundle"} for i in ids if i not in by)
        return ok

    conflicts = [{**c, "ids": ids} for c in out.get("conflicts", []) if (ids := keep("conflicts", c["ids"]))]
    expl = out.get("explanation", "")
    for u in set(UUID_RE.findall(expl)):
        if u not in by:
            drops.append({"field": "explanation", "id": u, "reason": "record ID in text not in input bundle"})
            expl = expl.replace(u, "[removed reference]")
    return {"sources": sources, "missing": out.get("missing", []), "stale": keep("stale", out.get("stale", [])), "conflicts": conflicts,
            "unsupported": out.get("unsupported", []), "explanation": expl, "explanation_refs": keep("explanation_refs", out.get("explanation_refs", []))}, drops


def _merge(ai: dict, det: dict) -> dict:
    """Deterministic facts (conflicts, stale, missing) are never lost when the AI omits them."""
    have = {tuple(sorted(c["ids"])) for c in ai["conflicts"]}
    return {**ai, "stale": sorted(set(ai["stale"]) | set(det["stale"])),
            "conflicts": ai["conflicts"] + [c for c in det["conflicts"] if tuple(sorted(c["ids"])) not in have],
            "missing": ai["missing"] + [m for m in det["missing"] if m not in ai["missing"]]}


def analyze_row(db: Session, wb: TrWorkbook, row: TrRow, actor_id=None) -> TrAnalysis:
    recs = bundle(db, wb, row)
    det = deterministic(recs)
    out, drops, mode, provider, model, ver, err = det, [], "deterministic", None, None, DET_VERSION, None
    svc = get_ai_service()
    if svc.configured and recs:
        try:
            res = asyncio.run(svc.run(PROMPT, VERSION, {"control": (row.control_id or "").upper(), "cci": row.cci_id or "",
                                                        "records": json.dumps(recs, default=str)}, actor_user_id=actor_id))
            ai, drops = validate(res.output.model_dump(), recs)
            out, mode, provider, model, ver = _merge(ai, det), "ai", res.provider, res.model, f"{PROMPT}@{VERSION}"
        except Exception as exc:  # AI failed or output rejected by the schema → deterministic stands, reason stored
            err = f"AI output not used: {exc}"[:500]
    a = TrAnalysis(row_id=row.id, workbook_id=wb.id, mode=mode, provider=provider, model=model, prompt_version=ver,
                   input_ids=[r["id"] for r in recs], input_bundle=recs, output=out, dropped=drops, error=err, requested_by=actor_id)
    db.add(a)
    db.flush()
    return a


def out(a: TrAnalysis) -> dict:
    return {"id": str(a.id), "row_id": str(a.row_id), "mode": a.mode, "label": "AI suggestion" if a.mode == "ai" else DET_LABEL,
            "provider": a.provider, "model": a.model, "prompt_version": a.prompt_version, "input_ids": a.input_ids, "records": a.input_bundle,
            "output": a.output, "dropped": a.dropped or [], "error": a.error, "created_at": a.created_at.isoformat()}
