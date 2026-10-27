"""Policy → control mapping: explicit control IDs (base, enhancement, part), "-1 policy and procedures" statement language,
and control-title language. Each mapping carries a confidence (High/Medium/Low), its basis and the matched snippets."""
import re
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Control, PolicyControlMap

# RA-1 · RA-1a · RA-1a.1 · RA-1.a · AC-2(1) · AC-2 (1) · AC-2(1)(a)
CID_RX = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2})-(\d{1,2})(?:\s?\((\d{1,2})\))?(?:\.?([a-z])(?:\.?(\d{1,2}))?)?(?![A-Za-z0-9])")
POLICY_TERMS = ("purpose", "scope", "roles", "responsibilities", "management commitment", "coordination", "compliance", "procedures")
CONF_RANK = {"High": 0, "Medium": 1, "Low": 2}


def _sentence(text: str, start: int, end: int) -> str:
    from app.services.rmf import sentence_at
    ls, le = text.rfind("\n", 0, start) + 1, text.find("\n", end)
    line = text[ls:le if le >= 0 else len(text)]
    if " | " in line:  # table row (e.g. traceability matrix): the whole row, not cut at "8.2"
        return line.strip()[:300]
    s, e = sentence_at(text, start, end)
    return text[s:e].strip()[:300]


NOT_SEL = re.compile(r"\bnot selected\b", re.I)


def _not_selected(text: str, known: set) -> dict:
    """Controls the policy itself declares "not selected": a table row whose first cell is the control and a later cell says so,
    or prose where "not selected" follows the control ID within the same clause (no other ID in between)."""
    out: dict = {}
    for line in text.splitlines():
        if not NOT_SEL.search(line):
            continue
        cells = line.split(" | ")
        ids = list(CID_RX.finditer(line))
        for i, mt in enumerate(ids):
            fam, num, enh = mt.group(1), mt.group(2), mt.group(3)
            cid = f"{fam.lower()}-{int(num)}" + (f".{int(enh)}" if enh else "")
            if cid not in known:
                continue
            if len(cells) > 1:
                hit = mt.start() < len(cells[0]) and len(ids[:i]) == 0 and any(NOT_SEL.search(c) for c in cells[1:])
            else:
                nxt = ids[i + 1].start() if i + 1 < len(ids) else len(line)
                hit = bool(NOT_SEL.search(line[mt.end():min(nxt, mt.end() + 60)]))
            if hit:
                out.setdefault(cid, line.strip()[:300])
    return out


