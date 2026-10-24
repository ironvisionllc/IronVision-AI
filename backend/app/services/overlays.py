"""Official CNSSI 1253 overlays: versioned reference data (parsed from the CNSS PDFs) → one Overlay row per variant;
apply adds/removes controls and sets parameter values; remove reverses exactly that overlay's own changes."""
import json
from functools import lru_cache
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ControlAssignment, OdpValue, Overlay, System, TailoringDecision, User
from app.services import audit

PUBLIC_REF = Path(__file__).parent / "content" / "cnssi1253_overlays.json"

GROUPS = {
    "privacy": {"title": "Privacy Overlays", "kind": "variant",
                "question": "Does the system process PII other than, or in addition to, audit logs or account management records? "
                            "If yes, pick the privacy risk level (Low / Moderate / High) from the privacy risk analysis. If it only holds PII in "
                            "audit logs or account management records, pick Accountability (ACCT).",
                "help": "Two-question approach in Section 4.1. Each control set layers on the one below (ACCT → Low → Moderate → High). "
                        "Privacy Enhancing controls are optional and are tailored in individually. Applies on top of the CNSS Privacy Control Baseline.",
                "variants": [("acct", "Accountability (ACCT)"), ("low", "Low privacy risk"), ("moderate", "Moderate privacy risk"), ("high", "High privacy risk")]},
    "classified": {"title": "Classified System Overlay", "kind": "yesno",
                   "question": "Does the system, by intent and design, store, process, or transmit classified information?",
                   "help": "Section 4. Baseline independent. Does not apply to systems holding classified information only for a limited time "
                           "as a consequence of an information spill.", "variants": [("classified", "Yes – the system handles classified information")]},
    "space": {"title": "Space Platform Overlay", "kind": "yesno",
              "question": "Is this system the space platform (payloads, onboard computing, on-orbit relays) or the link segment interfacing with it, of a space NSS?",
              "help": "Section 1 and 4. Tailors the CNSSI 1253 H/H/H baseline: '+' adds, '--' tailors out. Ground and user segments are out of scope.",
              "variants": [("space", "Yes – space platform / link segment")]},
    "intelligence": {"title": "Intelligence Overlays", "kind": "variant", "restricted": True,
                     "variants": [("int-a", "INT-A"), ("int-b", "INT-B"), ("int-c", "INT-C")]},
    "cds": {"title": "Cross Domain Solution (CDS) Overlays", "kind": "variant", "restricted": True,
            "variants": [("access", "Access CDS"), ("transfer", "Transfer / Multilevel CDS")]},
}
_CNSS = "Committee on National Security Systems (CNSS)"
OVERLAY_META = {  # record metadata shown with each overlay; version/effective date come from the loaded document
    "privacy": {"issuing_authority": _CNSS, "source_document": "CNSSI 1253F Attachment 6 – Privacy Overlays (31 Oct 2024)", "framework": "CNSSI 1253",
                "applicability": "NSS that process PII (Att. 6 §4.1 two-question approach; ACCT defined in Table 1, p. 11). Non-NSS systems use the "
                                 "SP 800-53B privacy baseline instead.", "status": "Authoritative – public"},
    "classified": {"issuing_authority": _CNSS, "source_document": "CNSSI 1253 Appendix E Attachment 5 – Classified System Overlay", "framework": "CNSSI 1253",
                   "applicability": "NSS that by intent and design store, process or transmit classified information (§3, p. 3); explicit answer required.",
                   "status": "Authoritative – public"},
    "space": {"issuing_authority": _CNSS, "source_document": "CNSSI 1253F Attachment 2 – Space Platform Overlay (Aug 2025)", "framework": "CNSSI 1253",
              "applicability": "Space platform / link segment of a space NSS.", "status": "Authoritative – public"},
    "intelligence": {"issuing_authority": _CNSS, "source_document": "CNSSI 1253 Intelligence Overlays (UNCLASSIFIED//FOUO)", "framework": "CNSSI 1253",
                     "applicability": "Intelligence community systems.", "status": "Unavailable – pending validation (restricted document)"},
    "cds": {"issuing_authority": _CNSS, "source_document": "CNSSI 1253 Cross Domain Solution Overlays (UNCLASSIFIED//FOUO)", "framework": "CNSSI 1253",
            "applicability": "Cross domain solutions.", "status": "Unavailable – pending validation (restricted document)"},
}
RESTRICTED_NOTE = ("The official document is marked UNCLASSIFIED//FOUO, so its control list is not shipped with this application. "
                   "A platform administrator can import the derived data file (Select → Overlays → Import official data).")


def key_for(group: str, variant: str) -> str:
    return f"cnssi-{group}" if group == variant else f"cnssi-{group}-{variant}"


@lru_cache
def public_reference() -> dict:
    return json.loads(PUBLIC_REF.read_text())


