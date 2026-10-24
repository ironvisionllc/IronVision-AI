"""CNSSI No. 1253 (29 July 2022) Appendix D NSS baselines: selection per security objective (Task S-1, §3.2.1, p. 10).
Data: content/cnssi1253_baselines.json (parsed by scripts/parse_cnssi1253.py from the SHA-256-pinned source PDF)."""
import json
import re
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ControlAssignment, Implementation, System, TailoringDecision

PATH = Path(__file__).parent / "content" / "cnssi1253_baselines.json"
LV = {"low": "l", "moderate": "m", "high": "h"}
SEL = ("X", "+")


@lru_cache
def data() -> dict:
    return json.loads(PATH.read_text())


def rows() -> list[dict]:
    return data()["rows"]


def trigraph(c: str | None, i: str | None, a: str | None) -> str | None:
    if not (c and i and a) or any(v.lower() not in LV for v in (c, i, a)):
        return None
    return "-".join(v[0].upper() for v in (c, i, a))


def system_trigraph(s: System) -> str | None:
    return trigraph(s.confidentiality_impact, s.integrity_impact, s.availability_impact) if s.categorization_mode == "cnssi1253" else None


@lru_cache(maxsize=32)
def selection(tri: str) -> dict:
    """Controls selected for a trigraph (e.g. 'M-H-L'): C column at C level ∪ I at I level ∪ A at A level ∪ privacy control baseline."""
    lv = dict(zip("cia", tri.lower().split("-")))
    by: dict[str, set] = {"c": set(), "i": set(), "a": set(), "privacy": set()}
    why: dict[str, list] = {}
    for r in rows():
        if r["withdrawn"] or r.get("not_in_catalog"):
            continue
        for o in "cia":
            mark = r["marks"][f"{o}_{lv[o]}"]
            if mark in SEL:
                by[o].add(r["control_id"])
                why.setdefault(r["control_id"], []).append(f"{o.upper()}={lv[o].upper()}{' (+ NSS addition)' if mark == '+' else ''}")
        if r["privacy_baseline"] in SEL:
            by["privacy"].add(r["control_id"])
            why.setdefault(r["control_id"], []).append("Privacy Control Baseline (all NSS)")
    ids = by["c"] | by["i"] | by["a"] | by["privacy"]
    return {"trigraph": tri, "ids": ids, "by": by, "why": why, "security_union": len(by["c"] | by["i"] | by["a"])}


def basis(cid: str, tri: str) -> str | None:
    r = next((x for x in rows() if x["control_id"] == cid), None)
    w = selection(tri)["why"].get(cid)
    if not (r and w):
        return None
    return f"Selected by CNSSI 1253 {r['table']} ({', '.join(w)}), p. {r['doc_page']} (PDF p. {r['pdf_page']})"


def row(cid: str) -> dict | None:
    return next((x for x in rows() if x["control_id"] == cid), None)


def uncovered_catalog_ids(db: Session) -> list[str]:
    """Selectable Rev 5 catalog controls with no row in the CNSSI 1253 tables (added to 800-53 after July 2022)."""
    from app.models import Control
    from app.services.content.loader import active_catalog_id

    have = {r["control_id"] for r in rows()}
    return sorted(c for c in db.scalars(select(Control.control_id).where(Control.catalog_version_id == active_catalog_id(db),
                                                                         Control.is_withdrawn.is_(False))) if c not in have)


def applied(s: System) -> str | None:
    return (s.cnssi_baseline or {}).get("applied")


def _with_work(db: Session, s: System, ids: set) -> set:
    """Assignments that carry work (an approved/submitted statement, assessment or evidence) – never dropped silently."""
    from app.models import EvidenceControl

    out = set()
    for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == s.id, ControlAssignment.control_id.in_(ids))):
        stm = db.scalar(select(Implementation.review_status).where(Implementation.assignment_id == a.id).order_by(Implementation.version.desc()).limit(1))
        ev = db.scalar(select(EvidenceControl.id).where(EvidenceControl.assignment_id == a.id).limit(1))
        if (stm and stm != "draft") or ev or (a.assessment_status or "not_assessed") != "not_assessed":
            out.add(a.control_id)
    return out


