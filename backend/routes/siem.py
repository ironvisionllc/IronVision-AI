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

# SIEM event categories and their control mappings (all frameworks)
CONTROL_MAPPINGS = {
    "authentication": {
        "controls": [
            "AC-2", "AC-7", "IA-2", "IA-5",
            "PR.AC-1", "PR.AC-7", "DE.CM-1",
            "3.1.1", "3.1.2", "3.1.8", "3.5.1", "3.5.2",
            "5.15", "5.16", "5.17", "8.5",
            "164.312(a)(1)", "164.312(d)",
            "CC6.1", "CC6.2", "CC6.3",
            "AC.L1-3.1.1", "AC.L1-3.1.2", "IA.L1-3.5.1", "IA.L1-3.5.2",
            "NIS2-8", "NIS2-9",
            "SR-AC-1", "SR-AC-2", "SR-AC-7", "SR-IA-1", "SR-IA-2",
            "Art.32",
        ],
        "frameworks": ["nist-800-53", "nist-csf", "nist-800-171", "iso-27001", "hipaa", "soc2", "cmmc", "nis2", "stateramp", "gdpr"],
        "description": "Authentication & Access Control",
    },
    "authorization": {
        "controls": [
            "AC-3", "AC-6", "AC-17",
            "PR.AC-3", "PR.AC-4", "PR.AC-5",
            "3.1.3", "3.1.4", "3.1.5", "3.1.6", "3.1.7", "3.1.12",
            "5.3", "5.18", "8.1", "8.4",
            "164.312(a)(2)(ii)", "164.308(a)(3)(i)",
            "CC6.6", "CC6.7", "CC6.8",
            "AC.L2-3.1.3", "AC.L2-3.1.4", "AC.L2-3.1.5",
            "NIS2-10",
            "SR-AC-3", "SR-AC-5", "SR-AC-6", "SR-AC-17",
            "Art.25",
        ],
        "frameworks": ["nist-800-53", "nist-csf", "nist-800-171", "iso-27001", "hipaa", "soc2", "cmmc", "nis2", "stateramp", "gdpr"],
        "description": "Authorization & Least Privilege",
    },
    "data_access": {
        "controls": [
            "AU-3", "AU-6", "AU-12", "SI-4",
            "PR.DS-1", "PR.DS-2", "PR.DS-5", "DE.AE-3", "DE.CM-3", "DE.CM-7",
            "3.3.1", "3.3.2", "3.3.3", "3.3.4", "3.3.5",
            "5.33", "8.10", "8.12", "8.13",
            "164.312(b)", "164.312(c)(1)", "164.308(a)(1)(ii)(D)",
            "CC4.1", "CC4.2", "CC5.1", "C1.1",
            "AU.L2-3.3.1", "AU.L2-3.3.2", "AU.L2-3.3.5",
            "NIS2-5",
            "SR-AU-1", "SR-AU-2", "SR-AU-3", "SR-AU-6",
            "Art.5", "Art.30",
        ],
        "frameworks": ["nist-800-53", "nist-csf", "nist-800-171", "iso-27001", "hipaa", "soc2", "cmmc", "nis2", "stateramp", "gdpr"],
        "description": "Audit & Data Monitoring",
    },
    "policy_change": {
        "controls": [
            "CM-3", "CM-5", "CM-6",
            "PR.IP-1", "PR.IP-3",
            "3.4.1", "3.4.2", "3.4.3", "3.4.5",
            "5.1", "5.37", "8.9",
            "164.308(a)(1)(i)",
            "CC8.1", "CC5.2",
            "CM.L2-3.4.1", "CM.L2-3.4.2", "CM.L2-3.4.3",
            "NIS2-6",
            "SR-CM-1", "SR-CM-2", "SR-CM-3",
            "Art.25",
        ],
        "frameworks": ["nist-800-53", "nist-csf", "nist-800-171", "iso-27001", "hipaa", "soc2", "cmmc", "nis2", "stateramp", "gdpr"],
        "description": "Configuration & Change Management",
    },
    "risk_management": {
        "controls": [
            "RA-3", "RA-5", "PM-9",
            "ID.RA-1", "ID.RA-3", "ID.RA-5", "ID.RM-1",
            "3.11.1", "3.11.2", "3.11.3", "3.12.1", "3.12.2",
            "5.7", "5.23", "5.29",
            "164.308(a)(1)(ii)(A)", "164.308(a)(1)(ii)(B)",
            "CC3.1", "CC3.2", "CC3.3", "CC9.1",
            "RE.L2-3.13.1",
            "NIS2-1", "NIS2-4",
            "SR-CA-1", "SR-CA-2", "SR-CA-7",
            "Art.35",
        ],
        "frameworks": ["nist-800-53", "nist-csf", "nist-800-171", "iso-27001", "hipaa", "soc2", "cmmc", "nis2", "stateramp", "gdpr"],
        "description": "Risk Assessment",
    },
    "incident": {
        "controls": [
            "IR-4", "IR-5", "IR-6",
            "RS.AN-1", "RS.AN-2", "RS.MI-1", "RS.MI-2", "DE.AE-2", "DE.AE-5",
            "3.6.1", "3.6.2", "3.6.3",
            "5.24", "5.25", "5.26",
            "164.308(a)(6)(i)", "164.308(a)(6)(ii)",
            "CC7.2", "CC7.3",
            "IR.L2-3.6.1", "IR.L2-3.6.2", "IR.L2-3.6.3",
            "NIS2-2", "NIS2-11", "NIS2-12",
            "SR-IR-1", "SR-IR-2", "SR-IR-4", "SR-IR-6",
            "Art.33", "Art.34",
        ],
        "frameworks": ["nist-800-53", "nist-csf", "nist-800-171", "iso-27001", "hipaa", "soc2", "cmmc", "nis2", "stateramp", "gdpr"],
        "description": "Incident Response",
    },
    "system": {
        "controls": [
            "SI-2", "SI-4", "SI-7",
            "PR.MA-1", "DE.CM-4", "DE.CM-8",
            "3.13.1", "3.14.1", "3.14.2", "3.14.3", "3.14.6", "3.7.1",
            "8.7", "8.8", "8.15", "8.16",
            "164.310(a)(1)", "164.310(d)(1)",
            "CC7.1", "A1.1", "A1.2",
            "MA.L2-3.7.1",
            "NIS2-3", "NIS2-7",
            "SR-SI-1", "SR-SI-2", "SR-SI-3", "SR-SI-4", "SR-CP-1",
            "Art.32",
        ],
        "frameworks": ["nist-800-53", "nist-csf", "nist-800-171", "iso-27001", "hipaa", "soc2", "cmmc", "nis2", "stateramp", "gdpr"],
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
        import io
        import csv
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


# ---- Source Management ----

import secrets
import asyncio
import random

class SourceCreate(BaseModel):
    name: str
    source_type: str  # splunk, cloudtrail, qradar, generic


@router.get("/sources")
async def list_sources(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    sources = await db.siem_sources.find(
        {"organization_id": org_id}, {"_id": 0}
    ).to_list(50)
    # Enrich with event counts
    for src in sources:
        src["event_count"] = await db.siem_events.count_documents({"source": src["source_key"]})
        last_event = await db.siem_events.find_one(
            {"source": src["source_key"]}, {"_id": 0, "timestamp": 1},
            sort=[("timestamp", -1)]
        )
        src["last_event_at"] = last_event["timestamp"] if last_event else None
    return sources


@router.post("/sources")
async def create_source(req: SourceCreate, current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    source_key = f"src_{secrets.token_hex(12)}"
    api_key = f"iv_siem_{secrets.token_hex(24)}"
    now = datetime.now(timezone.utc).isoformat()

    source = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "name": req.name,
        "source_type": req.source_type,
        "source_key": source_key,
        "api_key": api_key,
        "status": "active",
        "created_at": now,
    }
    await db.siem_sources.insert_one(source)
    del source["_id"]
    return source


@router.delete("/sources/{source_id}")
async def delete_source(source_id: str, current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    result = await db.siem_sources.delete_one({"id": source_id, "organization_id": org_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Source not found")
    return {"status": "deleted"}


# ---- Webhook Ingestion (no auth - uses API key in header) ----

SPLUNK_SEVERITY_MAP = {"1": "info", "2": "info", "3": "low", "4": "low", "5": "medium", "6": "medium", "7": "high", "8": "high", "9": "critical", "10": "critical"}
CLOUDTRAIL_CATEGORY_MAP = {
    "ConsoleLogin": "authentication", "AssumeRole": "authorization",
    "GetObject": "data_access", "PutObject": "data_access",
    "CreatePolicy": "policy_change", "DeletePolicy": "policy_change",
    "RunInstances": "system", "StopInstances": "system",
}


def _classify_event(event_type: str, details: str = "") -> str:
    """Auto-classify event into a SIEM category."""
    text = f"{event_type} {details}".lower()
    if any(k in text for k in ["login", "auth", "password", "mfa", "credential", "brute"]):
        return "authentication"
    if any(k in text for k in ["permission", "role", "privilege", "access denied", "unauthorized"]):
        return "authorization"
    if any(k in text for k in ["export", "download", "query", "read", "evidence", "audit"]):
        return "data_access"
    if any(k in text for k in ["policy", "config", "setting", "change", "update"]):
        return "policy_change"
    if any(k in text for k in ["risk", "vulnerability", "threat", "scan"]):
        return "risk_management"
    if any(k in text for k in ["incident", "breach", "exposure", "leak"]):
        return "incident"
    return "system"


from fastapi import Request, Header

@router.post("/ingest/{source_key}")
async def ingest_event(source_key: str, request: Request, x_api_key: str = Header(None)):
    """Universal webhook endpoint for external SIEM sources."""
    source = await db.siem_sources.find_one({"source_key": source_key}, {"_id": 0})
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    if source.get("api_key") != x_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if source.get("status") != "active":
        raise HTTPException(status_code=403, detail="Source is inactive")

    body = await request.json()
    source_type = source.get("source_type", "generic")
    events_created = 0
    now = datetime.now(timezone.utc).isoformat()

    # Parse based on source type
    if source_type == "splunk":
        # Splunk HEC format: { "event": {...}, "sourcetype": "...", "index": "..." }
        raw_events = [body] if "event" in body else body.get("events", [body])
        for raw in raw_events:
            ev_data = raw.get("event", raw)
            severity = SPLUNK_SEVERITY_MAP.get(str(ev_data.get("severity", "1")), "info")
            event_type = ev_data.get("event_type", ev_data.get("name", "splunk_event"))
            details = ev_data.get("message", ev_data.get("_raw", str(ev_data)))
            category = _classify_event(event_type, details)
            await _store_ingested(source_key, source["name"], event_type, category, severity, details, ev_data, now)
            events_created += 1

    elif source_type == "cloudtrail":
        # AWS CloudTrail format: { "Records": [{...}] }
        records = body.get("Records", [body])
        for rec in records:
            event_type = rec.get("eventName", "unknown")
            category = CLOUDTRAIL_CATEGORY_MAP.get(event_type, _classify_event(event_type))
            user_name = rec.get("userIdentity", {}).get("userName", rec.get("userIdentity", {}).get("arn", ""))
            ip = rec.get("sourceIPAddress", "")
            severity = "high" if "Delete" in event_type or "Create" in event_type else "info"
            details = f"{event_type} by {user_name} from {ip} in {rec.get('awsRegion', 'unknown')}"
            await _store_ingested(source_key, source["name"], event_type, category, severity, details, rec, now, user_name=user_name, ip=ip)
            events_created += 1

    elif source_type == "qradar":
        # QRadar LEEF / offense format
        offenses = body.get("offenses", [body])
        for off in offenses:
            event_type = off.get("offense_type_str", off.get("event_type", "qradar_offense"))
            severity = "critical" if off.get("magnitude", 0) >= 8 else "high" if off.get("magnitude", 0) >= 5 else "medium"
            details = off.get("description", str(off))
            category = _classify_event(event_type, details)
            await _store_ingested(source_key, source["name"], event_type, category, severity, details, off, now)
            events_created += 1

    else:
        # Generic JSON: { "events": [{event_type, severity, details, ...}] } or single event
        raw_events = body.get("events", [body])
        for raw in raw_events:
            event_type = raw.get("event_type", raw.get("type", "generic_event"))
            severity = raw.get("severity", "info")
            if severity not in SEVERITY_WEIGHTS:
                severity = "info"
            details = raw.get("details", raw.get("message", str(raw)))
            category = raw.get("category", _classify_event(event_type, details))
            user_name = raw.get("user_name", raw.get("user", None))
            ip = raw.get("ip_address", raw.get("ip", None))
            await _store_ingested(source_key, source["name"], event_type, category, severity, details, raw, now, user_name=user_name, ip=ip)
            events_created += 1

    return {"status": "ingested", "events_created": events_created}


async def _store_ingested(source_key, source_name, event_type, category, severity, details, metadata, ts, user_name=None, ip=None):
    mapping = CONTROL_MAPPINGS.get(category, {})
    await db.siem_events.insert_one({
        "id": str(uuid.uuid4()),
        "event_type": event_type,
        "category": category,
        "severity": severity,
        "source": source_key,
        "source_name": source_name,
        "details": details[:500],
        "user_id": None,
        "user_name": user_name,
        "ip_address": ip,
        "metadata": metadata if isinstance(metadata, dict) else {},
        "mapped_controls": mapping.get("controls", []),
        "mapped_frameworks": mapping.get("frameworks", []),
        "timestamp": ts,
    })


# ---- Live Simulator ----

_simulation_task = None
_simulation_active = False

SIMULATION_EVENTS = [
    {"event_type": "login_success", "category": "authentication", "severity": "info", "details": "User {user} logged in from {ip}", "source_label": "Splunk HEC"},
    {"event_type": "login_failed", "category": "authentication", "severity": "medium", "details": "Failed login attempt for {user} from {ip}", "source_label": "Splunk HEC"},
    {"event_type": "brute_force_attempt", "category": "authentication", "severity": "critical", "details": "Brute force: {n} failed attempts from {ip} in 5 minutes", "source_label": "Splunk HEC"},
    {"event_type": "ConsoleLogin", "category": "authentication", "severity": "info", "details": "AWS ConsoleLogin by {user} from {ip} in us-east-1", "source_label": "AWS CloudTrail"},
    {"event_type": "AssumeRole", "category": "authorization", "severity": "low", "details": "AssumeRole by {user} for role AdminAccess in us-west-2", "source_label": "AWS CloudTrail"},
    {"event_type": "DeleteBucket", "category": "data_access", "severity": "high", "details": "S3 bucket 'compliance-evidence-prod' deletion attempted by {user}", "source_label": "AWS CloudTrail"},
    {"event_type": "GetObject", "category": "data_access", "severity": "info", "details": "S3 GetObject s3://audit-logs/{file} by {user}", "source_label": "AWS CloudTrail"},
    {"event_type": "unauthorized_api", "category": "authorization", "severity": "high", "details": "Unauthorized API call to /admin/users by {user} from {ip}", "source_label": "QRadar"},
    {"event_type": "privilege_escalation", "category": "authorization", "severity": "critical", "details": "Privilege escalation detected: {user} gained admin role", "source_label": "QRadar"},
    {"event_type": "policy_modified", "category": "policy_change", "severity": "medium", "details": "Security policy 'Password Requirements' modified by {user}", "source_label": "IronVision"},
    {"event_type": "firewall_rule_change", "category": "policy_change", "severity": "high", "details": "Firewall rule modified: Allow inbound 0.0.0.0/0 on port 22 by {user}", "source_label": "QRadar"},
    {"event_type": "vulnerability_scan", "category": "risk_management", "severity": "medium", "details": "Vulnerability scan completed: {n} findings ({n2} critical) on {host}", "source_label": "QRadar"},
    {"event_type": "malware_detected", "category": "incident", "severity": "critical", "details": "Malware detected on endpoint {host}: Trojan.GenericKD.{sig}", "source_label": "QRadar"},
    {"event_type": "data_exfiltration", "category": "incident", "severity": "critical", "details": "Potential data exfiltration: {n}GB uploaded to external IP {ip}", "source_label": "Splunk HEC"},
    {"event_type": "system_patch", "category": "system", "severity": "info", "details": "System {host} patched: {n} updates applied", "source_label": "IronVision"},
    {"event_type": "certificate_expiry", "category": "system", "severity": "high", "details": "TLS certificate for {host} expires in 3 days", "source_label": "IronVision"},
    {"event_type": "bulk_data_export", "category": "data_access", "severity": "medium", "details": "Bulk export: {n} records from compliance database by {user}", "source_label": "IronVision"},
    {"event_type": "risk_escalated", "category": "risk_management", "severity": "high", "details": "Risk '{risk}' escalated from Medium to Critical", "source_label": "IronVision"},
    {"event_type": "incident_response", "category": "incident", "severity": "medium", "details": "Incident INC-{inc}: Response team activated for {desc}", "source_label": "IronVision"},
    {"event_type": "config_drift", "category": "system", "severity": "medium", "details": "Configuration drift detected on {host}: {n} parameters changed", "source_label": "Splunk HEC"},
]

FAKE_USERS = ["j.smith@acme.com", "admin@acme.com", "k.jones@acme.com", "svc-backup@acme.com", "root", "m.chen@acme.com"]
FAKE_IPS = ["203.0.113.42", "198.51.100.7", "10.0.1.55", "192.168.1.100", "172.16.0.12", "45.33.32.156"]
FAKE_HOSTS = ["web-prod-01", "db-primary", "api-gateway", "compliance-app", "mail-server", "k8s-node-03"]
FAKE_RISKS = ["Unpatched Systems", "Third-party Exposure", "Data at Rest Encryption", "Insider Threat", "Cloud Misconfiguration"]
FAKE_FILES = ["audit_2025.pdf", "policy_v3.docx", "evidence_soc2.zip", "risk_report.csv"]


def _fill_template(template: str) -> str:
    return (
        template
        .replace("{user}", random.choice(FAKE_USERS))
        .replace("{ip}", random.choice(FAKE_IPS))
        .replace("{host}", random.choice(FAKE_HOSTS))
        .replace("{risk}", random.choice(FAKE_RISKS))
        .replace("{file}", random.choice(FAKE_FILES))
        .replace("{n}", str(random.randint(3, 500)))
        .replace("{n2}", str(random.randint(1, 20)))
        .replace("{sig}", str(random.randint(40000, 99999)))
        .replace("{inc}", str(random.randint(1001, 9999)))
        .replace("{desc}", random.choice(["phishing attack", "data breach", "ransomware", "DDoS attempt"]))
    )


async def _run_simulation():
    global _simulation_active
    while _simulation_active:
        template = random.choice(SIMULATION_EVENTS)
        now = datetime.now(timezone.utc).isoformat()
        details = _fill_template(template["details"])
        mapping = CONTROL_MAPPINGS.get(template["category"], {})

        await db.siem_events.insert_one({
            "id": str(uuid.uuid4()),
            "event_type": template["event_type"],
            "category": template["category"],
            "severity": template["severity"],
            "source": f"sim_{template['source_label'].lower().replace(' ', '_')}",
            "source_name": f"[SIM] {template['source_label']}",
            "details": details,
            "user_id": None,
            "user_name": details.split("by ")[-1].split(" from")[0] if "by " in details else None,
            "ip_address": next((ip for ip in FAKE_IPS if ip in details), None),
            "metadata": {"simulated": True, "source_label": template["source_label"]},
            "mapped_controls": mapping.get("controls", []),
            "mapped_frameworks": mapping.get("frameworks", []),
            "timestamp": now,
        })

        delay = random.uniform(2.0, 6.0)
        await asyncio.sleep(delay)


@router.post("/simulator/start")
async def start_simulation(current_user: Dict = Depends(get_current_user)):
    global _simulation_task, _simulation_active
    if _simulation_active:
        return {"status": "already_running"}

    _simulation_active = True
    _simulation_task = asyncio.create_task(_run_simulation())
    return {"status": "started", "message": "Simulation generating events every 2-6 seconds"}


@router.post("/simulator/stop")
async def stop_simulation(current_user: Dict = Depends(get_current_user)):
    global _simulation_task, _simulation_active
    _simulation_active = False
    if _simulation_task:
        _simulation_task.cancel()
        _simulation_task = None
    return {"status": "stopped"}


@router.get("/simulator/status")
async def simulation_status(current_user: Dict = Depends(get_current_user)):
    return {"active": _simulation_active}
