"""Policy Auditor requirement coverage. For every control a policy maps to, list its requirements (DISA CCIs + SP 800-53A
assessment objectives) and decide MET / PARTIAL / MISSING from the policy text with deterministic keyword/section heuristics.
Each result keeps the matched snippet(s) with page/section, a confidence, the reason, any organization-defined value found
(e.g. review frequency) and – when not met – what text would satisfy it. Nothing here changes a control status."""
import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Cci, CciControlMap, Control, ControlAssignment, ControlObjective, Policy, PolicyControlMap, PolicyRequirementCoverage, System
from app.services import policy_profile as pp
from app.services.rmf import locate

ANALYZER_VERSION = "coverage-4"

ELEMENTS = [("purpose", r"\bpurpose\b"), ("scope", r"\bscope\b"), ("roles", r"\broles?\b"), ("responsibilities", r"\bresponsibilit"),
            ("management commitment", r"management commitment|commitment (?:of|from) (?:senior |executive )?(?:management|leadership)|leadership commitment"),
            ("coordination among organizational entities", r"\bcoordinat"), ("compliance", r"\bcomplian")]
FREQ = (r"\b(annually|yearly|every\s+(?:\d+|one|two|three|six|twelve)\s+(?:months?|years?)|at least (?:once )?(?:annually|every\s+\d+\s+(?:months?|years?)|once (?:a|per) year)"
        r"|quarterly|biennially|semi-?annually|monthly|once (?:a|per) year)\b")
EVENTS = (r"\b(?:following|after|upon|in response to|whenever|when)\b[^.]{0,160}?\b(incidents?|breach\w*|significant changes?|changes? (?:to|in) [a-z ]{3,40}|"
          r"(?:risk |security )?assessments?|audits?|findings?|new (?:laws?|regulations?|threats?)|reorgani[sz]ation|mission changes?)")
DISSEM = r"\b(disseminat\w*|distribut\w*|communicat\w*|published|made available|provided)\b"
RECIP = r"\b(?:to|among|with)\s+((?:all |the )?[A-Za-z][A-Za-z ,/&()-]{2,90}?)(?=[.;]|$| via | through | within | by | upon | at )"
ROLE = (r"\b(ISSM|CISO|CIO|ISSO|CPO|SAOP|Chief [A-Z][a-z]+(?: [A-Z][a-z]+){0,3}|Authorizing Official|Senior Agency Official[a-zA-Z ]*|Risk Executive"
        r"|Information System Security Manager|Information System Security Officer|Privacy Officer|Director of [A-Z][a-z]+(?: [A-Z][a-z]+)?)\b")
LABEL = {"develop": "policy developed and documented", "develop_elements": "policy addresses purpose, scope, roles, responsibilities, management commitment, coordination and compliance",
         "element": "policy addresses {elem}", "laws": "consistent with applicable laws, directives and standards", "disseminate": "{target} disseminated",
         "recipients": "personnel/roles the {target} is disseminated to", "official": "designated official", "frequency": "review frequency for the {target}",
         "events": "events that trigger review of the {target}", "generic": "requirement text"}


def now() -> datetime:
    return datetime.now(timezone.utc)


def _target(t: str) -> str:
    if "policy and procedures" in t or "policies and procedures" in t:
        return "policy and procedures"
    i, j = t.find("procedure"), t.find("policy")
    return "procedures" if i >= 0 and (j < 0 or i < j) else "policy"


def classify(text: str) -> tuple[str, str, str | None]:
    t = re.sub(r"\s+", " ", text.lower())
    tgt = _target(t)
    if "defines the personnel or roles" in t or ("disseminat" in t and "[assignment: personnel or roles]" in t and "defines" in t):
        return "recipients", tgt, None
    if "official" in t and ("designat" in t or "defines the official" in t or "[assignment: official]" in t):
        return "official", "policy and procedures", None
    if "frequency" in t:
        return "frequency", tgt, None
    if "events" in t and ("following" in t or "defines the events" in t):
        return "events", tgt, None
    if "disseminat" in t:
        return "disseminate", tgt, None
    if "consistent with applicable laws" in t:
        return "laws", "policy", None
    m = re.search(r"addresses ([^.;]+)", t)
    if m:
        elems = [e for e, _ in ELEMENTS if e.split()[0] in m.group(1)]
        if len(elems) == 1:
            return "element", "policy", elems[0]
        if elems:
            return "develop_elements", "policy", None
    if "develop" in t or "documented" in t:
        return "develop", tgt, None
    return "generic", tgt, None


def _sentences(text: str):
    return [(m.start(), m.end(), m.group().strip()) for m in re.finditer(r"[^.\n]+\.?", text) if len(m.group().strip()) > 3]


def _about(s: str, target: str) -> bool:
    s = s.lower()
    if target == "procedures":
        return "procedure" in s
    if target == "policy":
        return "policy" in s or "this document" in s
    return "policy" in s or "procedure" in s


