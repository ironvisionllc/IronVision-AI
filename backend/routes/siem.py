"""
SIEM Integration - Security event collection, monitoring, and control mapping.
Captures security-relevant events from the app and maps them to compliance controls.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Dict, Optional, List
from datetime import datetime, timezone, timedelta
import uuid
import logging

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/siem", tags=["siem"])

# SIEM event categories and their control mappings
CONTROL_MAPPINGS = {
    "authentication": {
        "controls": ["AC-2", "AC-7", "IA-2", "IA-5"],
        "frameworks": ["nist-800-53", "nist-800-171"],
        "description": "Authentication & Access Control",
    },
    "authorization": {
        "controls": ["AC-3", "AC-6", "AC-17"],
        "frameworks": ["nist-800-53"],
        "description": "Authorization & Least Privilege",
    },
    "data_access": {
        "controls": ["AU-3", "AU-6", "AU-12", "SI-4"],
        "frameworks": ["nist-800-53", "nist-800-171"],
        "description": "Audit & Data Monitoring",
    },
    "policy_change": {
        "controls": ["CM-3", "CM-5", "CM-6"],
        "frameworks": ["nist-800-53"],
        "description": "Configuration & Change Management",
    },
    "risk_management": {
        "controls": ["RA-3", "RA-5", "PM-9"],
        "frameworks": ["nist-800-53"],
        "description": "Risk Assessment",
    },
    "incident": {
        "controls": ["IR-4", "IR-5", "IR-6"],
        "frameworks": ["nist-800-53", "nist-800-171"],
        "description": "Incident Response",
    },
    "system": {
        "controls": ["SI-2", "SI-4", "SI-7"],
        "frameworks": ["nist-800-53"],
        "description": "System & Information Integrity",
    },
}

SEVERITY_WEIGHTS = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


class SIEMEvent(BaseModel):
    event_type: str
    category: str
    severity: str = "info"
    source: str = "ironvision"
    details: str = ""
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    ip_address: Optional[str] = None
    metadata: Optional[dict] = None


async def log_siem_event(
    event_type: str,
    category: str,
    severity: str = "info",
    source: str = "ironvision",
    details: str = "",
    user_id: str = None,
    user_name: str = None,
    ip_address: str = None,
    metadata: dict = None,
):
    """Log a SIEM event to the database. Called internally by other routes."""
    now = datetime.now(timezone.utc).isoformat()
    mapping = CONTROL_MAPPINGS.get(category, {})

    event = {
        "id": str(uuid.uuid4()),
        "event_type": event_type,
        "category": category,
        "severity": severity,
        "source": source,
        "details": details,
        "user_id": user_id,
        "user_name": user_name,
        "ip_address": ip_address,
        "metadata": metadata or {},
        "mapped_controls": mapping.get("controls", []),
        "mapped_frameworks": mapping.get("frameworks", []),
        "timestamp": now,
    }
    try:
        await db.siem_events.insert_one(event)
    except Exception as e:
        logger.error(f"Failed to log SIEM event: {e}")


@router.get("/events")
async def get_events(
    category: Optional[str] = None,
    severity: Optional[str] = None,
    source: Optional[str] = None,
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=100, ge=1, le=500),
    current_user: Dict = Depends(get_current_user),
):
    """Get SIEM events with filtering."""
    query = {}
    if category:
        query["category"] = category
    if severity:
        query["severity"] = severity
    if source:
        query["source"] = source

    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    query["timestamp"] = {"$gte": cutoff}

    events = await db.siem_events.find(
        query, {"_id": 0}
    ).sort("timestamp", -1).to_list(limit)
    return events


@router.get("/dashboard")
async def get_siem_dashboard(
    days: int = Query(default=7, ge=1, le=90),
    current_user: Dict = Depends(get_current_user),
):
    """SIEM dashboard summary with aggregated metrics."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

    total = await db.siem_events.count_documents({"timestamp": {"$gte": cutoff}})

    # Severity distribution
    severity_dist = {}
    for sev in ["critical", "high", "medium", "low", "info"]:
        severity_dist[sev] = await db.siem_events.count_documents({
            "timestamp": {"$gte": cutoff}, "severity": sev
        })

    # Category distribution
    category_dist = {}
    for cat in CONTROL_MAPPINGS:
        category_dist[cat] = await db.siem_events.count_documents({
            "timestamp": {"$gte": cutoff}, "category": cat
        })

    # Hourly event volume (last 24h)
    hourly_cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    recent_events = await db.siem_events.find(
        {"timestamp": {"$gte": hourly_cutoff}},
        {"_id": 0, "timestamp": 1, "severity": 1}
    ).to_list(1000)

    hourly_volume = {}
    for ev in recent_events:
        try:
            hour = ev["timestamp"][:13]
            hourly_volume[hour] = hourly_volume.get(hour, 0) + 1
        except (KeyError, TypeError):
            pass

    # Latest critical/high events
    critical_events = await db.siem_events.find(
        {"timestamp": {"$gte": cutoff}, "severity": {"$in": ["critical", "high"]}},
        {"_id": 0}
    ).sort("timestamp", -1).to_list(10)

    # Threat score (weighted severity count)
    threat_score = 0
    for sev, count in severity_dist.items():
        threat_score += SEVERITY_WEIGHTS.get(sev, 0) * count
    max_possible = total * 4 if total > 0 else 1
    threat_level = min(int((threat_score / max_possible) * 100), 100) if total > 0 else 0

    return {
        "total_events": total,
        "period_days": days,
        "threat_level": threat_level,
        "severity_distribution": severity_dist,
        "category_distribution": category_dist,
        "hourly_volume": [{"hour": h, "count": c} for h, c in sorted(hourly_volume.items())],
        "critical_events": critical_events,
    }


