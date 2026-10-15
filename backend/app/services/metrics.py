"""Single source of truth for every dashboard number (Controls, RMF Workflow, POA&M, eMASS Sync, Evidence Sources, Leadership)."""
import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (ApprovalRequest, ControlAssignment, EmassChange, EmassRemoteRecord, EmassSyncRun, Evidence, EvidenceSource, Finding,
                        IngestRun, Poam, PriorityWeight, System)
from app.services.evaluation import FRESH_OK, OP_WEIGHTS, STALE, open_findings_q

DEFINITIONS = {
    "evidence_items_fresh_pct": "% of collected evidence items within their freshness window (current or near expiration). Superseded items are excluded.",
    "controls_with_current_evidence": "Assigned controls whose newest supporting evidence for every covered asset is current or near expiration.",
    "control_evidence_coverage_pct": "Controls with current supporting evidence ÷ assigned controls.",
    "pending_emass_sync": "POA&Ms whose eMASS state is not sent, out of sync, queued, conflict or failed/retrying (derived from the outbound queue + sync history).",
    "results_vs_findings": "Results = every record a source produced (checks, config snapshots, findings). Findings (failed) = open failing findings.",
}
QUEUED = ("proposed", "pending_approval", "approved", "submitting")
PENDING_EMASS = ("not_sent", "out_of_sync", "queued", "retrying", "conflict", "failed")
EMASS_LABEL = {"not_sent": "not sent", "out_of_sync": "out of sync", "queued": "queued", "retrying": "failed – retrying", "conflict": "conflict",
               "failed": "failed", "synced": "synced"}


def _emass_state(p: Poam, ch: EmassChange | None, remote: EmassRemoteRecord | None) -> str:
    if ch is None:
        return "not_sent"
    if ch.status in QUEUED:
        return "queued"
    if ch.status == "pending_retry":
        return "retrying"
    if ch.status in ("conflict", "failed"):
        return ch.status
    synced_version = (ch.response or {}).get("remote_version")
    if remote is not None and synced_version is not None and remote.remote_version > synced_version:
        return "out_of_sync"
    if ch.submitted_at and p.updated_at and p.updated_at > ch.submitted_at + timedelta(seconds=5):
        return "out_of_sync"
    return "synced"


def emass_states(db: Session, poams: list[Poam]) -> dict[uuid.UUID, dict]:
    """eMASS state per POA&M, derived ONLY from emass_changes (queue + sync history) and the remote record version."""
    if not poams:
        return {}
    latest: dict[str, EmassChange] = {}
    for ch in db.scalars(select(EmassChange).where(EmassChange.entity_type == "poam", EmassChange.entity_id.in_([str(p.id) for p in poams]),
                                                   EmassChange.status != "cancelled").order_by(EmassChange.created_at)):
        latest[ch.entity_id] = ch
    rids = [c.remote_id for c in latest.values() if c.remote_id]
    remote = {(r.system_id, r.remote_id): r for r in db.scalars(select(EmassRemoteRecord).where(EmassRemoteRecord.entity_type == "poam",
                                                                                                 EmassRemoteRecord.remote_id.in_(rids)))} if rids else {}
    out = {}
    for p in poams:
        ch = latest.get(str(p.id))
        st = _emass_state(p, ch, remote.get((p.system_id, ch.remote_id)) if ch and ch.remote_id else None)
        out[p.id] = {"state": st, "label": EMASS_LABEL[st], "remote_id": ch.remote_id if ch and st != "not_sent" else None,
                     "last_synced_at": ch.submitted_at if ch and ch.status == "succeeded" else None, "pending": st in PENDING_EMASS}
    return out


def last_emass_sync(db: Session, org_id, system_id=None):
    q = select(func.max(EmassSyncRun.created_at)).where(EmassSyncRun.org_id == org_id, EmassSyncRun.status == "succeeded")
    if system_id:
        q = q.where(EmassSyncRun.system_id == system_id)
    return db.scalar(q)


def poam_summary(db: Session, system_ids: list) -> dict:
    from app.services.workflow import ACTIVE_POAM

    today = date.today()
    poams = list(db.scalars(select(Poam).where(Poam.system_id.in_(system_ids))))
    active = [p for p in poams if p.status in ACTIVE_POAM]
    states = emass_states(db, poams)
    return {"open": len(active), "overdue": sum(1 for p in active if p.status in ("new", "in_progress") and p.due_date and p.due_date < today),
            "due_30d": sum(1 for p in active if p.due_date and today <= p.due_date <= today + timedelta(days=30)),
            "cat1": sum(1 for p in active if p.cat == "CAT I"),
            "pending_issm_review": db.scalar(select(func.count()).select_from(ApprovalRequest).where(
                ApprovalRequest.system_id.in_(system_ids), ApprovalRequest.status == "pending", ApprovalRequest.assigned_role == "issm",
                ApprovalRequest.poam_id.is_not(None))) if system_ids else 0,
            "pending_emass_sync": sum(1 for v in states.values() if v["pending"]),
            "emass_by_state": {k: sum(1 for v in states.values() if v["state"] == k) for k in EMASS_LABEL},
            "definitions": {"pending_emass_sync": DEFINITIONS["pending_emass_sync"]}}


