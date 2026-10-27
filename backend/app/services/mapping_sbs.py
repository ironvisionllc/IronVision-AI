"""Side-by-side policy→control mapping review: control requirement (left) vs exact, located policy excerpts (right), evidence-based
confidence explanation, coverage outcome, gap analysis and persisted reviewer decisions."""
import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Control, PolicyControlMap, PolicyRequirementCoverage
from app.services.content.loader import active_catalog_id

NO_TEXT = "No supporting text found – manual review required"
PREAMBLE = "Preamble / title"
LEGEND = {"High": "Explicit control ID together with requirement language (shall / must / required …) in the same passage – direct evidence.",
          "Medium": "Requirement language that matches the control's requirement, or an explicit ID without requirement language – direct but partial evidence.",
          "Low": "Inferred relevance only (e.g. the control's name appears) – no requirement language tied to the control.",
          "Requires manual review": NO_TEXT}
OUTCOME = {"met": "Fully Addressed", "partial": "Partially Addressed", "missing": "Not Addressed"}
REQ_WORDS = re.compile(r"\b(shall|must|will|required|requires|is responsible|are responsible|ensure[sd]?)\b", re.I)


def now():
    return datetime.now(timezone.utc)


def locate(text: str, snippet: str) -> dict:
    """Exact-substring check (server-side) plus page and section: page from form-feed page breaks, section from the same finder as coverage snippets."""
    from app.services.rmf import section_at

    i = text.find(snippet) if snippet else -1
    if i < 0:
        return {"exact": False}
    page = text.count("\f", 0, i) + 1 if "\f" in text else None
    sec = section_at(text, i, window=None) or PREAMBLE  # nothing before the first heading → title / preamble
    ctx_s, ctx_e = max(0, i - 160), min(len(text), i + len(snippet) + 160)
    return {"exact": True, "start": i, "end": i + len(snippet), "page": page, "section": sec,
            "context_before": text[ctx_s:i], "context_after": text[i + len(snippet):ctx_e]}


def explain(m: PolicyControlMap, text: str) -> dict:
    srcs = set((m.source or "").split("+"))
    ex = [{"text": s, **locate(text, s)} for s in (m.snippets or [])]
    exact = [e for e in ex if e["exact"]]
    req = any(REQ_WORDS.search(e["text"]) for e in exact)
    if not exact:
        conf, why, kind = "Requires manual review", NO_TEXT, "none"
    elif "explicit_id" in srcs and (req or "statement_language" in srcs):
        conf, why, kind = "High", "The passage quotes the control ID and states a requirement.", "direct"
    elif "explicit_id" in srcs or "statement_language" in srcs:
        conf, why, kind = "Medium", ("Explicit control ID without requirement language." if "explicit_id" in srcs else
                                     "Requirement language matches the control, but the control ID is not quoted."), "direct"
    else:
        conf, why, kind = "Low", "Only the control's name appears – relevance is inferred.", "inferred"
    dropped = [e["text"] for e in ex if not e["exact"]]
    return {"evidence_confidence": conf, "confidence_explanation": why, "evidence_kind": kind, "excerpts": exact,
            "unverified_excerpts": dropped, "no_supporting_text": not exact, "stored_confidence": m.confidence}


def outcome(m: PolicyControlMap, cov: list[PolicyRequirementCoverage], ev: dict) -> dict:
    if m.coverage_override:
        return {**m.coverage_override, "overridden": True}
    if ev["no_supporting_text"] or not cov:
        return {"outcome": "Requires Manual Review", "model_status": None, "overridden": False}
    st = {c.status for c in cov}
    model = "met" if st == {"met"} else "missing" if st == {"missing"} else "partial"
    return {"outcome": OUTCOME[model], "model_status": model.upper(), "overridden": False,
            "note": "Coverage is computed per requirement from the policy text – confidence never makes a mapping Fully Addressed."}


def gaps(db: Session, m: PolicyControlMap, cov: list[PolicyRequirementCoverage], ev: dict, ctrl: Control | None, policy) -> list[dict]:
    from app.services.policy_coverage import gap_name  # complete sentences, never cut (the UI clips at a word boundary for display)
    out = [{"type": "Missing requirement", "text": gap_name(c)} for c in cov if c.status == "missing"]
    out += [{"type": "Incomplete statement", "text": f"{c.label}: {' '.join((c.reason or '').split())}"} for c in cov if c.status == "partial"]
    out += [{"type": "Unsupported claim", "text": f"Excerpt not found verbatim in the stored policy text: “{t[:120]}”"} for t in ev["unverified_excerpts"]]
    vals = {v.get("parameter") for v in (policy.analysis or {}).get("values", []) if v.get("control_id") == m.control_id}
    for p in (ctrl.parameters or []) if ctrl else []:
        if p["id"] not in vals:
            out.append({"type": "Organizational decision required", "text": f"ODP {p['id']} ({p.get('label') or 'value'}) is not set in this policy."})
    if ev["no_supporting_text"]:
        out.append({"type": "Recommendation", "text": "Recommendation: add a statement that addresses this control (quote the control ID and use requirement language)."})
    elif any(g["type"] in ("Missing requirement", "Incomplete statement") for g in out):
        out.append({"type": "Recommendation", "text": "Recommendation: extend the policy to cover the missing / incomplete requirements listed above."})
    return out


def control_panel(db: Session, cid: str) -> dict:
    from app.services import policy_coverage as pc

    cat = active_catalog_id(db)
    c = db.scalar(select(Control).where(Control.catalog_version_id == cat, Control.control_id == cid))
    if c is None:
        return {"control_id": cid, "title": None}
    enh = [{"control_id": e.control_id, "title": e.title} for e in db.scalars(select(Control).where(Control.catalog_version_id == cat, Control.parent_control_id == cid,
                                                                                                    Control.is_withdrawn.is_(False)).order_by(Control.sort_id))]
    return {"control_id": cid, "label": c.label, "title": c.title, "statement": c.statement, "guidance": c.guidance, "enhancements": enh,
            "odps": [{"id": p["id"], "label": p.get("label")} for p in c.parameters or []], "family": c.family_title,
            "framework": "NIST SP 800-53 Rev. 5", "requirements": pc.requirements(db, cid)}


def review(db: Session, policy, m: PolicyControlMap) -> dict:
    text = policy.text_content or ""
    ev = explain(m, text)
    cov = list(db.scalars(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id == policy.id, PolicyRequirementCoverage.control_id == m.control_id)))
    left = control_panel(db, m.control_id)
    ctrl = db.scalar(select(Control).where(Control.catalog_version_id == active_catalog_id(db), Control.control_id == m.control_id))
    return {"control": left, "policy": {"id": str(policy.id), "title": policy.title, "version": policy.version},
            "mapping": {"id": str(m.id), "status": m.status, "source": m.source, "rationale": m.basis, "justification": m.justification,
                        "review_flag": m.review_flag, "comments": m.comments or [], "reanalysis": m.reanalysis, **ev},
            "coverage": outcome(m, cov, ev), "requirements": [{"label": c.label, "status": c.status, "reason": c.reason} for c in cov],
            "gaps": gaps(db, m, cov, ev, ctrl, policy), "legend": LEGEND}


def comment(m: PolicyControlMap, actor_email: str, action: str, text: str) -> None:
    m.comments = (m.comments or []) + [{"by": actor_email, "at": now().isoformat(), "action": action, "comment": text}]