def approval_state(db: Session, s: System) -> dict:
    """Approved categorization trigraph (the one in force) vs a newer draft / pending re-approval revision."""
    from app.services.rmf_accuracy import latest

    ap, cur = latest(db, s.id, "approved"), latest(db, s.id)
    imp = (ap.impacts or {}) if ap else {}
    tri = trigraph(imp.get("c"), imp.get("i"), imp.get("a")) if ap and ap.framework == "cnssi1253" else None
    pend = cur if cur and cur.status != "approved" else None
    return {"approved_trigraph": tri, "approved_revision": ap.revision if ap else None,
            "pending_revision": pend.revision if pend else None, "pending_status": pend.status if pend else None}


def proposal(db: Session, s: System) -> dict | None:
    """Pending change between the applied baseline and the CNSSI 1253 baseline for the system's trigraph (never applied silently).
    kind 'tables_loaded' = an NSS system registered before the tables (same C/I/A); 'categorization_change' = the trigraph changed and
    can only be accepted once that categorization revision is approved."""
    tri = system_trigraph(s)
    if not tri or applied(s) == tri:
        return None
    kind = "tables_loaded" if applied(s) is None else "categorization_change"
    st = approval_state(db, s)
    blocked = None
    if kind == "categorization_change" and st["approved_trigraph"] != tri:
        rev = f" (revision {st['pending_revision']} is {st['pending_status'].replace('_', ' ')})" if st["pending_revision"] else ""
        blocked = f"Approve the categorization revision first{rev} – the AO approves it in 2 · Categorize"
    want = selection(tri)["ids"]
    asg = {a.control_id: a for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == s.id))}
    removed = set(db.scalars(select(TailoringDecision.control_id).where(TailoringDecision.system_id == s.id, TailoringDecision.action == "remove")))
    add = sorted(c for c in want if c not in asg and c not in removed)
    drop = sorted(c for c, a in asg.items() if a.origin == "baseline" and c not in want)
    keep = sorted(_with_work(db, s, set(drop)))
    return {"from": applied(s) or f"NIST SP 800-53B {s.baseline_key or '—'}", "to": tri, "kind": kind, "blocked_reason": blocked,
            "approval_link": "/rmf/categorize", "approved_revision": st["approved_revision"], "add": add, "remove": [c for c in drop if c not in keep],
            "keep_with_work": keep, "tailored_out_kept_out": sorted(want & removed),
            "message": f"CNSSI 1253 baseline loaded – {len(add)} controls added / {len(drop) - len(keep)} removed"
                       f"{f' / {len(keep)} kept (have work)' if keep else ''} – review"}


def accept(db: Session, s: System, actor, expected_to: str) -> dict:
    from app.services.rmf_steps import _add, _finish, _remove

    p = proposal(db, s)
    if p is None or p["to"] != expected_to:
        raise ValueError("The CNSSI 1253 baseline proposal changed or no longer applies – reload and review it again")
    if p["blocked_reason"]:
        raise ValueError(p["blocked_reason"])
    added = _add(db, s, p["add"], "baseline", f"CNSSI 1253 {p['to']}", actor)
    gone = _remove(db, s, p["remove"])
    for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == s.id, ControlAssignment.control_id.in_(p["keep_with_work"]))):
        a.origin, a.origin_detail = "tailored_in", "tailoring"
        db.add(TailoringDecision(system_id=s.id, control_id=a.control_id, action="add", decided_by=actor.id,
                                 justification=f"Kept when the CNSSI 1253 {p['to']} baseline was applied: the control already has statement, evidence or assessment work"))
    for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == s.id, ControlAssignment.origin == "baseline")):
        a.origin_detail = f"CNSSI 1253 {p['to']}"
    s.cnssi_baseline = {"applied": p["to"], "applied_at": datetime.now(timezone.utc).isoformat(), "applied_by": actor.email,
                        "source_sha256": data()["source"]["sha256"], "previous": p["from"]}
    _finish(db, s, actor, "system.cnssi_baseline_applied", {"from": p["from"], "to": p["to"], "kind": p["kind"], "categorization_revision": p["approved_revision"],
                                                           "added": added, "removed": gone,
                                                           "kept_with_work": p["keep_with_work"]})
    return {"added": len(added), "removed": len(gone), "kept_with_work": len(p["keep_with_work"]), "applied": p["to"]}