def _snip(text: str, hits):
    return [{"text": s[:300], "location": locate(text, a)} for a, _, s in hits[:3]]


def evaluate(text: str, concept: str, target: str, elem: str | None, family: str, req_text: str) -> dict:
    sents, low = _sentences(text), text.lower()
    fam = family.lower()
    r = {"status": "missing", "confidence": "High", "snippets": [], "parameter": None, "value": None, "needs": None}

    def found(hits, reason, conf="High", value=None, param=None, status="met"):
        r.update(status=status, confidence=conf, snippets=_snip(text, hits), reason=reason, value=value, parameter=param)
        return r

    if concept == "element":
        rx = dict(ELEMENTS)[elem]
        hits = [h for h in sents if re.search(rx, h[2], re.I)]
        if hits:
            return found(hits, f"The policy addresses {elem}.")
        r.update(reason=f"No statement addressing {elem} was found.", needs=f"Add a section or sentence on {elem} for the {fam} policy.")
        return r
    if concept in ("develop_elements", "develop") and target != "procedures":
        have = [e for e, rx in ELEMENTS if re.search(rx, low)]
        miss = [e for e, _ in ELEMENTS if e not in have]
        hits = [h for h in sents if any(re.search(rx, h[2], re.I) for _, rx in ELEMENTS)]
        if concept == "develop":
            if len(have) >= 3:
                return found(hits, f"A documented {fam} policy with {len(have)} of 7 policy elements.")
            if have:
                return found(hits, f"Only {len(have)} of 7 policy elements found ({', '.join(have)}).", "Medium", status="partial")
        else:
            if not miss:
                return found(hits, "All 7 policy elements are addressed: " + ", ".join(have) + ".")
            if have:
                r.update(status="partial", confidence="Medium", snippets=_snip(text, hits), reason=f"{len(have)} of 7 elements found; missing: {', '.join(miss)}.",
                         needs=f"Add statements on: {', '.join(miss)}.")
                return r
        r.update(reason="The text does not read as a documented policy (no purpose/scope/roles statements).", needs=f"Document the {fam} policy with purpose, scope, roles and responsibilities.")
        return r
    if concept == "develop":
        hits = [h for h in sents if "procedure" in h[2].lower() and re.search(r"develop|document|establish|maintain|facilitat|implement|describ", h[2], re.I)]
        if hits:
            return found(hits, f"{fam.capitalize()} procedures are documented or referenced to facilitate implementation.")
        weak = [h for h in sents if "procedure" in h[2].lower()]
        if weak:
            return found(weak, "Procedures are mentioned but not described as developed/documented.", "Medium", status="partial")
        r.update(reason="No procedures are documented or referenced.", needs=f"State that {fam} procedures are developed, documented and facilitate implementation of the policy.")
        return r
    if concept == "laws":
        hits = [h for h in sents if re.search(r"\b(laws?|executive orders?|directives?|regulations?|standards|guidelines)\b", h[2], re.I)
                and re.search(r"complian|consistent|accordance|adhere|comply", h[2], re.I)]
        if hits:
            return found(hits, "The policy states consistency/compliance with applicable laws, directives or standards.")
        r.update(reason="No statement of consistency with applicable laws, executive orders, directives, regulations, policies, standards and guidelines.",
                 needs="Add: “This policy is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines.”")
        return r
    if concept in ("disseminate", "recipients"):
        hits = [h for h in sents if re.search(DISSEM, h[2], re.I) and _about(h[2], target)]
        rec = None
        for h in hits:
            m = re.search(DISSEM + r"[^.]*?" + RECIP, h[2], re.I)
            if m:
                rec = m.group(2).strip(" ,")
                break
        if hits and rec:
            return found(hits, f"The {target} is disseminated to {rec}.", value=rec[:255], param=f"dissemination recipients ({target})")
        if hits:
            r.update(status="partial", confidence="Medium", snippets=_snip(text, hits), reason=f"Dissemination of the {target} is mentioned but the personnel or roles are not named.",
                     needs=f"Name who receives the {target}, e.g. “The {fam} {target} is disseminated to all system owners, ISSOs and the ISSM.”")
            return r
        r.update(reason=f"No statement that the {target} is disseminated.", needs=f"Add: “The {fam} {target} is disseminated to <personnel or roles>.”")
        return r
    if concept == "official":
        hits = [h for h in sents if re.search(r"\bofficial\b|designat|appoint", h[2], re.I) and re.search(r"manag|develop|disseminat|responsib|review|maintain", h[2], re.I)]
        named = [(h, re.search(ROLE, h[2])) for h in hits]
        named = [(h, m) for h, m in named if m]
        if named:
            return found([h for h, _ in named], f"{named[0][1].group(1)} is designated to manage the {fam} policy and procedures.", value=named[0][1].group(1),
                         param="designated official")
        if hits:
            r.update(status="partial", confidence="Medium", snippets=_snip(text, hits), reason="An official is referred to, but no specific official or role is named.",
                     needs=f"Name the official, e.g. “The ISSM is designated to manage the development, documentation and dissemination of the {fam} policy and procedures.”")
            return r
        r.update(reason="No designated official is named.", needs=f"Add: “The <official> is designated to manage the {fam} policy and procedures.”")
        return r
    if concept in ("frequency", "events"):
        rx = FREQ if concept == "frequency" else EVENTS
        rev = [h for h in sents if re.search(r"review|updat|revis", h[2], re.I)]
        mine = [h for h in rev if _about(h[2], target) and re.search(rx, h[2], re.I)]
        what = "review frequency" if concept == "frequency" else "review-triggering events"
        if mine:
            m = re.search(rx, mine[0][2], re.I)
            val = (m.group(1) if concept == "frequency" else m.group(0)).strip()
            return found(mine, f"The {target} states its {what}: “{val}”.", value=val[:255], param=f"{what} ({target})")
        other = [h for h in rev if re.search(rx, h[2], re.I)]
        if [h for h in rev if _about(h[2], target)]:
            r.update(status="partial", confidence="Medium", snippets=_snip(text, [h for h in rev if _about(h[2], target)]),
                     reason=f"The {target} is said to be reviewed, but no {what} is stated for it." + (" A value is stated for something else." if other else ""))
        else:
            r.update(reason=f"No {what} is stated for the {target}.")
        r["needs"] = (f"Add: “The {fam} {target} is reviewed and updated at least annually.”" if concept == "frequency"
                      else f"Add: “The {fam} {target} is reviewed and updated following significant changes, incidents or assessment findings.”")
        return r
    words = {w for w in re.findall(r"[a-z]{5,}", req_text.lower())} - {"organization", "defined", "assignment", "selection", "system", "policy", "controls"}
    best = max(sents, key=lambda h: len(words & set(re.findall(r"[a-z]{5,}", h[2].lower()))), default=None)
    score = len(words & set(re.findall(r"[a-z]{5,}", best[2].lower()))) / max(len(words), 1) if best else 0
    if best and score >= 0.5:
        return found([best], f"Similar wording found ({score:.0%} of the requirement's key words).", "Low", status="partial")
    r.update(confidence="Low", reason="No sentence with the requirement's key words was found.", needs="Add text that addresses this requirement directly.")
    return r


