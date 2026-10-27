"""PII at registration: one Yes/No answer. Yes adds the privacy controls straight away (FIPS 199 → SP 800-53B privacy baseline,
CNSSI 1253 → the Privacy Overlay variant matched to the impact level); No adds nothing. Changing the answer adds/removes them via the
existing overlay / baseline paths (statements and evidence are kept; removed controls follow the existing removal rules). Audited."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Overlay, System, User
from app.services import audit


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


def preview(db: Session, mode: str | None, level: str | None, baseline_key: str | None = None, current_ids: set | None = None) -> dict:
    """What "Yes" adds: controls not already selected (registration: not in the chosen baseline; existing system: not assigned)."""
    from app.services.rmf_steps import baseline_control_ids
    key, ids = target_ids(db, mode, level)
    have = current_ids if current_ids is not None else (set(baseline_control_ids(db, baseline_key)) if baseline_key else set())
    n = len(set(ids) - have)
    label = f"the CNSSI 1253 Privacy Overlay ({key.rsplit('-', 1)[-1]} variant)" if nss(mode) else "the SP 800-53B privacy baseline"
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
            return {"applied": overlay_key_for(s.categorization), **rs.set_overlay(db, s, overlay_key_for(s.categorization), True, actor)}
        return {"applied": "privacy_baseline", **rs.apply_baseline(db, s, s.baseline_key or "moderate", True, actor)}
    if not on and cur:
        if nss(s.categorization_mode):
            return {"removed": cur, **rs.set_overlay(db, s, cur, False, actor)}
        return {"removed": "privacy_baseline", **rs.apply_baseline(db, s, s.baseline_key or "moderate", False, actor)}
    return {}


def set_pii(db: Session, s: System, value: bool, actor: User, source: str) -> dict:
    before = {"processes_pii": s.processes_pii, "privacy": applied_key(s)}
    s.processes_pii = value
    s.pta = {**(s.pta or {}), "pii_status": "yes" if value else "no", "pii_source": source}
    out = _apply(db, s, value, actor)
    audit.record(db, action="system.pii_answered", actor_user_id=actor.id, actor_email=actor.email, entity_type="system", entity_id=str(s.id),
                 before=before, after={"processes_pii": value, "privacy": applied_key(s), "source": source,
                                       "overlay_change": {k: v for k, v in out.items() if k in ("applied", "removed")}})
    return {"processes_pii": value, "privacy": applied_key(s), **{k: v for k, v in out.items() if k in ("applied", "removed")}}
