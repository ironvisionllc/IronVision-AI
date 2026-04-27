"""
Dynamic Risk Scoring Engine
- Combines SIEM events, ingested checklist status, pipeline scan results, and policy coverage gaps
- Real-time risk score per framework, per control family, and org-wide
- Continuous compliance monitoring with threshold alerts and trend tracking
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List
from datetime import datetime, timezone, timedelta
import logging

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/risk-scoring", tags=["risk-scoring"])


# Risk factor weights (configurable)
RISK_WEIGHTS = {
    "siem_critical": 15,
    "siem_high": 8,
    "siem_medium": 3,
    "unmapped_control_high": 10,
    "unmapped_control_medium": 5,
    "unmapped_control_low": 2,
    "non_compliant_control": 12,
    "partial_control": 5,
    "pipeline_critical": 20,
    "pipeline_high": 10,
    "pipeline_medium": 4,
    "missing_policy": 6,
    "stale_evidence_days": 0.1,  # per day stale
}

SEVERITY_THRESHOLDS = {
    "critical": {"min": 80, "label": "Critical Risk", "color": "#dc2626"},
    "high": {"min": 60, "label": "High Risk", "color": "#ea580c"},
    "elevated": {"min": 40, "label": "Elevated Risk", "color": "#d97706"},
    "moderate": {"min": 20, "label": "Moderate Risk", "color": "#2563eb"},
    "low": {"min": 0, "label": "Low Risk", "color": "#059669"},
}


def get_risk_level(score: float) -> dict:
    """Get risk level based on score."""
    for level, config in SEVERITY_THRESHOLDS.items():
        if score >= config["min"]:
            return {"level": level, "label": config["label"], "color": config["color"]}
    return {"level": "low", "label": "Low Risk", "color": "#059669"}


@router.get("/org-score")
async def get_org_risk_score(current_user: Dict = Depends(get_current_user)):
    """Calculate aggregate risk score for the entire organization."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    # 1. SIEM Factor
    siem_score = await _calc_siem_risk(org_id)

    # 2. Compliance Factor (across all frameworks)
    compliance_score = await _calc_compliance_risk(org_id)

    # 3. Pipeline Factor
    pipeline_score = await _calc_pipeline_risk(org_id)

    # 4. Ingestion Factor (unmapped controls)
    ingestion_score = await _calc_ingestion_risk(org_id)

    # 5. Policy Coverage Factor
    policy_score = await _calc_policy_risk(org_id)

    # 6. Asset-Weighted Vulnerability Factor (criticality multiplier)
    asset_score, top_risky_assets = await _calc_asset_weighted_risk(org_id)

    # Weighted aggregate (normalize to 0-100)
    raw = (siem_score * 0.20 + compliance_score * 0.20 + pipeline_score * 0.15 +
           ingestion_score * 0.10 + policy_score * 0.10 + asset_score * 0.25)
    org_score = min(100, max(0, raw))
    risk_level = get_risk_level(org_score)

    # Store snapshot for trend tracking
    now = datetime.now(timezone.utc).isoformat()
    await db.risk_score_history.insert_one({
        "organization_id": org_id,
        "score": round(org_score, 1),
        "level": risk_level["level"],
        "factors": {
            "siem": round(siem_score, 1),
            "compliance": round(compliance_score, 1),
            "pipeline": round(pipeline_score, 1),
            "ingestion": round(ingestion_score, 1),
            "policy": round(policy_score, 1),
            "asset": round(asset_score, 1),
        },
        "timestamp": now,
    })

    return {
        "score": round(org_score, 1),
        "level": risk_level["level"],
        "label": risk_level["label"],
        "color": risk_level["color"],
        "factors": {
            "siem": {"score": round(siem_score, 1), "weight": 0.20, "label": "SIEM Events"},
            "compliance": {"score": round(compliance_score, 1), "weight": 0.20, "label": "Compliance Status"},
            "pipeline": {"score": round(pipeline_score, 1), "weight": 0.15, "label": "Pipeline Security"},
            "ingestion": {"score": round(ingestion_score, 1), "weight": 0.10, "label": "Checklist Coverage"},
            "policy": {"score": round(policy_score, 1), "weight": 0.10, "label": "Policy Coverage"},
            "asset": {"score": round(asset_score, 1), "weight": 0.25, "label": "Asset Risk (Criticality-Weighted)"},
        },
        "top_risky_assets": top_risky_assets,
        "timestamp": now,
    }