def extract_mappings(db: Session, text: str, detail: dict | None = None) -> list[dict]:
    """Proposals (review items). When the policy declares its controls by explicit ID, title-only matches in OTHER families are not
    proposed – they are returned in detail["possible_related"] (low confidence, not proposed; a reviewer can promote one manually).
    detail["not_selected"]: controls the policy states are not selected (kept as proposals, flagged for human review, no gap rows)."""
    rows = db.execute(select(Control.control_id, Control.family_id, Control.title, Control.is_withdrawn)
                      .where(Control.catalog_version_id == _cat(db))).all()
    known = {r.control_id for r in rows if not r.is_withdrawn}
    fam_title = {}
    for r in rows:
        if "-" in r.control_id and "." not in r.control_id and r.control_id.endswith("-1"):
            fam_title[r.family_id] = None
    from app.models import Control as C
    for fid, ftitle in db.execute(select(C.family_id, C.family_title).where(C.catalog_version_id == _cat(db)).distinct()):
        fam_title[fid] = ftitle
    out: dict[str, dict] = {}

    def add(cid, conf, source, basis, snippet=None, part=None):
        m = out.setdefault(cid, {"control_id": cid, "confidence": conf, "sources": [], "basis": [], "snippets": [], "parts": [], "mentions": 0})
        if CONF_RANK[conf] < CONF_RANK[m["confidence"]]:
            m["confidence"] = conf
        if source not in m["sources"]:
            m["sources"].append(source)
            m["basis"].append(basis)
        row = bool(snippet) and " | " in snippet and bool(CID_RX.match(snippet)) and source == "explicit_id"  # matrix row naming this control
        if snippet and snippet not in m["snippets"] and (len(m["snippets"]) < 4 or (row and sum(" | " in x for x in m["snippets"]) < 2)):
            m["snippets"].append(snippet)
        if part and part not in m["parts"]:
            m["parts"].append(part)
        m["mentions"] += 1

    for mt in CID_RX.finditer(text):
        fam, num, enh, part, sub = mt.groups()
        base = f"{fam.lower()}-{int(num)}"
        cid = f"{base}.{int(enh)}" if enh else base
        if cid not in known:
            continue
        label = f"{fam.upper()}-{int(num)}" + (f"({int(enh)})" if enh else "") + (part or "") + (f".{sub}" if sub else "")
        add(cid, "High", "explicit_id", "explicit control ID in the text", _sentence(text, mt.start(), mt.end()), label if part else None)

    low = text.lower()
    terms = [t for t in POLICY_TERMS if re.search(rf"\b{re.escape(t)}\b", low)]
    if len(terms) >= 4:
        for fid, ftitle in fam_title.items():
            if not ftitle:
                continue
            hits = [m.start() for m in re.finditer(rf"\b{re.escape(ftitle.lower())}\b", low)]
            if len(hits) >= 2 and f"{fid}-1" in known:
                i = low.find("purpose") if "purpose" in terms else hits[0]
                add(f"{fid}-1", "Medium", "statement_language",
                    f"{fid.upper()}-1 statement language: “{ftitle}” policy + {len(terms)}/{len(POLICY_TERMS)} policy elements ({', '.join(terms)})",
                    _sentence(text, i, i + 1), f"{fid.upper()}-1a.1")
    for r in rows:
        t = (r.title or "").lower()
        if r.is_withdrawn or t == "policy and procedures" or len(t) < 12 or len(t.split()) < 2:
            continue
        i = low.find(t)
        if i >= 0:
            add(r.control_id, "Low", "title_language", f"control title “{r.title}” appears in the text", _sentence(text, i, i + len(t)))
    declared = {c.split("-")[0] for c, m in out.items() if "explicit_id" in m["sources"]}
    related = [m for c, m in out.items() if declared and set(m["sources"]) <= {"title_language", "statement_language"} and c.split("-")[0] not in declared]
    for m in related:
        del out[m["control_id"]]
    ns = _not_selected(text, known)
    for c, line in ns.items():
        if c in out:
            out[c]["not_selected"] = line
            out[c]["basis"].insert(0, f"policy states not selected: “{line[:200]}”")
    if detail is not None:
        detail["possible_related"] = [{"control_id": m["control_id"], "confidence": "Low", "status": "possible related control (low confidence, not proposed)",
                                       "basis": "; ".join(m["basis"]), "matched_text": m["snippets"][:2]} for m in sorted(related, key=lambda x: x["control_id"])]
        detail["not_selected"] = ns
    ranked = sorted(out.values(), key=lambda m: (CONF_RANK[m["confidence"]], -len(m["sources"]), -m["mentions"], m["control_id"]))
    return ranked


def _cat(db: Session):
    from app.services.content.loader import active_catalog_id
    return active_catalog_id(db)


def now() -> datetime:
    return datetime.now(timezone.utc)


def current(db: Session, policy_id) -> list[PolicyControlMap]:
    return list(db.scalars(select(PolicyControlMap).where(PolicyControlMap.policy_id == policy_id, PolicyControlMap.valid_to.is_(None))))