def requirements(db: Session, control_id: str) -> list[dict]:
    from app.services.content.loader import active_catalog_id

    out, seen = [], set()
    defs = {}
    for m in db.scalars(select(CciControlMap).where(CciControlMap.control_id == control_id, CciControlMap.version == "5").order_by(CciControlMap.cci_id)):
        if m.cci_id in seen:
            continue
        seen.add(m.cci_id)
        defs.setdefault(m.cci_id, db.scalar(select(Cci.definition).where(Cci.cci_id == m.cci_id).limit(1)))
        out.append({"type": "cci", "id": m.cci_id, "label": m.cci_id, "text": defs[m.cci_id] or "", "ref": m.reference_index})
    cu = db.scalar(select(Control.id).where(Control.control_id == control_id, Control.catalog_version_id == active_catalog_id(db)))
    for o in db.scalars(select(ControlObjective).where(ControlObjective.control_uuid == cu).order_by(ControlObjective.sort_order)):
        if (o.prose or "").strip():
            out.append({"type": "objective", "id": o.objective_id, "label": o.label or o.objective_id, "text": o.prose, "ref": o.label})
    return out


def is_xx1(control_id: str) -> bool:
    return bool(re.fullmatch(r"[a-z]{2}-1", control_id))


def evaluate_req(text: str, sents: list, control_id: str, req: dict, fam: str) -> tuple[str, dict]:
    if not is_xx1(control_id):
        r = pp.evaluate(text, sents, control_id, req["text"], lambda hits: _snip(text, hits))
        if r is not None:
            return f"profile-{r.pop('basis')}", r
    concept, target, elem = classify(req["text"])
    return concept, evaluate(text, concept, target, elem, fam, req["text"])


