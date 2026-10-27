"""PII at registration: one Yes/No answer. Yes adds the privacy controls straight away (FIPS 199 → SP 800-53B privacy baseline,
CNSSI 1253 → the Privacy Overlay variant matched to the impact level); No adds nothing. Changing the answer adds/removes them via the
existing overlay / baseline paths (statements and evidence are kept; removed controls follow the existing removal rules). Audited."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, ControlAssignment, EvidenceControl, Implementation, Overlay, System, User
from app.services import audit

_SKIP = {"id", "assignment_id", "created_at", "updated_at"}


def _cols(obj, skip=_SKIP) -> dict:
    from sqlalchemy import inspect
    return {c.key: (str(v) if hasattr(v, "hex") and not isinstance(v, (int, float, str, bool)) else v.isoformat() if hasattr(v, "isoformat") else v)
            for c in inspect(obj).mapper.column_attrs if c.key not in skip for v in [getattr(obj, c.key)]}


def _retain(db: Session, s: System, rows: list, actor: User) -> dict:
    """Removing privacy controls deletes their assignments (existing removal rule) – their statements and evidence links are retained
    in an audited archive first and restored (flagged for review) when the controls are re-added. Evidence itself is never deleted."""
    keep = {}
    for a in rows:
        imps = [_cols(i) for i in db.scalars(select(Implementation).where(Implementation.assignment_id == a.id))]
        evs = [_cols(e) for e in db.scalars(select(EvidenceControl).where(EvidenceControl.assignment_id == a.id))]
        if imps or evs:
            keep[a.control_id] = {"implementations": imps, "evidence_links": evs}
    audit.record(db, action="system.privacy_controls_retained", actor_user_id=actor.id, actor_email=actor.email, entity_type="system",
                 entity_id=str(s.id), after={"controls": sorted(a.control_id for a in rows), "retained": keep})
    return keep


def _restore(db: Session, s: System) -> list[str]:
    import uuid as _u
    from datetime import datetime
    ev = db.scalar(select(AuditEvent).where(AuditEvent.entity_type == "system", AuditEvent.entity_id == str(s.id),
                                            AuditEvent.action == "system.privacy_controls_retained").order_by(AuditEvent.created_at.desc()).limit(1))
    if ev is None:
        return []
    have = {a.control_id: a for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == s.id))}
    done = []
    for cid, k in ((ev.after or {}).get("retained") or {}).items():
        a = have.get(cid)
        if a is None:
            continue
        fresh = list(db.scalars(select(Implementation).where(Implementation.assignment_id == a.id)))
        if any((i.narrative or "").strip() for i in fresh):
            continue  # someone already wrote a statement – never overwrite
        for i in fresh:  # the blank placeholder created on re-add gives way to the retained statements
            db.delete(i)
        db.flush()
        for i in k.get("implementations") or []:
            v = {x: y for x, y in i.items() if x not in ("author_id", "ai_interaction_id")}
            db.add(Implementation(assignment_id=a.id, **{**v, "needs_reconsideration": True},
                                  author_id=_u.UUID(i["author_id"]) if i.get("author_id") else None))
        for e in k.get("evidence_links") or []:
            db.add(EvidenceControl(assignment_id=a.id, evidence_id=_u.UUID(e["evidence_id"]), needs_revalidation=True,
                                   revalidation_reason="Restored after the privacy controls were re-added – re-validate",
                                   removed_at=datetime.fromisoformat(e["removed_at"]) if e.get("removed_at") else None))
        done.append(cid)
    return done


def privacy_only_rows(db: Session, s: System) -> list:
    """FIPS: assignments that exist only because of the SP 800-53B privacy baseline (not in the security baseline, not tailored in)."""
    from app.services.rmf_steps import baseline_control_ids
    base = set(baseline_control_ids(db, s.baseline_key)) if s.baseline_key else set()
    priv = set(baseline_control_ids(db, "privacy"))
    return [a for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == s.id))
            if a.control_id in priv and a.control_id not in base and a.origin == "baseline"]


def nss(mode: str | None) -> bool:
    return (mode or "") == "cnssi1253"


def overlay_key_for(level: str | None) -> str:
    return f"cnssi-privacy-{level if level in ('low', 'moderate', 'high') else 'moderate'}"


def target_ids(db: Session, mode: str | None, level: str | None) -> tuple[str, list[str]]:
    from app.services.rmf_steps import baseline_control_ids
    if nss(mode):
        key = overlay_key_for(level)
        ov = db.scalar(select(Overlay).where(Overlay.overlay_key == key, Overlay.is_active.is_(True)).order_by(Overlay.created_at.desc()))
        return key, list((ov.controls_add if ov else None) or [])
    return "privacy_baseline", list(baseline_control_ids(db, "privacy"))


def preview(db: Session, mode: str | None, level: str | None, baseline_key: str | None = None, current_ids: set | None = None,
            trigraph: str | None = None) -> dict:
    """What "Yes" adds: controls not already selected (registration: not in the chosen baseline / NSS trigraph selection; existing system: not assigned)."""
    from app.services import cnssi1253
    from app.services.rmf_steps import baseline_control_ids
    key, ids = target_ids(db, mode, level)
    label = f"the CNSSI 1253 Privacy Overlay ({key.rsplit('-', 1)[-1]} variant)" if nss(mode) else "the SP 800-53B privacy baseline"
    if current_ids is not None:
        have = current_ids
    elif nss(mode) and trigraph:
        have = set(cnssi1253.selection(trigraph)["ids"])
    elif not nss(mode) and baseline_key:
        have = set(baseline_control_ids(db, baseline_key))
    else:
        return {"target": key, "count": None, "label": label, "note": "Select a baseline to see the count."}
    n = len(set(ids) - have)
    return {"target": key, "count": n, "label": label,
            "note": f"Yes adds {'the Privacy Overlay' if nss(mode) else 'the privacy baseline (Privacy Overlay for non-NSS)'} ({n} controls) to this system."}


def display(s: System) -> str:
    """Existing systems (incl. retired PTA answers) map to yes / no / not_answered for display; nothing is migrated."""
    return "yes" if s.processes_pii is True else "no" if s.processes_pii is False else "not_answered"


def applied_key(s: System) -> str | None:
    if nss(s.categorization_mode):
        return next((k for k in (s.overlay_keys or []) if k.startswith("cnssi-privacy")), None)
    return "privacy_baseline" if s.include_privacy else None


def _apply(db: Session, s: System, on: bool, actor: User) -> dict:
    from app.services import rmf_steps as rs
    cur = applied_key(s)
    if on and not cur:
        if nss(s.categorization_mode):
            r = rs.set_overlay(db, s, overlay_key_for(s.categorization), True, actor)
            out = {**r, "added_ids": r.get("applied"), "applied": overlay_key_for(s.categorization)}
        else:
            out = {"applied": "privacy_baseline", **rs.apply_baseline(db, s, s.baseline_key or "moderate", True, actor)}
        db.flush()
        return {**out, "restored_statements": _restore(db, s)}
    if not on and cur:
        if nss(s.categorization_mode):
            rows = list(db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == s.id, ControlAssignment.origin == "overlay",
                                                                   ControlAssignment.origin_detail.like(f"{cur} v%"))))
            kept = _retain(db, s, rows, actor)
            r = rs.set_overlay(db, s, cur, False, actor)
            return {**r, "removed_ids": r.get("removed"), "removed": cur, "retained": sorted(kept)}
        rows = privacy_only_rows(db, s)
        kept = _retain(db, s, rows, actor)
        ids = rs._remove(db, s, [a.control_id for a in rows])
        s.include_privacy = False
        rs._finish(db, s, actor, "system.privacy_baseline_removed", {"removed": ids, "retained": sorted(kept)})
        return {"removed": "privacy_baseline", "removed_ids": ids, "retained": sorted(kept)}
    return {}


def set_pii(db: Session, s: System, value: bool, actor: User, source: str) -> dict:
    before = {"processes_pii": s.processes_pii, "privacy": applied_key(s)}
    s.processes_pii = value
    s.pta = {**(s.pta or {}), "pii_status": "yes" if value else "no", "pii_source": source}
    out = _apply(db, s, value, actor)
    audit.record(db, action="system.pii_answered", actor_user_id=actor.id, actor_email=actor.email, entity_type="system", entity_id=str(s.id),
                 before=before, after={"processes_pii": value, "privacy": applied_key(s), "source": source,
                                       "overlay_change": {k: v for k, v in out.items() if k in ("applied", "removed")}})
    return {"processes_pii": value, "privacy": applied_key(s),
            **{k: v for k, v in out.items() if k in ("applied", "removed", "removed_ids", "retained", "restored_statements")}}