@router.get("/framework-scores")
async def get_framework_risk_scores(current_user: Dict = Depends(get_current_user)):
    """Calculate risk scores per framework."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    frameworks = await db.frameworks.find({"type": "standard"}, {"_id": 0}).to_list(100)
    results = []

    for fw in frameworks:
        fw_id = fw["id"]

        # Compliance status for this framework
        compliance_data = await db.control_compliance.find(
            {"organization_id": org_id, "framework_id": fw_id}, {"_id": 0}
        ).to_list(5000)

        total_controls = await db.controls.count_documents({"framework_id": fw_id})
        assessed = len(compliance_data)
        compliant = sum(1 for c in compliance_data if c.get("status") == "compliant")
        partial = sum(1 for c in compliance_data if c.get("status") == "partial")
        non_compliant = sum(1 for c in compliance_data if c.get("status") == "non_compliant")
        not_assessed = total_controls - assessed

        # Calculate framework risk
        if total_controls == 0:
            fw_score = 0
        else:
            risk_points = (
                non_compliant * RISK_WEIGHTS["non_compliant_control"] +
                partial * RISK_WEIGHTS["partial_control"] +
                not_assessed * RISK_WEIGHTS["unmapped_control_medium"]
            )
            fw_score = min(100, risk_points / max(total_controls, 1) * 10)

        # Policy coverage
        mappings = await db.mappings.find(
            {"organization_id": org_id, "framework_id": fw_id}, {"_id": 0, "control_id": 1}
        ).to_list(5000)
        controls_with_policy = len(set(m["control_id"] for m in mappings))
        policy_coverage = controls_with_policy / max(total_controls, 1) * 100

        risk_level = get_risk_level(fw_score)

        results.append({
            "framework_id": fw_id,
            "framework_name": fw["name"],
            "risk_score": round(fw_score, 1),
            "risk_level": risk_level["level"],
            "risk_label": risk_level["label"],
            "risk_color": risk_level["color"],
            "total_controls": total_controls,
            "compliant": compliant,
            "partial": partial,
            "non_compliant": non_compliant,
            "not_assessed": not_assessed,
            "policy_coverage": round(policy_coverage, 1),
        })

    results.sort(key=lambda x: -x["risk_score"])
    return results


@router.get("/trend")
async def get_risk_trend(days: int = 30, current_user: Dict = Depends(get_current_user)):
    """Get risk score trend over time."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    history = await db.risk_score_history.find(
        {"organization_id": org_id, "timestamp": {"$gte": cutoff}}, {"_id": 0}
    ).sort("timestamp", 1).to_list(1000)

    return {
        "history": history,
        "period_days": days,
        "data_points": len(history),
    }