PRIVACY_OVERLAY = "CNSSI 1253F Privacy Overlay (Attachment 6)"


def privacy_gap(db: Session) -> list[str]:
    """NIST SP 800-53B privacy-baseline controls marked '--' in the Appendix D privacy column (left to the Privacy Overlay)."""
    from app.services.systems import baseline_control_ids

    dash = {r["control_id"] for r in rows() if r["privacy_baseline"] == "--"}
    return sorted(set(baseline_control_ids(db, "privacy")) & dash, key=lambda c: (c.split("-")[0], [int(x) for x in re.findall(r"\d+", c)]))


def privacy_prompt(db: Session, s: System) -> dict | None:
    """NSS + PII yes / unknown → prompt to apply the Privacy Overlay; coverage only as recorded in the overlay data."""
    from app.models import Control, Overlay
    from app.services.content.loader import active_catalog_id

    pii = "yes" if s.processes_pii else "unknown" if (s.pta or {}).get("pii_status") == "unknown" and s.processes_pii is None else None
    if s.categorization_mode != "cnssi1253" or not pii:
        return None
    gap = privacy_gap(db)
    ovs = list(db.scalars(select(Overlay).where(Overlay.group_key == "privacy", Overlay.is_active.is_(True)).order_by(Overlay.overlay_key)))
    applied = next((o for o in ovs if o.overlay_key in (s.overlay_keys or [])), None)
    titles = dict(db.execute(select(Control.control_id, Control.title).where(Control.catalog_version_id == active_catalog_id(db), Control.control_id.in_(gap))).all())

    def cov(o, cid):
        d = (o.details or {}).get(cid)
        return (d.get("detail_page") or True) if cid in (o.controls_add or []) and d and d.get("action") != "remove" else None

    items = []
    for cid in gap:
        pages = {o.variant: cov(o, cid) for o in ovs}
        page = next((p for p in pages.values() if p not in (None, True)), None)
        base = {"control_id": cid, "title": titles.get(cid), "variants": [v for v, p in pages.items() if p]}
        if applied:
            ok = cov(applied, cid)
            base["coverage"] = (f"covered by Privacy Overlay p. {ok}" if ok not in (None, True) else "covered by Privacy Overlay") if ok else \
                f"not covered by the applied Privacy Overlay ({applied.variant}) – SME review"
            base["covered"] = bool(ok)
        else:
            base["coverage"] = (f"covered by Privacy Overlay p. {page}" if page else "covered by Privacy Overlay") if base["variants"] and len(base["variants"]) == len(ovs) else \
                (f"covered only by the {', '.join(base['variants'])} variant(s), p. {page}" if base["variants"] else "not covered by the Privacy Overlay – SME review")
            base["covered"] = bool(base["variants"])
        items.append(base)
    n = len(gap)
    by_variant = {o.variant: sum(1 for c in gap if cov(o, c)) for o in ovs}
    if applied:
        k = sum(1 for i in items if i["covered"])
        return {"state": "applied", "pii": pii, "count": n, "covered": k, "variant": applied.variant, "overlay_key": applied.overlay_key, "items": items,
                "by_variant": by_variant, "message": f"Privacy Overlay applied – {k} of {n} covered"}
    return {"state": "prompt", "pii": pii, "count": n, "items": items, "by_variant": by_variant, "link": "/rmf/select?overlay=privacy",
            "message": f"This system handles PII. CNSSI 1253 leaves {n} NIST privacy-baseline controls to the {PRIVACY_OVERLAY}. "
                       "Apply the Privacy Overlay to select them."}