def analyze(db: Session, policy: Policy, use_ai: bool = False) -> list[PolicyRequirementCoverage]:
    """Recompute coverage for every current proposed/mapped control of this policy; covered-elsewhere overrides are kept."""
    maps = [m for m in db.scalars(select(PolicyControlMap).where(PolicyControlMap.policy_id == policy.id, PolicyControlMap.valid_to.is_(None)))
            if m.status == "mapped" or (m.status == "proposed" and m.confidence in ("High", "Medium"))]
    old = {(c.control_id, c.requirement_id): c for c in db.scalars(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id == policy.id))}
    for c in old.values():
        db.delete(c)
    db.flush()
    text = policy.text_content or ""
    sents = _sentences(text)
    out = []
    for m in maps:
        fam = db.scalar(select(Control.family_title).where(Control.control_id == m.control_id).limit(1)) or m.control_id.split("-")[0].upper()
        reqs = requirements(db, m.control_id)
        results = [evaluate_req(text, sents, m.control_id, req, fam) for req in reqs]
        if use_ai and not is_xx1(m.control_id):
            ai = ai_refine(text, m.control_id, reqs, results, policy.org_id)
            merged = [(c, pp.apply_ai(text, r, ai.get(req["id"]))) for req, (c, r) in zip(reqs, results)]
            results = [("profile-ai" if r.get("basis") == "ai" else c, r) for c, r in merged]
        for req, (concept, r) in zip(reqs, results):
            r.pop("basis", None)
            r.pop("ai_discarded", None)
            prev = old.get((m.control_id, req["id"]))
            row = PolicyRequirementCoverage(id=uuid.uuid4(), org_id=policy.org_id, policy_id=policy.id, policy_version=policy.version, control_id=m.control_id,
                                            requirement_type=req["type"], requirement_id=req["id"], label=req["label"], text=req["text"], concept=concept,
                                            status=r["status"], confidence=r["confidence"], reason=r["reason"], snippets=r["snippets"],
                                            parameter=r["parameter"], parameter_value=r["value"], needs=r["needs"] if r["status"] != "met" else None,
                                            source="ai" if concept == "profile-ai" else "deterministic", override=prev.override if prev else None,
                                            linked=prev.linked if prev else None)
            db.add(row)
            out.append(row)
    policy.analysis = {**(policy.analysis or {}), "coverage_version": ANALYZER_VERSION,
                       "values": _merge_values((policy.analysis or {}).get("values", []), out)}
    db.flush()
    return out


def _merge_values(values: list, rows: list) -> list:
    """Top-level policy values = analyzer values + every organization-defined value found at requirement level (A5)."""
    out = [v for v in values if v.get("source") != "coverage"]
    seen = {(v["control_id"], v["parameter"]) for v in out}
    for c in rows:
        if c.parameter_value and c.status == "met" and (c.control_id, c.parameter) not in seen:
            seen.add((c.control_id, c.parameter))
            out.append({"control_id": c.control_id, "parameter": c.parameter, "value": c.parameter_value, "requirement": c.requirement_id,
                        "quote": (c.snippets or [{}])[0].get("text"), "location": (c.snippets or [{}])[0].get("location"), "source": "coverage"})
    return out


def ensure_current(db: Session, policies) -> int:
    """Re-run coverage for policies analysed by an older analyzer (the worker does not hot-reload). Idempotent."""
    from app.services.rmf import refresh_text

    n = 0
    for p in policies:
        try:
            if refresh_text(db, p):
                n += 1
                continue
        except Exception as exc:  # a missing stored original must not stop the other policies
            p.analysis = {**(p.analysis or {}), "text_refresh_error": f"{type(exc).__name__}: {exc}"[:300]}
        if p.analysis_status == "analyzed" and (p.analysis or {}).get("coverage_version") != ANALYZER_VERSION:
            analyze(db, p)
            n += 1
    if n:
        db.flush()
    return n


AI_PROMPT = "policy.coverage_refine"
AI_BATCH = 8
log = logging.getLogger(__name__)


def _refine_batch(svc, items: list, control_id: str, text: str, stats: dict) -> dict:
    """One strict-JSON call for a batch; a truncated reply (finish_reason=length) is retried as two halves. Other failures → {}."""
    import asyncio
    import json

    from app.services.ai.service import AIOutputTruncatedError, ai_max_output_tokens
    stats["batches"] += 1
    try:
        res = asyncio.run(svc.run(AI_PROMPT, "1.0.0", {"control_id": control_id.upper(), "requirements": json.dumps(items),
                                                         "policy": text[:24000]}, max_tokens=ai_max_output_tokens()))
    except AIOutputTruncatedError:
        stats["truncated"] += 1
        if len(items) == 1:
            stats["failed"] += 1
            return {}
        half = len(items) // 2
        return {**_refine_batch(svc, items[:half], control_id, text, stats), **_refine_batch(svc, items[half:], control_id, text, stats)}
    except Exception as exc:
        stats["failed"] += 1
        log.warning("coverage AI batch failed for %s (%d requirements): %s – deterministic result kept", control_id, len(items), str(exc)[:200])
        return {}
    stats["succeeded"] += 1
    ids = {i["requirement_id"] for i in items}
    return {i.requirement_id: i.model_dump() for i in res.output.items if i.requirement_id in ids}


def ai_refine(text: str, control_id: str, reqs: list, results: list, org_id, stats: dict | None = None) -> dict:
    """Batches of AI_BATCH objectives/CCIs per call, merged into {requirement_id: {status, quote, rationale}}. A failed batch keeps
    its deterministic results without dropping the others; quotes are verified later by policy_profile.apply_ai."""
    from app.services.ai.service import get_ai_service

    svc = get_ai_service()
    if not svc.configured:
        return {}
    stats = stats if stats is not None else {}
    for k in ("batches", "succeeded", "failed", "truncated"):
        stats.setdefault(k, 0)
    items = [{"requirement_id": q["id"], "text": q["text"][:500], "deterministic": r["status"]} for q, (_, r) in zip(reqs, results)]
    merged: dict = {}
    for i in range(0, len(items), AI_BATCH):
        merged.update(_refine_batch(svc, items[i:i + AI_BATCH], control_id, text, stats))
    log.info("coverage AI %s: %d requirements, %s", control_id, len(items), stats)
    return merged


