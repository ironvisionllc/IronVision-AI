"""Single source of truth for every control COUNT shown in the UI (catalog, baselines, system selection, evidence coverage).
Every number carries a label saying what it counts; screens must render these instead of computing their own."""
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ControlAssignment, System, TailoringDecision
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
    from app.services import cnssi1253
    from app.services.systems import baseline_control_ids

    tri = cnssi1253.applied(system)
    keys = [system.baseline_key] + (["privacy"] if system.include_privacy else [])
    baseline = set()
    if tri:
        sel = cnssi1253.selection(tri)
        baseline = set(sel["ids"])
    else:
        for k in keys:
            baseline |= set(baseline_control_ids(db, k))
    rows = db.execute(select(ControlAssignment.origin, ControlAssignment.evidence_freshness_status).where(ControlAssignment.system_id == system.id)).all()
    by = Counter(o for o, _ in rows)
    assigned = len(rows)
    removed = len(baseline) - by.get("baseline", 0)
    have = set(db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == system.id)))
    ov_removed = len({c for c in db.scalars(select(TailoringDecision.control_id).where(
        TailoringDecision.system_id == system.id, TailoringDecision.action == "remove", TailoringDecision.overlay_key.is_not(None)))
        if c in baseline and c not in have})
    tailored_out = removed - ov_removed
    with_ev = sum(1 for _, f in rows if f != "no_evidence")
    current = sum(1 for _, f in rows if f in FRESH_OK)
    bl = " + ".join(BASELINE_NAME.get(k, k) for k in keys)
    oa, ti = by.get("overlay", 0), by.get("tailored_in", 0)
    bl_label = f"{len(baseline):,} in the {bl} baseline (base + enhancements)"
    head = f"{len(baseline):,} baseline"
    cn = None
    if tri:
        b = sel["by"]
        cn = {"trigraph": tri, "c": len(b["c"]), "i": len(b["i"]), "a": len(b["a"]), "security_union": sel["security_union"],
              "privacy_baseline": len(b["privacy"]), "union": len(baseline)}
        bl_label = (f"CNSSI 1253 baseline for {tri}: {len(baseline):,} (C: {cn['c']:,}, I: {cn['i']:,}, A: {cn['a']:,}, union {cn['security_union']:,}"
                    f" + NSS privacy control baseline {cn['privacy_baseline']:,} → {len(baseline):,})")
        head = bl_label
    return {"baseline_key": system.baseline_key, "baseline": len(baseline), "removed": removed, "overlay_added": oa, "overlay_removed": ov_removed,
            "tailored_out": tailored_out, "tailored_in": ti, "assigned": assigned, "with_evidence": with_ev, "with_current_evidence": current,
            "cnssi": cn,
            "labels": {"baseline": bl_label,
                       "assigned": f"{assigned:,} assigned after tailoring",
                       "reconciliation": f"{head} + {oa:,} added by overlays − {ov_removed:,} removed by overlays"
                                         f" − {tailored_out:,} tailored out + {ti:,} tailored in = {assigned:,} assigned",
                       "with_evidence": f"{with_ev:,} of {assigned:,} assigned controls have any evidence",
                       "with_current_evidence": f"{current:,} of {assigned:,} assigned controls have current evidence"}}