def load_reference(db: Session, data: dict, actor_email: str | None = None) -> list[str]:
    """Create one active Overlay row per variant from parsed reference data; idempotent per key+version."""
    created = []
    for g, ov in data.get("overlays", {}).items():
        if g not in GROUPS:
            raise ValueError(f"Unknown overlay group {g}")
        doc = ov["document"]
        version = str(doc["date"])[:20]
        for v, label in GROUPS[g]["variants"]:
            key = key_for(g, v)
            if db.scalar(select(Overlay.id).where(Overlay.overlay_key == key, Overlay.version == version)):
                continue
            details, add, rem, optional = {}, [], [], []
            for c in ov["controls"]:
                spec = c["by_variant"].get(v)
                if not spec or not c.get("in_rev5", True):
                    continue
                cid = c["control_id"]
                (add if spec["action"] == "add" else rem if spec["action"] == "remove" else optional if spec["action"] == "optional" else []).append(cid)
                details[cid] = {"action": spec["action"], "flags": spec["flags"], "name": c.get("name"), "source_id": c["source_id"],
                                "summary_page": c["summary_page"], "detail_page": c.get("detail_page"),
                                "fields": [f for f in c.get("fields", []) if not f.get("variants") or v in f["variants"]]}
            db.query(Overlay).filter(Overlay.overlay_key == key).update({"is_active": False})
            db.query(Overlay).filter(Overlay.overlay_key == f"cnssi-{g}", Overlay.structure_only.is_(True)).update({"is_active": False})
            db.add(Overlay(overlay_key=key, version=version, title=f"{GROUPS[g]['title']} – {label}" if GROUPS[g]["kind"] == "variant" else GROUPS[g]["title"],
                           description=f"{doc['title']} ({doc['date']}). Parsed from {doc['file']}.", controls_add=sorted(set(add)), controls_remove=sorted(set(rem)),
                           is_synthetic=False, structure_only=False, group_key=g, variant=v, details=details,
                           source=f"{doc['file']} sha256:{doc['sha256'][:16]}…",
                           provenance={**doc, "applicability": ov.get("applicability"), "optional": sorted(set(optional)), "flagged_ids": ov.get("flagged_ids", []),
                                       "ambiguous": ov.get("ambiguous", []), "loaded_by": actor_email}))
            created.append(key)
    db.flush()
    return created


def ensure_public(db: Session) -> None:
    load_reference(db, public_reference())


def _cite(ov: Overlay, page) -> str:
    return f"{(ov.provenance or {}).get('cite', ov.title)}, p. {page}" if page else (ov.provenance or {}).get("cite", ov.title)


def _active(db: Session, key: str) -> Overlay | None:
    return db.scalar(select(Overlay).where(Overlay.overlay_key == key, Overlay.is_active.is_(True)).order_by(Overlay.created_at.desc()))


def _param_rows(ov: Overlay):
    for cid, d in (ov.details or {}).items():
        for f in d.get("fields", []):
            if "Parameter" in f["label"]:
                yield cid, f


def apply(db: Session, s: System, ov: Overlay, actor: User, add_fn) -> dict:
    keys = list(s.overlay_keys or [])
    for other in [k for k in keys if k != ov.overlay_key]:
        o = _active(db, other)
        if o is not None and o.group_key and o.group_key == ov.group_key:
            remove(db, s, o, actor)
            keys = list(s.overlay_keys or [])
    added = add_fn(db, s, list(ov.controls_add), "overlay", f"{ov.overlay_key} v{ov.version}", actor)
    have = {a.control_id: a for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == s.id))}
    removed = []
    for cid in ov.controls_remove:
        a = have.get(cid)
        if a is None:
            continue
        page = (ov.details or {}).get(cid, {}).get("summary_page")
        db.add(TailoringDecision(system_id=s.id, control_id=cid, action="remove", decided_by=actor.id, overlay_key=ov.overlay_key,
                                 prior_origin=a.origin, prior_origin_detail=a.origin_detail,
                                 justification=f"Removed by {ov.title} ({_cite(ov, page)})"))
        db.delete(a)
        removed.append(cid)
    db.flush()
    assigned = set(db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == s.id)))
    params = 0
    for cid, f in _param_rows(ov):
        if cid in assigned:
            db.add(OdpValue(system_id=s.id, control_id=cid, parameter=f"overlay:{ov.overlay_key}", value=f["text"][:255],
                            source=f"{ov.title} ({_cite(ov, f.get('page'))})"))
            params += 1
    s.overlay_keys = sorted(set(keys + [ov.overlay_key]))
    return {"added": added, "removed": sorted(removed), "parameters_set": params}


