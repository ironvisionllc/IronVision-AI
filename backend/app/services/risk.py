"""Operational prioritization score for findings (configurable weights in priority_weights, codes rf_*).

score = Σ weight_i × factor_i, where each factor is in [0, 1]. Every factor and its points are returned so the explanation
always adds up to the total. This is an operational prioritization score, not a formal residual risk determination.
"""
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Asset, Evidence, Finding, PriorityWeight, System

LABEL = "Operational prioritization score – not a formal residual risk determination"
DEFAULT_WEIGHTS = {
    "rf_severity": (40, "Severity / CAT: CAT I=1.0, CAT II=0.5, CAT III=0.2, none=0.1"),
    "rf_kev": (25, "On the active CISA KEV catalog version = 1.0"),
    "rf_epss": (10, "EPSS probability (0–1); EPSS is not loaded in this build, so this factor is 0"),
    "rf_asset_criticality": (10, "Asset criticality: high=1.0, moderate=0.5, low=0.2, unknown=0.5"),
    "rf_mission_criticality": (5, "System mission criticality: mission critical=1.0, mission essential=0.6, other=0.3"),
    "rf_exposure": (10, "Network zone: internet/DMZ=1.0, internal=0.4, restricted/management=0.2, unknown=0.5"),
    "rf_remediation_age": (10, "Days open ÷ 180 (capped at 1.0)"),
    "rf_authorization_status": (5, "Authorization: expired/denied/none=1.0, in assessment=0.7, authorized=0.2"),
    "rf_evidence_confidence": (5, "Evidence confidence gap: integrity verified=0, hash recorded=0.3, unverified/none=1.0"),
}


def weights(db: Session) -> dict[str, int]:
    return {w.reason_code: w.weight for w in db.scalars(select(PriorityWeight).where(PriorityWeight.reason_code.like("rf_%")))}


def _sev(f: Finding) -> tuple[float, str]:
    cat = f.cat or {"critical": "CAT I", "high": "CAT I", "medium": "CAT II", "low": "CAT III"}.get((f.severity or "").lower())
    return {"CAT I": 1.0, "CAT II": 0.5, "CAT III": 0.2}.get(cat, 0.1), cat or "none"


def _zone(z: str | None) -> float:
    z = (z or "").lower()
    if any(k in z for k in ("internet", "dmz", "public")):
        return 1.0
    if any(k in z for k in ("restricted", "mgmt", "management", "enclave")):
        return 0.2
    return 0.4 if z else 0.5


def _auth(s: System) -> float:
    st = (s.authorization_status or "").lower()
    if st.startswith("authorized") and (s.authorization_expiration is None or s.authorization_expiration >= date.today()):
        return 0.2
    return 0.7 if "assessment" in st else 1.0


def score(db: Session, f: Finding, w: dict, system: System, asset: Asset | None, ev: Evidence | None) -> tuple[float, list[dict]]:
    sev, cat = _sev(f)
    crit = (asset.criticality or "").lower() if asset else ""
    mission = (system.mission_criticality or "").lower()
    age = (datetime.now(timezone.utc) - f.first_seen_at).days if f.first_seen_at else 0
    integ = ev.integrity_status if ev else None
    factors = [
        ("rf_severity", sev, cat),
        ("rf_kev", 1.0 if f.is_kev else 0.0, "KEV" if f.is_kev else "not on KEV"),
        ("rf_epss", 0.0, "not loaded"),
        ("rf_asset_criticality", {"high": 1.0, "moderate": 0.5, "medium": 0.5, "low": 0.2}.get(crit, 0.5), crit or "unknown"),
        ("rf_mission_criticality", 1.0 if "critical" in mission else 0.6 if "essential" in mission else 0.3, system.mission_criticality or "unset"),
        ("rf_exposure", _zone(asset.network_zone if asset else None), (asset.network_zone if asset else None) or "unknown"),
        ("rf_remediation_age", min(age / 180, 1.0), f"{age} days open"),
        ("rf_authorization_status", _auth(system), system.authorization_status),
        ("rf_evidence_confidence", {"verified": 0.0, "hash_recorded": 0.3}.get(integ or "", 1.0), integ or "no evidence"),
    ]
    out = [{"factor": k, "weight": w.get(k, 0), "value": round(v, 3), "points": round(w.get(k, 0) * v, 1), "basis": b} for k, v, b in factors]
    return round(sum(x["points"] for x in out), 1), out


def recompute(db: Session, system_id=None) -> int:
    w = weights(db)
    q = select(Finding).where(Finding.system_id == system_id) if system_id else select(Finding)
    systems, assets, n = {}, {}, 0
    for f in db.scalars(q):
        s = systems.get(f.system_id) or systems.setdefault(f.system_id, db.get(System, f.system_id))
        a = None
        if f.asset_id:
            a = assets.get(f.asset_id) or assets.setdefault(f.asset_id, db.get(Asset, f.asset_id))
        ev = db.get(Evidence, f.latest_evidence_id) if f.latest_evidence_id else None
        f.priority_score, f.priority_breakdown = score(db, f, w, s, a, ev)
        n += 1
    db.flush()
    return n
