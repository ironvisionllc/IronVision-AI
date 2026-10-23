"""Policy Auditor requirement coverage. For every control a policy maps to, list its requirements (DISA CCIs + SP 800-53A
assessment objectives) and decide MET / PARTIAL / MISSING from the policy text with deterministic keyword/section heuristics.
Each result keeps the matched snippet(s) with page/section, a confidence, the reason, any organization-defined value found
(e.g. review frequency) and – when not met – what text would satisfy it. Nothing here changes a control status."""
import hashlib
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Cci, CciControlMap, Control, ControlAssignment, ControlObjective, Policy, PolicyControlMap, PolicyRequirementCoverage, System
from app.services.rmf import locate

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


def analyze(db: Session, policy: Policy) -> list[PolicyRequirementCoverage]:
    """Recompute coverage for every current proposed/mapped control of this policy; covered-elsewhere overrides are kept."""
    maps = [m for m in db.scalars(select(PolicyControlMap).where(PolicyControlMap.policy_id == policy.id, PolicyControlMap.valid_to.is_(None)))
            if m.status == "mapped" or (m.status == "proposed" and m.confidence in ("High", "Medium"))]
    old = {(c.control_id, c.requirement_id): c for c in db.scalars(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id == policy.id))}
    for c in old.values():
        db.delete(c)
    db.flush()
    text = policy.text_content or ""
    out = []
    for m in maps:
        fam = db.scalar(select(Control.family_title).where(Control.control_id == m.control_id).limit(1)) or m.control_id.split("-")[0].upper()
        for req in requirements(db, m.control_id):
            concept, target, elem = classify(req["text"])
            r = evaluate(text, concept, target, elem, fam, req["text"])
            prev = old.get((m.control_id, req["id"]))
            row = PolicyRequirementCoverage(id=uuid.uuid4(), org_id=policy.org_id, policy_id=policy.id, policy_version=policy.version, control_id=m.control_id,
                                            requirement_type=req["type"], requirement_id=req["id"], label=req["label"], text=req["text"], concept=concept,
                                            status=r["status"], confidence=r["confidence"], reason=r["reason"], snippets=r["snippets"],
                                            parameter=r["parameter"], parameter_value=r["value"], needs=r["needs"] if r["status"] != "met" else None,
                                            source="deterministic", override=prev.override if prev else None,
                                            linked=prev.linked if prev else None)
            db.add(row)
            out.append(row)
    db.flush()
    return out


def effective(c: PolicyRequirementCoverage) -> str:
    return "met" if c.override else c.status


def gap_name(c: PolicyRequirementCoverage) -> str:
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
    return f"{cid}: {s['met']} of {s['total']} requirements met ({s['ccis']} CCIs, {s['objectives']} objectives){tail}"


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
        e["coverage"] = summarize(e["rows"])["state"] if e["rows"] else None
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
    if policy_coverage and not (e and e["coverage"] == policy_coverage):
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


def suggestions(db: Session, system: System) -> list[dict]:
    from app.services.rmf import get_setting

    dismissed = get_setting(db, system.org_id, DISMISSED, {}).get(str(system.id), {})
    assigned = {a.control_id: a for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == system.id))}
    out = []
    for p in applicable_policies(db, system):
        maps = {m.control_id: m for m in db.scalars(select(PolicyControlMap).where(PolicyControlMap.policy_id == p.id, PolicyControlMap.valid_to.is_(None)))}
        rows: dict = {}
        for c in db.scalars(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id == p.id)):
            rows.setdefault(c.control_id, []).append(c)
        for cid, rs in rows.items():
            a, m = assigned.get(cid), maps.get(cid)
            if a is None or m is None or m.status == "rejected" or not re.fullmatch(r"[a-z]{2}-1", cid):
                continue
            s = summarize(rs)
            if s["met"] == 0:
                continue
            target = "implemented" if s["state"] == "met" else "partially_implemented"
            if a.implementation_status == target or (target == "partially_implemented" and a.implementation_status == "implemented"):
                continue
            fp = fingerprint(rs)
            if dismissed.get(f"{p.id}:{cid}") == fp:
                continue
            line = summary_line(cid, s)
            out.append({"kind": "policy_status", "key": f"ps:{p.id}:{cid}", "ids": [str(p.id)], "control_id": cid, "policy_id": str(p.id), "target": target,
                        "title": f"{line} → Implementation: {'Implemented' if target == 'implemented' else 'Partially Implemented'}",
                        "source": f"Policy Auditor – CCI/objective coverage of “{p.title}” v{p.version}", "confidence": "Suggestion", "coverage": s,
                        "current": {"implementation": a.implementation_status, "assessment": a.assessment_status},
                        "reasoning": ("All requirements are met by the policy text." if target == "implemented" else f"Gaps: {'; '.join(s['gaps'])}.")
                                     + " Approving sets the implementation status and links the policy as evidence for the met CCIs; the SCA still confirms assessment.",
                        "snippets": [x["text"] for c in rs if effective(c) == "met" for x in (c.snippets or [])][:2],
                        "evidence": [{"id": str(e), "file_name": p.file_name} for e in (p.evidence_ids or [])][:1], "evidence_fp": fp})
    return out


def dismiss(db: Session, system: System, policy_id: str, control_id: str, fp: str, actor, justification: str) -> None:
    from app.services.rmf import get_setting, set_setting

    all_ = get_setting(db, system.org_id, DISMISSED, {})
    all_.setdefault(str(system.id), {})[f"{policy_id}:{control_id}"] = fp
    set_setting(db, system.org_id, DISMISSED, all_)


def approve(db: Session, system: System, policy: Policy, control_id: str, actor) -> dict:
    from app.models import EvidenceControl
    from app.services import policy_mapping as pm

    a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == system.id, ControlAssignment.control_id == control_id))
    rows = list(db.scalars(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id == policy.id, PolicyRequirementCoverage.control_id == control_id)))
    if a is None or not rows:
        raise ValueError("Nothing to approve for this control")
    s = summarize(rows)
    target = "implemented" if s["state"] == "met" else "partially_implemented"
    before = {"implementation_status": a.implementation_status}
    a.implementation_status = target
    stamp = {"assignment_id": str(a.id), "system_id": str(system.id), "by": actor.email, "at": now().isoformat()}
    linked = []
    for c in rows:
        if effective(c) == "met":
            c.linked = stamp
            linked.append(c.requirement_id)
    for e in policy.evidence_ids or []:
        if not db.scalar(select(EvidenceControl.id).where(EvidenceControl.evidence_id == uuid.UUID(str(e)), EvidenceControl.assignment_id == a.id)):
            db.add(EvidenceControl(evidence_id=uuid.UUID(str(e)), assignment_id=a.id))
    m = next((x for x in pm.current(db, policy.id) if x.control_id == control_id), None)
    if m is not None and m.status == "proposed":
        pm.decide(db, policy, control_id, "mapped", actor, "Approved with the CCI coverage status suggestion")
    db.flush()
    return {"assignment": a, "before": before, "target": target, "linked": linked, "summary": s}