def store_proposals(db: Session, policy, mappings: list[dict]) -> None:
    """Re-analysis replaces parser proposals; human decisions (mapped/rejected) are kept and never re-proposed."""
    cur = {m.control_id: m for m in current(db, policy.id)}
    found = {m["control_id"] for m in mappings}
    for m in cur.values():  # a reviewer-promoted "possible related" proposal stays open until a human decides (unless the parser now proposes it)
        if m.status == "proposed" and (m.source != RELATED_SRC or m.control_id in found):
            m.valid_to = now()
    for m in mappings:
        prev = cur.get(m["control_id"])
        if prev is not None and prev.status == "proposed":
            prev = None
        if prev is not None and prev.status != "proposed":  # never overwrite a human decision – keep a proposal that "differs from approved"
            if prev.confidence != m["confidence"] or sorted(prev.snippets or []) != sorted(m["snippets"]):
                prev.reanalysis = {"label": "differs from approved", "confidence": m["confidence"], "snippets": m["snippets"],
                                   "basis": "; ".join(m["basis"]), "at": now().isoformat()}
            continue
        db.add(PolicyControlMap(id=uuid.uuid4(), policy_id=policy.id, org_id=policy.org_id, control_id=m["control_id"], status="proposed",
                                source="+".join(m["sources"]), confidence=m["confidence"], basis="; ".join(m["basis"]),
                                snippets=m["snippets"], parts=m["parts"], review_flag=bool(m.get("not_selected"))))
    db.flush()


RELATED_SRC = "related_promoted"


def propose_related(db: Session, policy, control_id: str, actor) -> PolicyControlMap:
    """'Send to Mapping Review' for a possible related control: an OPEN proposal (no decision, decided_by empty) with the matched text
    as basis; it stays undecided until an authorized reviewer decides in Mapping Review."""
    if any(m.control_id == control_id for m in current(db, policy.id)):
        raise ValueError(f"{control_id} already has a mapping or proposal on this policy")
    det: dict = {}
    extract_mappings(db, policy.text_content or "", det)
    rel = next((r for r in det.get("possible_related", []) if r["control_id"] == control_id), None)
    if rel is None:
        raise LookupError(f"{control_id} is not a possible related control of this policy")
    row = PolicyControlMap(id=uuid.uuid4(), policy_id=policy.id, org_id=policy.org_id, control_id=control_id, status="proposed", source=RELATED_SRC,
                           confidence="Low", basis=f"possible related control sent to Mapping Review by {actor.email}; {rel['basis']}",
                           snippets=rel["matched_text"], parts=[], review_flag=True)
    db.add(row)
    db.flush()
    return row


def decide(db: Session, policy, control_id: str, status: str, actor, justification: str | None) -> PolicyControlMap:
    prev = next((m for m in current(db, policy.id) if m.control_id == control_id), None)
    if prev is not None:
        prev.valid_to = now()
    det: dict = {}
    found = None if prev else next((m for m in extract_mappings(db, policy.text_content or "", det) if m["control_id"] == control_id), None)
    rel = None if prev or found else next((r for r in det.get("possible_related", []) if r["control_id"] == control_id), None)
    if rel:  # reviewer promotes a "possible related control" – keep its matched text, still Low
        found = {"sources": ["title_language"], "confidence": "Low", "basis": [rel["basis"]], "snippets": rel["matched_text"], "parts": []}
    # A manual mapping is not "High" by default: it gets the evidence the text actually contains, or Low with no excerpt (manual review).
    row = PolicyControlMap(id=uuid.uuid4(), policy_id=policy.id, org_id=policy.org_id, control_id=control_id, status=status,
                           source=prev.source if prev else ("+".join(found["sources"])[:30] if found else "manual"),
                           confidence=prev.confidence if prev else (found["confidence"] if found else "Low"),
                           basis=(prev.basis if prev else ("manual mapping by a reviewer; " + "; ".join(found["basis"]) if found else
                                                           "manual mapping by a reviewer – no supporting text found, manual review required")),
                           snippets=prev.snippets if prev else (found["snippets"] if found else []),
                           parts=prev.parts if prev else (found["parts"] if found else []), justification=justification, decided_by=actor.id, decided_at=now(),
                           comments=prev.comments if prev else None, review_flag=prev.review_flag if prev else False)
    db.add(row)
    db.flush()
    from app.services import policy_coverage as pc

    pending = DEFER_ANALYZE.get()
    if pending is not None:  # bulk job: analyse each policy once per batch instead of once per decision
        pending[policy.id] = policy
    else:
        pc.analyze(db, policy)
    return row


import contextvars  # noqa: E402

DEFER_ANALYZE: contextvars.ContextVar[dict | None] = contextvars.ContextVar("defer_policy_analyze", default=None)