def remove(db: Session, s: System, ov: Overlay, actor: User) -> dict:
    key = ov.overlay_key
    others = [o for o in (_active(db, k) for k in (s.overlay_keys or []) if k != key) if o is not None]
    rows = db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == s.id, ControlAssignment.origin == "overlay",
                                                      ControlAssignment.origin_detail.like(f"{key} v%"))).all()
    dropped, kept = [], []
    for a in rows:
        heir = next((o for o in others if a.control_id in (o.controls_add or [])), None)
        if heir is not None:
            a.origin_detail = f"{heir.overlay_key} v{heir.version}"
            kept.append(a.control_id)
        else:
            db.delete(a)
            dropped.append(a.control_id)
    restored = []
    decisions = db.scalars(select(TailoringDecision).where(TailoringDecision.system_id == s.id, TailoringDecision.overlay_key == key)).all()
    db.query(OdpValue).filter(OdpValue.system_id == s.id, OdpValue.parameter == f"overlay:{key}").delete(synchronize_session=False)
    db.flush()
    from app.services.rmf_steps import _add

    for d in decisions:
        if d.action == "remove":
            restored += _add(db, s, [d.control_id], d.prior_origin or "baseline", d.prior_origin_detail or s.baseline_key, actor)
        db.delete(d)
    s.overlay_keys = [k for k in (s.overlay_keys or []) if k != key]
    return {"added": [], "removed": sorted(dropped), "restored": sorted(restored), "handed_over": sorted(kept)}


def groups_view(db: Session, s: System) -> list[dict]:
    applied = set(s.overlay_keys or [])
    out = []
    for g, meta in GROUPS.items():
        variants, doc, appl = [], None, None
        for v, label in meta["variants"]:
            o = _active(db, key_for(g, v))
            if o is None or o.structure_only:
                continue
            doc = doc or {k: (o.provenance or {}).get(k) for k in ("title", "file", "sha256", "date", "marking", "cite", "pdf_pages")}
            appl = appl or (o.provenance or {}).get("applicability")
            variants.append({"key": o.overlay_key, "variant": v, "label": label, "version": o.version, "add": len(o.controls_add),
                             "remove": len(o.controls_remove), "optional": len((o.provenance or {}).get("optional", [])),
                             "guidance_only": sum(1 for d in (o.details or {}).values() if d["action"] in ("guidance", "baseline", "consideration")),
                             "parameters": sum(1 for _ in _param_rows(o)), "applied": o.overlay_key in applied})
        restricted = bool(meta.get("restricted"))
        out.append({"group": g, "title": meta["title"], "kind": meta["kind"], "loaded": bool(variants), "restricted": restricted,
                    "question": meta.get("question") or (appl or {}).get("question"), "help": meta.get("help") or (appl or {}).get("help"),
                    "note": RESTRICTED_NOTE if restricted and not variants else None, "document": doc, "variants": variants,
                    "applied_key": next((x["key"] for x in variants if x["applied"]), None)})
    return out


def overlay_controls(db: Session, s: System, key: str) -> dict:
    ov = _active(db, key)
    if ov is None or ov.structure_only:
        raise ValueError("Unknown overlay")
    assigned = {a.control_id: a for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == s.id))}
    removed = set(db.scalars(select(TailoringDecision.control_id).where(TailoringDecision.system_id == s.id, TailoringDecision.overlay_key == key)))
    verb = {"add": "Added by", "remove": "Removed by", "optional": "Optional (Privacy Enhancing) in", "guidance": "Guidance from",
            "baseline": "Baseline control with guidance in", "consideration": "Implementation consideration in"}
    rows = []
    for cid, d in sorted((ov.details or {}).items()):
        page = d.get("detail_page") or d.get("summary_page")
        a = assigned.get(cid)
        rows.append({"control_id": cid, "name": d.get("name"), "action": d["action"], "flags": d["flags"],
                     "label": f"{verb.get(d['action'], 'In')} {ov.title} ({_cite(ov, page)})", "summary_page": d.get("summary_page"),
                     "detail_page": d.get("detail_page"), "assigned": a is not None, "removed_by_overlay": cid in removed,
                     "added_by_this": bool(a and a.origin == "overlay" and (a.origin_detail or "").startswith(f"{key} v")), "fields": d.get("fields", [])})
    return {"key": key, "title": ov.title, "version": ov.version, "applied": key in (s.overlay_keys or []), "document": ov.provenance, "controls": rows}


def control_notes(db: Session, s: System, control_id: str) -> list[dict]:
    out = []
    for k in s.overlay_keys or []:
        o = _active(db, k)
        d = (o.details or {}).get(control_id) if o else None
        if d:
            page = d.get("detail_page") or d.get("summary_page")
            out.append({"overlay": o.title, "key": k, "action": d["action"], "flags": d["flags"], "cite": _cite(o, page), "fields": d.get("fields", [])})
    return out


def record_import(db: Session, actor: User, created: list[str], source: str) -> None:
    audit.record(db, action="overlay.reference_imported", actor_user_id=actor.id, actor_email=actor.email, entity_type="overlay",
                 entity_id=",".join(created)[:200] or "none", after={"created": created, "source": source})