@router.get("/alerts")
async def get_risk_alerts(current_user: Dict = Depends(get_current_user)):
    """Get active risk alerts based on current thresholds."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    alerts = []

    # Check SIEM for critical events
    cutoff = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    critical_events = await db.siem_events.count_documents(
        {"severity": "critical", "timestamp": {"$gte": cutoff}}
    )
    if critical_events > 0:
        alerts.append({
            "type": "siem",
            "severity": "critical",
            "title": f"{critical_events} critical SIEM events in last 7 days",
            "description": "Critical security events detected that may indicate active threats",
            "action": "Review SIEM events and investigate incidents",
        })

    # Check pipeline failures
    recent_runs = await db.pipeline_runs.find(
        {"organization_id": org_id, "gate_result": "fail"}, {"_id": 0}
    ).sort("created_at", -1).to_list(5)
    if recent_runs:
        alerts.append({
            "type": "pipeline",
            "severity": "high",
            "title": f"{len(recent_runs)} pipeline runs failed compliance gate",
            "description": f"Latest: {recent_runs[0].get('pipeline_name', 'Unknown')} - {recent_runs[0].get('total_findings', 0)} findings",
            "action": "Review pipeline findings and remediate vulnerabilities",
        })

    # Check for non-compliant controls
    non_compliant_count = await db.control_compliance.count_documents(
        {"organization_id": org_id, "status": "non_compliant"}
    )
    if non_compliant_count > 5:
        alerts.append({
            "type": "compliance",
            "severity": "high",
            "title": f"{non_compliant_count} controls are non-compliant",
            "description": "Multiple compliance controls have been assessed as non-compliant",
            "action": "Review non-compliant controls and implement remediation policies",
        })

    # Check unmapped ingested controls
    unmapped_count = await db.ingested_controls.count_documents(
        {"organization_id": org_id, "status": "unmapped"}
    )
    if unmapped_count > 10:
        alerts.append({
            "type": "ingestion",
            "severity": "medium",
            "title": f"{unmapped_count} ingested controls are unmapped",
            "description": "Checklist controls without framework mappings reduce compliance visibility",
            "action": "Run AI Auto-Map on unmapped checklists",
        })

    # Check stale assessments (frameworks not assessed in 30+ days)
    frameworks = await db.frameworks.find({"type": "standard"}, {"_id": 0, "id": 1, "name": 1}).to_list(100)
    stale_cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    for fw in frameworks:
        recent_assessment = await db.control_compliance.find_one(
            {"organization_id": org_id, "framework_id": fw["id"], "updated_at": {"$gte": stale_cutoff}}
        )
        if not recent_assessment:
            existing = await db.control_compliance.find_one(
                {"organization_id": org_id, "framework_id": fw["id"]}
            )
            if existing:
                alerts.append({
                    "type": "stale",
                    "severity": "low",
                    "title": f"{fw['name']} assessment may be stale",
                    "description": "No compliance updates in the last 30 days",
                    "action": "Re-run AI assessment to refresh compliance status",
                })

    alerts.sort(key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x["severity"], 4))
    return {"alerts": alerts, "total": len(alerts)}


# ─── Internal risk calculation helpers ─────────────────────

async def _calc_siem_risk(org_id: str) -> float:
    """Calculate risk from SIEM events (last 30 days)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$severity",
            "count": {"$sum": 1}
        }}
    ]
    sev_counts = {}
    async for doc in db.siem_events.aggregate(pipeline):
        sev_counts[doc["_id"]] = doc["count"]

    critical = sev_counts.get("critical", 0)
    high = sev_counts.get("high", 0)
    medium = sev_counts.get("medium", 0)

    score = (critical * RISK_WEIGHTS["siem_critical"] +
             high * RISK_WEIGHTS["siem_high"] +
             medium * RISK_WEIGHTS["siem_medium"])

    # Normalize to 0-100 (cap at reasonable levels)
    return min(100, score / 10)


async def _calc_compliance_risk(org_id: str) -> float:
    """Calculate risk from compliance status across all frameworks."""
    pipeline = [
        {"$match": {"organization_id": org_id}},
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1}
        }}
    ]
    status_counts = {}
    async for doc in db.control_compliance.aggregate(pipeline):
        status_counts[doc["_id"]] = doc["count"]

    non_compliant = status_counts.get("non_compliant", 0)
    partial = status_counts.get("partial", 0)
    total = sum(status_counts.values())

    if total == 0:
        return 50  # No data = moderate risk

    risk_pct = (non_compliant * 1.0 + partial * 0.4) / total * 100
    return min(100, risk_pct)