def effective(c: PolicyRequirementCoverage) -> str:
    """Coverage comes from the policy text only; covered-elsewhere/linked annotations are shown separately and never turn MISSING into MET."""
    return c.status


def basis_label(c: PolicyRequirementCoverage) -> str:
    return {"profile-id": "explicit control ID + concepts", "profile-concept": "concept match", "profile-ai": "AI-verified quote"}.get(
        c.concept, "policy-element rule" if is_xx1(c.control_id) else "keyword similarity")


def kind_label(c: PolicyRequirementCoverage) -> str:
    return "policy" if is_xx1(c.control_id) else pp.req_kind(c.text)


def gap_name(c: PolicyRequirementCoverage) -> str:
    if not is_xx1(c.control_id):
        return f"{c.label}: {(c.needs or c.text)[:90]}"
    concept, target, elem = classify(c.text)
    return LABEL.get(concept, "requirement").format(target=target, elem=elem or "")


def summarize(rows: list[PolicyRequirementCoverage]) -> dict:
    n = len(rows)
    met = sum(effective(c) == "met" for c in rows)
    missing = [c for c in rows if effective(c) == "missing"]
    partial = [c for c in rows if effective(c) == "partial"]
    gaps = sorted({gap_name(c) for c in missing + partial})
    state = "met" if n and met == n else "gaps" if missing else "partial" if partial else None
    return {"total": n, "met": met, "partial": len(partial), "missing": len(missing), "state": state, "gaps": gaps,
            "ccis": sum(c.requirement_type == "cci" for c in rows), "objectives": sum(c.requirement_type == "objective" for c in rows)}


def summary_line(control_id: str, s: dict) -> str:
    cid = control_id.upper().replace(".", "(") + (")" if "." in control_id else "")
    tail = f" – missing: {'; '.join(s['gaps'][:4])}" if s["gaps"] else ""
    scope = "this enhancement only" if "." in control_id else "base control only, enhancements counted separately"
    return f"{cid} ({scope}): {s['met']} of {s['total']} requirements met ({s['ccis']} CCIs, {s['objectives']} objectives){tail}"


def requirement_counts(db: Session, system: System, control_id: str) -> dict:
    """ONE documented counting rule for a control's requirements (docs/RMF_INTERPRETATION_DECISIONS.md "Requirement counting"):
    base = DISA CCIs (Rev 5 list, unique) + 800-53A assessment objectives of the control itself; "including enhancements" adds the
    enhancements ASSIGNED to this system; "met" = best result across the system's applicable current policies (combine()) – never summed per policy."""
    base = control_id.split(".")[0]
    assigned = sorted(c for c in db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == system.id,
                                                                                         ControlAssignment.control_id.like(f"{base}%")))
                      if c == base or c.startswith(base + "."))
    idx = index(db, system)

    def one(cid: str) -> dict:
        reqs = requirements(db, cid)
        e = idx.get(cid) or {}
        rows = combine([c for c in e.get("rows", []) if str(c.policy_id) in e.get("mapped", set())])  # approved mappings only
        met = {c.requirement_id for c in rows if effective(c) == "met"}
        return {"control_id": cid, "ccis": sorted({r["id"] for r in reqs if r["type"] == "cci"}), "objectives": [r["id"] for r in reqs if r["type"] == "objective"],
                "requirements": len(reqs), "met": sorted(met), "policies": sorted(e.get("mapped", set())),
                "proposed_policies": sorted(e.get("proposed", set()) - e.get("mapped", set()))}
    rows = [one(c) for c in assigned or [base]]
    b = next((r for r in rows if r["control_id"] == base), one(base))
    uniq = sorted({x for r in rows for x in r["ccis"]})
    return {"control_id": base, "rules": "CCIs are unique per control (Rev 5 DISA list); objectives are SP 800-53A Rev 5; 'met' is the best result across "
                                         "applicable current policies for the same requirement, never a sum over policies",
            "base_only": {"ccis": len(b["ccis"]), "objectives": len(b["objectives"]), "requirements": b["requirements"], "met": len(b["met"])},
            "including_assigned_enhancements": {"controls": [r["control_id"] for r in rows], "ccis_unique": len(uniq),
                                                "objectives": sum(len(r["objectives"]) for r in rows), "requirements": sum(r["requirements"] for r in rows),
                                                "met": sum(len(r["met"]) for r in rows)},
            "per_control": rows}


RANK = {"met": 0, "partial": 1, "missing": 2}


