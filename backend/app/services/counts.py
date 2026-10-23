"""Single source of truth for every control COUNT shown in the UI (catalog, baselines, system selection, evidence coverage).
Every number carries a label saying what it counts; screens must render these instead of computing their own."""
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ControlAssignment, System
from app.services.content.loader import content_stats
from app.services.evaluation import FRESH_OK

BASELINE_NAME = {"low": "Low", "moderate": "Moderate", "high": "High", "privacy": "Privacy"}


def catalog_counts(db: Session) -> dict:
    s = content_stats(db)
    if not s.get("loaded"):
        return {"loaded": False}
    base, enh, total, wd = s["base_controls"], s["enhancements"], s["controls_total"], s["withdrawn"]
    sel = total - wd
    b = s["baselines"]
    return {"loaded": True, "base_controls": base, "enhancements": enh, "rev5_total": total, "withdrawn": wd, "selectable": sel, "baselines": b,
            "labels": {"rev5_total": f"{base:,} base controls + {enh:,} enhancements = {total:,} in the Rev 5 catalog",
                       "selectable": f"{sel:,} selectable = {total:,} in the catalog − {wd:,} withdrawn",
                       "baselines": {k: f"{v:,} in the {BASELINE_NAME.get(k, k)} baseline (base + enhancements)" for k, v in b.items()}}}


def system_counts(db: Session, system: System) -> dict:
    from app.services.systems import baseline_control_ids

    keys = [system.baseline_key] + (["privacy"] if system.include_privacy else [])
    baseline = set()
    for k in keys:
        baseline |= set(baseline_control_ids(db, k))
    rows = db.execute(select(ControlAssignment.origin, ControlAssignment.evidence_freshness_status).where(ControlAssignment.system_id == system.id)).all()
    by = Counter(o for o, _ in rows)
    assigned = len(rows)
    removed = len(baseline) - by.get("baseline", 0)
    with_ev = sum(1 for _, f in rows if f != "no_evidence")
    current = sum(1 for _, f in rows if f in FRESH_OK)
    bl = " + ".join(BASELINE_NAME.get(k, k) for k in keys)
    return {"baseline_key": system.baseline_key, "baseline": len(baseline), "removed": removed, "overlay_added": by.get("overlay", 0),
            "tailored_in": by.get("tailored_in", 0), "assigned": assigned, "with_evidence": with_ev, "with_current_evidence": current,
            "labels": {"baseline": f"{len(baseline):,} in the {bl} baseline (base + enhancements)",
                       "assigned": f"{assigned:,} assigned after tailoring",
                       "reconciliation": f"{len(baseline):,} baseline − {removed:,} removed (overlay/tailoring) + {by.get('overlay', 0):,} added by overlays"
                                         f" + {by.get('tailored_in', 0):,} tailored in = {assigned:,} assigned",
                       "with_evidence": f"{with_ev:,} of {assigned:,} assigned controls have any evidence",
                       "with_current_evidence": f"{current:,} of {assigned:,} assigned controls have current evidence"}}
