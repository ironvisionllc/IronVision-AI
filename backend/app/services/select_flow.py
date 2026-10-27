"""Select step (SP 800-37 Tasks S-1..S-4, S-6): dry-run previews that reuse the real services inside a rolled-back SAVEPOINT,
the original-vs-final selection diff, and "submit selection for approval" through the existing reviews workflow."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ApprovalRequest, ControlAssignment, EvidenceControl, Implementation, OdpValue, System, TailoringDecision
from app.services.counts import system_counts

APPLICABILITY = ("Applicable", "Not Applicable", "Compensating control")


def _state(db: Session, s: System) -> dict:
    rows = db.execute(select(ControlAssignment.control_id, ControlAssignment.origin).where(ControlAssignment.system_id == s.id)).all()
    odps = {(o.control_id, o.parameter): o.value for o in db.scalars(select(OdpValue).where(OdpValue.system_id == s.id))}
    return {"ids": {c: o for c, o in rows}, "odps": odps, "overlays": list(s.overlay_keys or []), "counts": system_counts(db, s)}


def losses(db: Session, s: System, ids: list[str]) -> dict:
    """What a removal would delete (shown in previews – no silent removals)."""
    if not ids:
        return {"statements": 0, "evidence_links": 0}
    aids = list(db.scalars(select(ControlAssignment.id).where(ControlAssignment.system_id == s.id, ControlAssignment.control_id.in_(ids))))
    st = db.scalar(select(func.count()).select_from(Implementation).where(Implementation.assignment_id.in_(aids), Implementation.narrative != "")) or 0
    ev = db.scalar(select(func.count()).select_from(EvidenceControl).where(EvidenceControl.assignment_id.in_(aids), EvidenceControl.removed_at.is_(None))) or 0
    return {"statements": st, "evidence_links": ev}


def dry_run(db: Session, s: System, fn, *args) -> dict:
    before = _state(db, s)
    sp = db.begin_nested()
    try:
        result = fn(db, s, *args)
        db.flush()
        after = _state(db, s)
    finally:
        sp.rollback()
        db.expire_all()
    removed = sorted(set(before["ids"]) - set(after["ids"]))
    changed_odps = sorted({f"{c}: {p}" for (c, p), v in after["odps"].items() if before["odps"].get((c, p)) != v}
                          | {f"{c}: {p}" for (c, p) in before["odps"] if (c, p) not in after["odps"]})
    return {"dry_run": True, "nothing_saved": True, "added": sorted(set(after["ids"]) - set(before["ids"])), "removed": removed,
            "parameters_changed": changed_odps, "would_delete": losses(db, s, removed),
            "counts_before": before["counts"], "counts_after": after["counts"],
            "result": {k: v for k, v in (result or {}).items() if k not in ("added_ids",)}}


def original_ids(db: Session, s: System) -> set[str]:
    from app.services import cnssi1253
    from app.services.systems import baseline_control_ids
    tri = cnssi1253.applied(s)
    if tri:
        return set(cnssi1253.selection(tri)["ids"])
    out = set()
    for k in [s.baseline_key] + (["privacy"] if s.include_privacy else []):
        if k:
            out |= set(baseline_control_ids(db, k))
    return out


def review(db: Session, s: System, select_view: dict) -> dict:
    """Step 5 – original baseline vs final selection, counts, what still needs a decision, approval status."""
    orig = original_ids(db, s)
    rows = {c: (o, d) for c, o, d in db.execute(select(ControlAssignment.control_id, ControlAssignment.origin, ControlAssignment.origin_detail)
                                                .where(ControlAssignment.system_id == s.id))}
    tds = list(db.scalars(select(TailoringDecision).where(TailoringDecision.system_id == s.id).order_by(TailoringDecision.created_at)))
    removed = sorted(orig - set(rows))
    why = {}
    for t in tds:
        why[t.control_id] = {"by": f"overlay {t.overlay_key}" if t.overlay_key else "tailoring", "action": t.action, "justification": t.justification,
                             "applicability": t.applicability, "compensating_control_id": t.compensating_control_id}
    added = sorted(c for c in rows if c not in orig)
    odp = db.scalar(select(func.count()).select_from(OdpValue).where(OdpValue.system_id == s.id)) or 0
    needs = []
    cn = select_view.get("cnssi") or {}
    if (cn.get("proposal") or {}).get("blocked_reason"):
        needs.append({"item": "CNSSI 1253 baseline proposal", "why": cn["proposal"]["blocked_reason"], "step": 2})
    if (select_view.get("privacy_prompt") or {}).get("show"):
        needs.append({"item": "Privacy overlay question", "why": "Answer whether the privacy overlay applies", "step": 3})
    if not s.baseline_key and not cn.get("applied"):
        needs.append({"item": "Initial baseline", "why": "No baseline applied yet", "step": 2})
    no_just = [c for c in removed if not (why.get(c) or {}).get("justification")]
    if no_just:
        needs.append({"item": f"{len(no_just)} removed control(s) without a recorded rationale", "why": ", ".join(c.upper() for c in no_just[:10]), "step": 4})
    req = db.scalar(select(ApprovalRequest).where(ApprovalRequest.system_id == s.id, ApprovalRequest.request_type == "selection_review")
                    .order_by(ApprovalRequest.created_at.desc()).limit(1))
    return {"original": {"count": len(orig), "source": select_view["counts"]["labels"]["baseline"]},
            "final": {"count": len(rows)},
            "added": [{"control_id": c, "origin": rows[c][0], "detail": rows[c][1], **({"decision": why[c]} if c in why else {})} for c in added],
            "removed": [{"control_id": c, "decision": why.get(c)} for c in removed],
            "counts": {"added_by_overlays": sum(1 for c in added if rows[c][0] == "overlay"), "tailored_in": sum(1 for c in added if rows[c][0] == "tailored_in"),
                       "removed_by_overlays": sum(1 for c in removed if (why.get(c) or {}).get("by", "").startswith("overlay")),
                       "tailored_out": sum(1 for c in removed if (why.get(c) or {}).get("by") == "tailoring" or c not in why),
                       "parameters_set": odp, "overlays_applied": len(s.overlay_keys or [])},
            "reconciliation": select_view["counts"]["labels"]["reconciliation"], "needs_decision": needs,
            "approval": None if not req else {"id": str(req.id), "human_id": req.human_id, "status": req.status, "assigned_role": req.assigned_role,
                                              "created_at": req.created_at.isoformat()}}


def submit(db: Session, s: System, actor, justification: str, snapshot: dict) -> ApprovalRequest:
    from fastapi import HTTPException
    from app.services import workflow
    if db.scalar(select(ApprovalRequest.id).where(ApprovalRequest.system_id == s.id, ApprovalRequest.request_type == "selection_review",
                                                  ApprovalRequest.status == "pending")):
        raise HTTPException(409, "A control selection review is already pending")
    return workflow.create_request(db, system=s, requester=actor, request_type="selection_review", justification=justification,
                                   payload={"final_count": snapshot["final"]["count"], "original_count": snapshot["original"]["count"],
                                            "counts": snapshot["counts"], "overlays": list(s.overlay_keys or []), "baseline_key": s.baseline_key,
                                            "framework": s.categorization_mode})