def combine(rows: list[PolicyRequirementCoverage]) -> list[PolicyRequirementCoverage]:
    """Best result per requirement across policies (each row keeps its policy_id, so the UI can say which policy matched)."""
    best: dict = {}
    for c in rows:
        k = (c.control_id, c.requirement_id)
        if k not in best or RANK[effective(c)] < RANK[effective(best[k])]:
            best[k] = c
    return list(best.values())


def scoped(e: dict | None, policies: set[str] | None) -> list[PolicyRequirementCoverage]:
    """Coverage rows for one control: only the selected policies when a policy filter is set (A3), else best-of across policies."""
    if not e:
        return []
    rows = [c for c in e["rows"] if not policies or str(c.policy_id) in policies]
    return combine(rows)


def applicable_policies(db: Session, system: System) -> list[Policy]:
    return [p for p in db.scalars(select(Policy).where(Policy.org_id == system.org_id, Policy.status == "current"))
            if not p.system_ids or str(system.id) in [str(x) for x in p.system_ids]]


def index(db: Session, system: System) -> dict:
    """control_id → {mapped: {policy ids}, proposed: {policy ids}, coverage: met|partial|gaps|None, rows}. One source for filters and counts."""
    pols = {p.id: p for p in applicable_policies(db, system)}
    out: dict = {}
    if not pols:
        return out
    for m in db.scalars(select(PolicyControlMap).where(PolicyControlMap.policy_id.in_(pols), PolicyControlMap.valid_to.is_(None))):
        if m.status in ("mapped", "proposed"):
            out.setdefault(m.control_id, {"mapped": set(), "proposed": set(), "rows": []})[m.status].add(str(m.policy_id))
    for c in db.scalars(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id.in_(pols))):
        e = out.get(c.control_id)
        if e is not None and str(c.policy_id) in e["mapped"] | e["proposed"]:
            e["rows"].append(c)
    for e in out.values():
        e["coverage"] = summarize(combine(e["rows"]))["state"] if e["rows"] else None
    return out


FACETS = {"policy_mapping": ("mapped", "not_mapped", "proposed"), "policy_coverage": ("met", "partial", "gaps")}


def matches(e: dict | None, policy_mapping: str | None, policies: set[str] | None, policy_coverage: str | None) -> bool:
    if policy_mapping == "mapped" and not (e and e["mapped"]):
        return False
    if policy_mapping == "proposed" and not (e and e["proposed"] and not e["mapped"]):
        return False
    if policy_mapping == "not_mapped" and e and (e["mapped"] or e["proposed"]):
        return False
    if policies and not (e and (e["mapped"] | e["proposed"]) & policies):
        return False
    if policy_coverage:
        rows = scoped(e, policies)
        if not rows or summarize(rows)["state"] != policy_coverage:
            return False
    return True


def facet_counts(db: Session, system: System) -> dict:
    idx = index(db, system)
    ids = list(db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == system.id)))
    pols = applicable_policies(db, system)
    return {"policy_mapping": {v: sum(matches(idx.get(c), v, None, None) for c in ids) for v in FACETS["policy_mapping"]},
            "policy_coverage": {v: sum(matches(idx.get(c), None, None, v) for c in ids) for v in FACETS["policy_coverage"]},
            "policy": [{"id": str(p.id), "title": p.title, "version": p.version, "count": sum(matches(idx.get(c), None, {str(p.id)}, None) for c in ids)} for p in pols]}


def fingerprint(rows) -> str:
    return hashlib.sha256("|".join(sorted(f"{c.requirement_id}:{effective(c)}" for c in rows)).encode()).hexdigest()[:16]


DISMISSED = "policy_status_dismissed"


def technical_evidence(db: Session, a: ControlAssignment, policy: Policy) -> bool:
    """Current, passing technical evidence (scan/STIG/config – not the policy file itself) and no open findings for the control."""
    from app.models import Evidence, EvidenceControl
    from app.services.evaluation import FRESH_OK

    if a.evidence_freshness_status not in FRESH_OK or (a.evaluation or {}).get("open_findings", 0):
        return False
    pol_ev = {str(e) for e in (policy.evidence_ids or [])}
    for eid, et in db.execute(select(Evidence.id, Evidence.evidence_type).join(EvidenceControl, EvidenceControl.evidence_id == Evidence.id)
                              .where(EvidenceControl.assignment_id == a.id, Evidence.state.in_(("current", "near_expiration")))):
        if str(eid) not in pol_ev and "policy" not in (et or "").lower():
            return True
    return False