@router.get("/control-mapping")
async def get_control_mapping(current_user: Dict = Depends(get_current_user)):
    """Get SIEM event-to-control framework mapping with event counts."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    result = []
    for cat, mapping in CONTROL_MAPPINGS.items():
        count = await db.siem_events.count_documents({
            "timestamp": {"$gte": cutoff}, "category": cat
        })
        result.append({
            "category": cat,
            "description": mapping["description"],
            "controls": mapping["controls"],
            "frameworks": mapping["frameworks"],
            "event_count_30d": count,
        })
    return result


@router.get("/export")
async def export_events(
    format: str = Query(default="json", regex="^(json|csv|syslog)$"),
    days: int = Query(default=7, ge=1, le=90),
    current_user: Dict = Depends(get_current_user),
):
    """Export SIEM events in various formats."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    events = await db.siem_events.find(
        {"timestamp": {"$gte": cutoff}}, {"_id": 0}
    ).sort("timestamp", -1).to_list(1000)

    if format == "csv":
        import io, csv
        output = io.StringIO()
        if events:
            writer = csv.DictWriter(output, fieldnames=["timestamp", "event_type", "category", "severity", "source", "details", "user_name", "ip_address"])
            writer.writeheader()
            for ev in events:
                writer.writerow({k: ev.get(k, "") for k in writer.fieldnames})
        from fastapi.responses import StreamingResponse
        output.seek(0)
        return StreamingResponse(
            iter([output.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=siem_events_{days}d.csv"}
        )

    if format == "syslog":
        lines = []
        for ev in events:
            pri = {"critical": 2, "high": 3, "medium": 4, "low": 5, "info": 6}.get(ev.get("severity", "info"), 6)
            lines.append(f"<{pri}>{ev.get('timestamp','')} {ev.get('source','')} {ev.get('event_type','')}: {ev.get('details','')}")
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("\n".join(lines), headers={"Content-Disposition": f"attachment; filename=siem_events_{days}d.log"})

    return {"events": events, "count": len(events), "period_days": days}


@router.post("/seed-demo")
async def seed_demo_events(current_user: Dict = Depends(get_current_user)):
    """Seed demo SIEM events for testing/demo purposes."""
    now = datetime.now(timezone.utc)
    demo_events = [
        {"event_type": "login_success", "category": "authentication", "severity": "info", "details": "Demo Admin logged in successfully", "user_name": "Demo Admin"},
        {"event_type": "login_failed", "category": "authentication", "severity": "medium", "details": "Failed login attempt for unknown@test.com", "user_name": "Unknown"},
        {"event_type": "policy_created", "category": "policy_change", "severity": "low", "details": "New policy 'Access Control Policy' created", "user_name": "Demo Admin"},
        {"event_type": "risk_escalated", "category": "risk_management", "severity": "high", "details": "Risk 'Unpatched Systems' escalated from Medium to High", "user_name": "Demo Admin"},
        {"event_type": "evidence_uploaded", "category": "data_access", "severity": "info", "details": "Evidence uploaded for SOC 2 audit", "user_name": "Demo Admin"},
        {"event_type": "brute_force_detected", "category": "authentication", "severity": "critical", "details": "5 failed login attempts detected from IP 203.0.113.42", "ip_address": "203.0.113.42"},
        {"event_type": "unauthorized_access", "category": "authorization", "severity": "high", "details": "User attempted to access admin endpoint without privileges", "user_name": "Demo User"},
        {"event_type": "config_change", "category": "policy_change", "severity": "medium", "details": "Slack integration settings updated", "user_name": "Demo Admin"},
        {"event_type": "risk_created", "category": "risk_management", "severity": "medium", "details": "New risk 'Third-party Vendor Exposure' added", "user_name": "Demo Admin"},
        {"event_type": "audit_completed", "category": "data_access", "severity": "low", "details": "Annual compliance audit completed for HIPAA framework", "user_name": "Demo Admin"},
        {"event_type": "incident_reported", "category": "incident", "severity": "high", "details": "Data exposure incident reported - PII found in logs", "user_name": "Demo Admin"},
        {"event_type": "system_update", "category": "system", "severity": "info", "details": "System patched to version 2.4.1", "user_name": "System"},
        {"event_type": "mfa_disabled", "category": "authentication", "severity": "high", "details": "MFA disabled for user account demo-user@grc.com", "user_name": "Demo Admin"},
        {"event_type": "permission_change", "category": "authorization", "severity": "medium", "details": "User 'Demo User' role changed from viewer to editor", "user_name": "Demo Admin"},
        {"event_type": "data_export", "category": "data_access", "severity": "medium", "details": "Bulk data export: 500 risk records exported to CSV", "user_name": "Demo Admin"},
    ]

    for i, ev in enumerate(demo_events):
        offset = timedelta(hours=i * 4, minutes=i * 17)
        ts = (now - offset).isoformat()
        mapping = CONTROL_MAPPINGS.get(ev["category"], {})
        await db.siem_events.insert_one({
            "id": str(uuid.uuid4()),
            "event_type": ev["event_type"],
            "category": ev["category"],
            "severity": ev["severity"],
            "source": "ironvision",
            "details": ev["details"],
            "user_id": None,
            "user_name": ev.get("user_name"),
            "ip_address": ev.get("ip_address"),
            "metadata": {},
            "mapped_controls": mapping.get("controls", []),
            "mapped_frameworks": mapping.get("frameworks", []),
            "timestamp": ts,
        })

    return {"status": "seeded", "count": len(demo_events)}