def source_counts(db: Session, s: EvidenceSource) -> dict:
    ev_ids = select(Evidence.id).where(Evidence.source_id == s.id)
    fq = select(func.count(func.distinct(Finding.id))).select_from(Finding).where(Finding.latest_evidence_id.in_(ev_ids))
    latest = db.scalar(select(IngestRun).where(IngestRun.source_id == s.id, IngestRun.status == "completed").order_by(IngestRun.received_at.desc()).limit(1))
    total = db.scalar(fq)
    mapped = db.scalar(fq.where(Finding.mapping_status == "mapped"))
    return {"results_latest_run": latest.total if latest else 0, "results_all_runs": db.scalar(select(func.coalesce(func.sum(IngestRun.total), 0))
                                                                                                 .where(IngestRun.source_id == s.id, IngestRun.status == "completed")),
            "findings_total": total, "findings_open": db.scalar(fq.where(Finding.current_state == "open")),
            "findings_passing": db.scalar(fq.where(Finding.current_state.in_(("pass", "not_applicable")))),
            # unmapped includes dispositioned (UI: "unmapped incl. N dispositioned") so Mapped + Unmapped = Total always holds
            "mapped": mapped, "unmapped": db.scalar(fq.where(Finding.mapping_status != "mapped")),
            "dispositioned": db.scalar(fq.where(Finding.mapping_status == "dispositioned")),
            "assets": db.scalar(select(func.count(func.distinct(Finding.asset_id))).where(Finding.latest_evidence_id.in_(ev_ids)))}


def system_metrics(db: Session, system: System) -> dict:
    sid = system.id
    fq = select(func.count()).select_from(ControlAssignment).where(ControlAssignment.system_id == sid)
    assigned = db.scalar(fq)
    open_q = open_findings_q(sid)
    evq = select(func.count()).select_from(Evidence).where(Evidence.system_id == sid, Evidence.state != "superseded")
    ev_total, ev_fresh = db.scalar(evq), db.scalar(evq.where(Evidence.state.in_(FRESH_OK)))
    with_ev = db.scalar(fq.where(ControlAssignment.evidence_freshness_status != "no_evidence"))
    fresh_ctl = db.scalar(fq.where(ControlAssignment.evidence_freshness_status.in_(FRESH_OK)))
    stale_ctl = db.scalar(fq.where(ControlAssignment.evidence_freshness_status.in_(STALE + ("partially_stale",))))
    ps = poam_summary(db, [sid])
    today, exp = date.today(), system.authorization_expiration
    m = {
        "assigned_controls": assigned,
        "open_findings": db.scalar(open_q),
        "open_cat1": db.scalar(open_q.where(Finding.cat == "CAT I")),
        "kev_open": db.scalar(open_q.where(Finding.is_kev.is_(True))),
        "unmapped_findings": db.scalar(select(func.count()).select_from(Finding).where(Finding.system_id == sid, Finding.mapping_status == "unmapped",
                                                                                      Finding.current_state == "open")),
        "monitoring_failing": db.scalar(fq.where(ControlAssignment.monitoring_status == "failing")),
        "evidence_total": ev_total,
        "evidence_items_fresh": ev_fresh,
        "evidence_items_fresh_pct": round(100 * ev_fresh / ev_total, 1) if ev_total else None,
        "controls_with_evidence": with_ev,
        "controls_with_current_evidence": fresh_ctl,
        "controls_fresh": fresh_ctl,
        "controls_stale": stale_ctl,
        "control_evidence_coverage_pct": round(100 * fresh_ctl / assigned, 1) if assigned else None,
        "evidence_fresh_pct": round(100 * fresh_ctl / assigned, 1) if assigned else None,
        "authorization_status": system.authorization_status,
        "days_to_expiration": (exp - today).days if exp else None,
        "open_poams": ps["open"], "overdue_poams": ps["overdue"], "poams_due_30d": ps["due_30d"], "pending_emass_sync": ps["pending_emass_sync"],
        "risk_acceptances": db.scalar(select(func.count()).select_from(Poam).where(Poam.system_id == sid, Poam.status == "risk_accepted")),
        "pending_risk_decisions": db.scalar(select(func.count()).select_from(ApprovalRequest).where(
            ApprovalRequest.system_id == sid, ApprovalRequest.status == "pending",
            ApprovalRequest.request_type.in_(("risk_acceptance", "waiver_extension", "deadline_extension")))),
        "definitions": DEFINITIONS,
    }
    weights = {w.reason_code: w.weight for w in db.scalars(select(PriorityWeight).where(PriorityWeight.reason_code.like("sys_%")))}
    parts = {"sys_cat1": m["open_cat1"], "sys_kev": m["kev_open"], "sys_overdue_poam": m["overdue_poams"], "sys_stale_controls": (stale_ctl or 0) // 5,
             "sys_auth_expiring": 1 if m["days_to_expiration"] is not None and m["days_to_expiration"] <= 90 else 0,
             "sys_pending_risk": m["pending_risk_decisions"]}
    m["op_score_breakdown"] = [{"code": k, "count": v, "weight": weights.get(k, OP_WEIGHTS[k][0]), "points": v * weights.get(k, OP_WEIGHTS[k][0]),
                                "description": OP_WEIGHTS[k][1]} for k, v in parts.items() if v]
    m["op_score"] = sum(x["points"] for x in m["op_score_breakdown"])
    return m