def policy_view(db: Session, a: ControlAssignment, rows: list, policy: Policy) -> dict:
    """What ONE current policy version's own text supports for this control. Low-confidence rows never count as met (review needed);
    linked-as-evidence and covered-elsewhere annotations are ignored – only the policy text decides."""
    from app.services import policy_profile as pp

    s = summarize(rows)
    low = [c for c in rows if c.confidence == "Low" and c.status != "missing"]
    sure = [c for c in rows if c.confidence != "Low" or c.status == "missing"]
    met = [c for c in sure if c.status == "met"]
    policy_gap = len(met) < len(rows)
    if is_xx1(a.control_id):
        target, tech_needed = ("implemented" if not policy_gap else "partially_implemented"), []
    else:
        has_ev = technical_evidence(db, a, policy)
        tech_needed = [c.label for c in rows if pp.req_kind(c.text) == "technical"] if not has_ev else []
        target = "implemented" if not policy_gap and has_ev else "partially_implemented"
    return {"policy": policy, "summary": s, "met": len(met), "low": [c.label for c in low], "policy_gap": policy_gap, "target": target,
            "tech_needed": tech_needed, "confident": bool(met), "rows": rows}


def control_decision(db: Session, a: ControlAssignment, views: list[dict]) -> dict:
    """ONE decision per control across every current policy mapped to it (the most conservative wins), so approving it can never
    make another policy produce the opposite suggestion from the same inputs."""
    label = {"implemented": "Implemented", "partially_implemented": "Partially Implemented"}
    conf = [v for v in views if v["confident"]]
    cid = a.control_id.upper()
    if not conf:
        low = [x for v in views for x in v["low"]]
        if low:
            return {"note": f"{cid}: {len(low)} requirement(s) matched with low confidence – review the coverage; no status is suggested.", "review": True}
        return {"note": f"{cid}: the policy text meets none of its requirements – no status is suggested."}
    target = "partially_implemented" if any(v["target"] == "partially_implemented" for v in conf) else "implemented"
    gap = any(v["policy_gap"] for v in conf)
    gov = max((v for v in conf if v["target"] == target), key=lambda v: (v["policy_gap"], v["policy"].created_at))
    cur = a.implementation_status
    if cur in ("not_applicable", "inherited"):
        return {"note": f"{cid} is {cur.replace('_', ' ')} – policy coverage does not change it."}
    if cur == target:
        return {"note": f"{cid} is already {label[target]} – this matches the current policy coverage."}
    if cur == "implemented" and not gap:
        return {"note": f"{cid} stays Implemented: the policy covers every requirement; technical evidence is still needed for: {', '.join(gov['tech_needed'][:4])}."}
    p, s = gov["policy"], gov["summary"]
    if cur == "implemented":
        title = f"{cid} is Implemented but the latest policy version (v{p.version}) is missing: {'; '.join(s['gaps'][:4]) or 'some requirements'} – suggest {label[target]}"
    elif target == "partially_implemented" and gov["tech_needed"]:
        title = f"{summary_line(a.control_id, s)} → Partially Implemented – technical evidence needed for: {', '.join(gov['tech_needed'][:4])}"
    else:
        title = f"{summary_line(a.control_id, s)} → Implementation: {label[target]}"
    per = [f"“{v['policy'].title}” v{v['policy'].version}: {v['met']} of {v['summary']['total']} met" + (" (gaps)" if v["policy_gap"] else "") for v in views]
    why = (f"Policies covering {cid}: {'; '.join(per)}. The most conservative result is used." if len(views) > 1 else
           ("All requirements are met by the policy text." if not gov["policy_gap"] else f"Gaps: {'; '.join(s['gaps'][:6])}."))
    if gov["tech_needed"]:
        why += f" Policy alone cannot prove implementation – technical evidence (scan/STIG/configuration) is still required for: {', '.join(gov['tech_needed'][:6])}."
    if any(v["low"] for v in views):
        why += f" Review needed (low confidence, not counted): {', '.join(x for v in views for x in v['low'])[:200]}."
    rows = [c for v in views for c in v["rows"]]
    return {"target": target, "governing": gov, "title": title, "reasoning": why, "downgrade": cur == "implemented", "tech_needed": gov["tech_needed"],
            "fp": fingerprint(rows), "rows": rows}


def _views(db: Session, system: System, assigned: dict) -> tuple[dict, list]:
    views: dict = {}
    pending = []
    for p in applicable_policies(db, system):
        maps = {m.control_id: m for m in db.scalars(select(PolicyControlMap).where(PolicyControlMap.policy_id == p.id, PolicyControlMap.valid_to.is_(None)))}
        rows: dict = {}
        for c in db.scalars(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id == p.id)):
            rows.setdefault(c.control_id, []).append(c)
        for cid, m in maps.items():
            a = assigned.get(cid)
            if a is None or m.status == "rejected":
                continue
            if cid not in rows:
                pending.append(f"Status suggestion for {cid.upper()} will appear after you approve the {cid.upper()} mapping of “{p.title}” v{p.version} "
                               f"(it was proposed with {m.confidence} confidence, so its requirements were not assessed yet).")
                continue
            views.setdefault(cid, []).append({**policy_view(db, a, rows[cid], p), "mapping": m})
    return views, pending