async def _calc_pipeline_risk(org_id: str) -> float:
    """Calculate risk from recent pipeline scan results."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    runs = await db.pipeline_runs.find(
        {"organization_id": org_id, "created_at": {"$gte": cutoff}}, {"_id": 0}
    ).to_list(100)

    if not runs:
        return 30  # No pipeline data = moderate concern

    total_risk = sum(r.get("risk_score", 0) for r in runs)
    failed = sum(1 for r in runs if r.get("gate_result") == "fail")
    avg_risk = total_risk / len(runs)

    # Factor in gate failure rate
    fail_rate = failed / len(runs) * 100 if runs else 0
    return min(100, avg_risk * 1.5 + fail_rate * 0.5)


async def _calc_ingestion_risk(org_id: str) -> float:
    """Calculate risk from unmapped ingested controls."""
    total = await db.ingested_controls.count_documents({"organization_id": org_id})
    unmapped = await db.ingested_controls.count_documents(
        {"organization_id": org_id, "status": "unmapped"}
    )

    if total == 0:
        return 20  # No checklists = some risk

    unmapped_pct = unmapped / total * 100
    return min(100, unmapped_pct * 0.8)


async def _calc_policy_risk(org_id: str) -> float:
    """Calculate risk from policy coverage gaps."""
    total_controls = await db.controls.count_documents({})
    mappings = await db.mappings.find(
        {"organization_id": org_id}, {"_id": 0, "control_id": 1}
    ).to_list(10000)
    mapped_controls = len(set(m["control_id"] for m in mappings))

    if total_controls == 0:
        return 0

    gap_pct = (total_controls - mapped_controls) / total_controls * 100
    return min(100, gap_pct * 0.8)


# Severity → base risk points
ASSET_SEVERITY_POINTS = {"critical": 25, "high": 12, "medium": 4}

# Criticality → multiplier (option 2b: Crown Jewels carry more weight than dev boxes)
ASSET_CRITICALITY_MULTIPLIER = {"critical": 2.0, "high": 1.5, "medium": 1.0, "low": 0.5}


async def _calc_asset_weighted_risk(org_id: str):
    """
    Calculate vulnerability risk weighted by asset criticality.
    Returns (org_asset_score 0-100, top 5 risky assets).
    A critical CVE on a Crown Jewel asset = 2× weight; on a dev box = 0.5×.
    """
    # Pull all open vuln findings
    findings = await db.tenable_findings.find(
        {
            "organization_id": org_id,
            "finding_type": "vulnerability",
            "state": {"$in": ["open", "reopened"]},
        },
        {"_id": 0},
    ).to_list(5000)

    if not findings:
        return 0, []

    # Build hostname→criticality map from assets collection
    assets = await db.assets.find(
        {"organization_id": org_id}, {"_id": 0, "id": 1, "hostname": 1, "asset_uuid": 1, "criticality": 1, "owner": 1, "environment": 1}
    ).to_list(5000)

    crit_by_uuid = {a.get("asset_uuid"): a for a in assets if a.get("asset_uuid")}
    crit_by_host = {a.get("hostname"): a for a in assets if a.get("hostname")}

    asset_risk_scores = {}  # asset_id → {score, hostname, vulns}

    for f in findings:
        sev = f.get("severity", "medium")
        base = ASSET_SEVERITY_POINTS.get(sev, ASSET_SEVERITY_POINTS["medium"])

        # Match asset
        a = crit_by_uuid.get(f.get("asset_uuid")) or crit_by_host.get(f.get("asset_hostname"))
        criticality = (a or {}).get("criticality", "medium")
        multiplier = ASSET_CRITICALITY_MULTIPLIER.get(criticality, 1.0)
        weighted_pts = base * multiplier

        if a:
            key = a["id"]
            bucket = asset_risk_scores.setdefault(key, {
                "asset_id": a["id"],
                "hostname": a.get("hostname", ""),
                "criticality": criticality,
                "owner": a.get("owner", ""),
                "environment": a.get("environment", ""),
                "score": 0.0,
                "open_vulns": 0,
                "critical_vulns": 0,
            })
        else:
            # No asset record yet — synthesize a placeholder bucket keyed by hostname
            host = f.get("asset_hostname", "unknown")
            bucket = asset_risk_scores.setdefault(f"_unmanaged_{host}", {
                "asset_id": None,
                "hostname": host,
                "criticality": "medium",
                "owner": "",
                "environment": "unknown",
                "score": 0.0,
                "open_vulns": 0,
                "critical_vulns": 0,
            })

        bucket["score"] += weighted_pts
        bucket["open_vulns"] += 1
        if sev == "critical":
            bucket["critical_vulns"] += 1

    # Org score: total weighted risk / total assets, normalized to 0-100
    total_weighted = sum(b["score"] for b in asset_risk_scores.values())
    asset_count = max(len(asset_risk_scores), 1)
    org_score = min(100, (total_weighted / asset_count) * 1.5)

    # Top 5 risky assets
    top = sorted(asset_risk_scores.values(), key=lambda x: -x["score"])[:5]
    for t in top:
        t["score"] = round(t["score"], 1)

    return org_score, top


@router.get("/asset-risk")
async def get_asset_risk_breakdown(current_user: Dict = Depends(get_current_user)):
    """Per-asset risk breakdown (criticality-weighted)."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    score, top = await _calc_asset_weighted_risk(org_id)
    return {
        "asset_risk_score": round(score, 1),
        "top_risky_assets": top,
        "criticality_multipliers": ASSET_CRITICALITY_MULTIPLIER,
        "severity_base_points": ASSET_SEVERITY_POINTS,
    }
