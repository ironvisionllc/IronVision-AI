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
    s, e = sentence_at(text, start, end)
    return text[s:e].strip()[:300]


def extract_mappings(db: Session, text: str) -> list[dict]:
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
        if snippet and snippet not in m["snippets"] and len(m["snippets"]) < 4:
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
    for m in cur.values():
        if m.status == "proposed":
            m.valid_to = now()
    for m in mappings:
        prev = cur.get(m["control_id"])
        if prev is not None and prev.status != "proposed":
            continue
        db.add(PolicyControlMap(id=uuid.uuid4(), policy_id=policy.id, org_id=policy.org_id, control_id=m["control_id"], status="proposed",
                                source="+".join(m["sources"]), confidence=m["confidence"], basis="; ".join(m["basis"]),
                                snippets=m["snippets"], parts=m["parts"]))
    db.flush()


def decide(db: Session, policy, control_id: str, status: str, actor, justification: str | None) -> PolicyControlMap:
    prev = next((m for m in current(db, policy.id) if m.control_id == control_id), None)
    if prev is not None:
        prev.valid_to = now()
    row = PolicyControlMap(id=uuid.uuid4(), policy_id=policy.id, org_id=policy.org_id, control_id=control_id, status=status,
                           source=prev.source if prev else "manual", confidence=prev.confidence if prev else "High",
                           basis=(prev.basis if prev else "manual mapping by a reviewer"), snippets=prev.snippets if prev else [],
                           parts=prev.parts if prev else [], justification=justification, decided_by=actor.id, decided_at=now())
    db.add(row)
    db.flush()
    from app.services import policy_coverage as pc

    pc.analyze(db, policy)
    return row