def suggestions(db: Session, system: System, review: list | None = None, notes: list | None = None) -> list[dict]:
    """One Mapping Review item per control whose combined policy coverage disagrees with its status (A1 downgrade included).
    Controls without an item get a plain-language note saying why."""
    from app.services.rmf import get_setting

    dismissed = get_setting(db, system.org_id, DISMISSED, {}).get(str(system.id), {})
    assigned = {a.control_id: a for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == system.id))}
    views, pending = _views(db, system, assigned)
    if notes is not None:
        notes.extend(pending)
    out = []
    for cid, vs in sorted(views.items()):
        a = assigned[cid]
        d = control_decision(db, a, vs)
        if "target" not in d:
            if d.get("review") and review is not None:
                review.append({"control_id": cid, "policy_id": str(vs[0]["policy"].id), "policy": f"{vs[0]['policy'].title} v{vs[0]['policy'].version}",
                               "message": d["note"], "low_confidence": [x for v in vs for x in v["low"]][:10]})
            elif notes is not None:
                notes.append(d["note"])
            continue
        if dismissed.get(f"ctl:{cid}") == d["fp"]:
            if notes is not None:
                notes.append(f"{cid.upper()}: the suggestion was rejected; it returns only if the policy coverage changes.")
            continue
        p, s = d["governing"]["policy"], d["governing"]["summary"]
        out.append({"kind": "policy_status", "key": f"ps:{p.id}:{cid}", "ids": [str(p.id)], "control_id": cid, "policy_id": str(p.id), "target": d["target"],
                    "title": d["title"], "downgrade": d["downgrade"], "tech_needed": d["tech_needed"], "policy_version": p.version,
                    "policies": [f"{v['policy'].title} v{v['policy'].version}" for v in vs],
                    "mapping_note": (f"Based on a proposed {d['governing']['mapping'].confidence}-confidence mapping – approving this also approves the "
                                     f"{cid.upper()} mapping from “{p.title}” v{p.version}" if d["governing"].get("mapping") is not None
                                     and d["governing"]["mapping"].status == "proposed" else None),
                    "source": f"Policy Auditor – CCI/objective coverage of “{p.title}” v{p.version} (current version)", "confidence": "Suggestion", "coverage": s,
                    "current": {"implementation": a.implementation_status, "assessment": a.assessment_status},
                    "reasoning": d["reasoning"] + " Approving sets the implementation status and links the policy as evidence for the met requirements; the SCA still confirms assessment.",
                    "snippets": [x["text"] for c in d["governing"]["rows"] if c.status == "met" for x in (c.snippets or [])][:2],
                    "evidence": [{"id": str(e), "file_name": p.file_name} for e in (p.evidence_ids or [])][:1], "evidence_fp": d["fp"]})
    return out


def dismiss(db: Session, system: System, policy_id: str, control_id: str, fp: str, actor, justification: str) -> None:
    from app.services.rmf import get_setting, set_setting

    all_ = get_setting(db, system.org_id, DISMISSED, {})
    all_.setdefault(str(system.id), {})[f"ctl:{control_id}"] = fp
    set_setting(db, system.org_id, DISMISSED, all_)


def approve(db: Session, system: System, policy: Policy, control_id: str, actor) -> dict:
    from app.models import EvidenceControl
    from app.services import policy_mapping as pm

    a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == system.id, ControlAssignment.control_id == control_id))
    if a is None:
        raise ValueError("Nothing to approve for this control")
    vs = _views(db, system, {control_id: a})[0].get(control_id, [])
    d = control_decision(db, a, vs) if vs else {"note": "No current policy coverage for this control"}
    if "target" not in d:
        raise ValueError(f"No status suggestion is open for this control – {d['note']}")
    policy, rows = d["governing"]["policy"], d["rows"]
    s, target = d["governing"]["summary"], d["target"]
    before = {"implementation_status": a.implementation_status}
    a.implementation_status = target
    stamp = {"assignment_id": str(a.id), "system_id": str(system.id), "by": actor.email, "at": now().isoformat()}
    linked = []
    for c in rows:
        if c.status == "met" and c.confidence != "Low":
            c.linked = stamp
            linked.append(c.requirement_id)
    for e in policy.evidence_ids or []:
        if not db.scalar(select(EvidenceControl.id).where(EvidenceControl.evidence_id == uuid.UUID(str(e)), EvidenceControl.assignment_id == a.id)):
            db.add(EvidenceControl(evidence_id=uuid.UUID(str(e)), assignment_id=a.id))
    also = []
    m = next((x for x in pm.current(db, policy.id) if x.control_id == control_id), None)
    if m is not None and m.status == "proposed":  # intended: the suggestion rests on this mapping, so approving it resolves the mapping item too
        pm.decide(db, policy, control_id, "mapped", actor, "Approved with the CCI coverage status suggestion")
        also.append({"map_id": str(m.id), "control_id": control_id, "policy_id": str(policy.id), "policy": policy.title, "version": policy.version,
                     "text": f"{control_id.upper()} mapping from “{policy.title}” v{policy.version}"})
    db.flush()
    return {"assignment": a, "before": before, "target": target, "linked": linked, "summary": s, "also_approved": also, "policy": policy}
