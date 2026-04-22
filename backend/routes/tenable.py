"""
Tenable Vulnerability Management Integration
- Connects to Tenable.io via pyTenable SDK
- Async export methodology for vulns and compliance
- Maps findings to NIST 800-53 / RMF controls
- Generates evidence artifacts for IronVision compliance engine
- Delta pulls with timestamp tracking
- Demo mode with simulated data when no API keys configured
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Optional, List
from datetime import datetime, timezone, timedelta
import uuid
import json
import logging
import asyncio

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tenable", tags=["tenable"])

# ─── NIST Control Mappings ─────────────────────────────────

VULN_SEVERITY_TO_CONTROLS = {
    "critical": {
        "controls": ["SI-2", "SI-5", "RA-5", "CM-6", "SA-11"],
        "status": "non_compliant",
        "reason": "Critical vulnerability detected — immediate remediation required",
    },
    "high": {
        "controls": ["SI-2", "RA-5", "CM-6"],
        "status": "non_compliant",
        "reason": "High severity vulnerability requires timely remediation",
    },
    "medium": {
        "controls": ["SI-2", "RA-5"],
        "status": "partial",
        "reason": "Medium severity vulnerability — remediation recommended",
    },
}

VULN_FIXED_CONTROLS = {
    "controls": ["SI-2", "RA-5"],
    "status": "compliant",
    "reason": "Vulnerability remediated — patch verified by scan",
}

COMPLIANCE_CHECK_TO_CONTROLS = {
    "password": ["IA-5", "AC-7"],
    "mfa": ["IA-2", "IA-2(1)", "IA-2(2)"],
    "multi-factor": ["IA-2", "IA-2(1)"],
    "encrypt": ["SC-28", "SC-13", "SC-8"],
    "tls": ["SC-8", "SC-13"],
    "ssl": ["SC-8", "SC-13"],
    "audit": ["AU-2", "AU-3", "AU-12"],
    "log": ["AU-2", "AU-6", "AU-12", "SI-4"],
    "firewall": ["SC-7", "AC-4"],
    "access control": ["AC-3", "AC-6"],
    "privilege": ["AC-6", "AC-6(1)"],
    "session": ["AC-12", "SC-10"],
    "timeout": ["AC-11", "AC-12"],
    "backup": ["CP-9", "CP-10"],
    "patch": ["SI-2", "CM-3"],
    "antivirus": ["SI-3"],
    "malware": ["SI-3", "SI-8"],
    "account": ["AC-2", "IA-4"],
    "lockout": ["AC-7"],
    "permission": ["AC-3", "AC-6"],
    "config": ["CM-2", "CM-6", "CM-7"],
    "baseline": ["CM-2", "CM-6"],
    "network": ["SC-7", "AC-4"],
    "remote": ["AC-17", "AC-17(1)"],
}


# ─── Models ─────────────────────────────────────────────

class TenableCredentials(BaseModel):
    access_key: str
    secret_key: str

class SyncRequest(BaseModel):
    mode: Optional[str] = "auto"  # auto, demo, live


# ─── Settings Endpoints ─────────────────────────────────

@router.post("/settings")
async def save_tenable_settings(creds: TenableCredentials, current_user: Dict = Depends(get_current_user)):
    """Save Tenable.io API credentials."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()

    await db.tenable_settings.update_one(
        {"organization_id": org_id},
        {"$set": {
            "access_key": creds.access_key,
            "secret_key": creds.secret_key,
            "configured": True,
            "updated_at": now,
            "updated_by": current_user["id"],
        },
         "$setOnInsert": {"organization_id": org_id, "created_at": now}},
        upsert=True,
    )
    return {"message": "Tenable credentials saved", "configured": True}


@router.get("/settings")
async def get_tenable_settings(current_user: Dict = Depends(get_current_user)):
    """Get Tenable settings (masked keys)."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    settings = await db.tenable_settings.find_one({"organization_id": org_id}, {"_id": 0})

    if not settings:
        return {"configured": False, "access_key_masked": "", "last_sync": None}

    ak = settings.get("access_key", "")
    return {
        "configured": settings.get("configured", False),
        "access_key_masked": f"{ak[:8]}...{ak[-4:]}" if len(ak) > 12 else "****",
        "last_sync": settings.get("last_sync"),
        "last_sync_results": settings.get("last_sync_results"),
    }


@router.delete("/settings")
async def delete_tenable_settings(current_user: Dict = Depends(get_current_user)):
    """Remove Tenable credentials."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    await db.tenable_settings.delete_one({"organization_id": org_id})
    return {"message": "Tenable credentials removed"}


# ─── Sync Endpoint ─────────────────────────────────────

@router.post("/sync")
async def sync_tenable_data(req: SyncRequest, current_user: Dict = Depends(get_current_user)):
    """Sync vulnerability and compliance data from Tenable.io."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()

    # Determine mode
    settings = await db.tenable_settings.find_one({"organization_id": org_id}, {"_id": 0})
    use_live = False

    if req.mode == "live":
        if not settings or not settings.get("configured"):
            raise HTTPException(400, "Tenable credentials not configured. Save API keys first.")
        use_live = True
    elif req.mode == "auto":
        use_live = bool(settings and settings.get("configured"))

    if use_live:
        results = await _sync_live(org_id, settings, now, current_user["id"])
    else:
        results = await _sync_demo(org_id, now, current_user["id"])

    # Update last sync timestamp
    await db.tenable_settings.update_one(
        {"organization_id": org_id},
        {"$set": {"last_sync": now, "last_sync_results": results},
         "$setOnInsert": {"organization_id": org_id, "configured": False}},
        upsert=True,
    )

    return results


# ─── Live Tenable Sync ─────────────────────────────────

async def _sync_live(org_id: str, settings: dict, now: str, user_id: str) -> dict:
    """Pull real data from Tenable.io using pyTenable."""
    try:
        from tenable.io import TenableIO
        tio = TenableIO(
            access_key=settings["access_key"],
            secret_key=settings["secret_key"],
        )

        # Get last sync time for delta pulls
        last_sync = settings.get("last_sync")
        since_ts = None
        if last_sync:
            try:
                since_ts = int(datetime.fromisoformat(last_sync.replace("Z", "+00:00")).timestamp())
            except (ValueError, AttributeError):
                since_ts = None

        vuln_count = 0
        compliance_count = 0
        mapped_controls = set()

        # 1. Vulnerability Export
        vuln_filters = {
            "severity": ["medium", "high", "critical"],
            "state": ["open", "reopened", "fixed"],
        }
        if since_ts:
            vuln_filters["since"] = since_ts

        try:
            for vuln in tio.exports.vulns(**vuln_filters):
                vuln_count += 1
                await _process_vulnerability(org_id, vuln, now, mapped_controls)
        except Exception as e:
            logger.error(f"Tenable vuln export error: {e}")

        # 2. Compliance Export
        try:
            for check in tio.exports.compliance():
                compliance_count += 1
                await _process_compliance_check(org_id, check, now, mapped_controls)
        except Exception as e:
            logger.error(f"Tenable compliance export error: {e}")

        # Store sync run
        run_doc = {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "mode": "live",
            "vulns_processed": vuln_count,
            "compliance_processed": compliance_count,
            "controls_updated": len(mapped_controls),
            "created_at": now,
        }
        await db.tenable_sync_runs.insert_one(run_doc)

        return {
            "mode": "live",
            "message": f"Synced {vuln_count} vulnerabilities and {compliance_count} compliance checks from Tenable.io",
            "vulns_processed": vuln_count,
            "compliance_processed": compliance_count,
            "controls_updated": len(mapped_controls),
        }

    except ImportError:
        raise HTTPException(500, "pyTenable library not available")
    except Exception as e:
        logger.error(f"Tenable sync failed: {e}")
        raise HTTPException(500, f"Tenable sync failed: {str(e)}")


async def _process_vulnerability(org_id: str, vuln: dict, now: str, mapped_controls: set):
    """Process a single Tenable vulnerability finding."""
    vuln_id = vuln.get("plugin", {}).get("id", str(uuid.uuid4())[:12])
    severity = vuln.get("severity", "medium").lower()
    state = vuln.get("state", "open").lower()
    plugin_name = vuln.get("plugin", {}).get("name", "Unknown Vulnerability")
    cves = vuln.get("plugin", {}).get("cve", [])
    asset_uuid = vuln.get("asset", {}).get("uuid", "")
    asset_hostname = vuln.get("asset", {}).get("hostname", asset_uuid[:12])

    # Determine control mapping
    if state == "fixed":
        mapping = VULN_FIXED_CONTROLS
    else:
        mapping = VULN_SEVERITY_TO_CONTROLS.get(severity, VULN_SEVERITY_TO_CONTROLS["medium"])

    # Store finding
    finding_doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "source": "tenable",
        "finding_type": "vulnerability",
        "tenable_plugin_id": str(vuln_id),
        "title": plugin_name,
        "severity": severity,
        "state": state,
        "cves": cves if isinstance(cves, list) else [cves] if cves else [],
        "asset_uuid": asset_uuid,
        "asset_hostname": asset_hostname,
        "control_ids": mapping["controls"],
        "compliance_status": mapping["status"],
        "reason": mapping["reason"],
        "raw_data": json.dumps({"plugin_id": vuln_id, "severity": severity, "state": state}),
        "collected_at": now,
    }

    # Upsert by plugin_id + asset
    await db.tenable_findings.update_one(
        {"organization_id": org_id, "tenable_plugin_id": str(vuln_id), "asset_uuid": asset_uuid},
        {"$set": finding_doc},
        upsert=True,
    )

    mapped_controls.update(mapping["controls"])


async def _process_compliance_check(org_id: str, check: dict, now: str, mapped_controls: set):
    """Process a single Tenable compliance check."""
    check_name = check.get("check_name", check.get("title", "Unknown Check"))
    status = check.get("status", "").upper()
    expected = check.get("expected_value", "")
    actual = check.get("actual_value", "")
    asset_uuid = check.get("asset", {}).get("uuid", "")

    # Map check to NIST controls based on keywords
    control_ids = _map_compliance_check_to_controls(check_name)
    compliance_status = "compliant" if status == "PASSED" else "non_compliant"

    finding_doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "source": "tenable",
        "finding_type": "compliance",
        "title": check_name,
        "status": status,
        "expected_value": str(expected),
        "actual_value": str(actual),
        "asset_uuid": asset_uuid,
        "control_ids": control_ids,
        "compliance_status": compliance_status,
        "reason": f"Compliance check {'passed' if status == 'PASSED' else 'failed'}: {check_name}",
        "collected_at": now,
    }

    await db.tenable_findings.update_one(
        {"organization_id": org_id, "title": check_name, "asset_uuid": asset_uuid, "finding_type": "compliance"},
        {"$set": finding_doc},
        upsert=True,
    )

    mapped_controls.update(control_ids)


def _map_compliance_check_to_controls(check_name: str) -> list:
    """Map a compliance check name to NIST controls via keyword matching."""
    controls = set()
    lower_name = check_name.lower()
    for keyword, ctrl_ids in COMPLIANCE_CHECK_TO_CONTROLS.items():
        if keyword in lower_name:
            controls.update(ctrl_ids)
    if not controls:
        controls.add("CM-6")  # Default to configuration management
    return list(controls)


# ─── Demo Mode Sync ─────────────────────────────────────

DEMO_VULNS = [
    {"plugin_id": "97833", "name": "Apache HTTP Server 2.4.x < 2.4.58 Multiple Vulnerabilities", "severity": "critical", "state": "open", "cve": ["CVE-2023-45802", "CVE-2023-43622"], "asset": "web-server-01", "asset_id": "a1b2c3d4"},
    {"plugin_id": "187352", "name": "OpenSSL 3.x < 3.1.4 Buffer Overflow", "severity": "critical", "state": "open", "cve": ["CVE-2023-5678"], "asset": "api-gateway-01", "asset_id": "e5f6a7b8"},
    {"plugin_id": "156032", "name": "Linux Kernel 5.x Privilege Escalation", "severity": "high", "state": "open", "cve": ["CVE-2024-1234"], "asset": "db-server-01", "asset_id": "c9d0e1f2"},
    {"plugin_id": "178234", "name": "PostgreSQL < 15.5 SQL Injection", "severity": "high", "state": "open", "cve": ["CVE-2024-5678"], "asset": "db-server-01", "asset_id": "c9d0e1f2"},
    {"plugin_id": "143567", "name": "Node.js < 20.10 HTTP Request Smuggling", "severity": "high", "state": "fixed", "cve": ["CVE-2023-44487"], "asset": "app-server-01", "asset_id": "d3e4f5a6"},
    {"plugin_id": "165890", "name": "nginx < 1.25.4 HTTP/2 Rapid Reset", "severity": "medium", "state": "open", "cve": ["CVE-2023-44487"], "asset": "lb-01", "asset_id": "b7c8d9e0"},
    {"plugin_id": "198765", "name": "jQuery < 3.5.0 XSS Vulnerability", "severity": "medium", "state": "fixed", "cve": ["CVE-2020-11022"], "asset": "web-server-01", "asset_id": "a1b2c3d4"},
    {"plugin_id": "145678", "name": "Docker Engine < 24.0.7 Container Escape", "severity": "critical", "state": "fixed", "cve": ["CVE-2024-9999"], "asset": "k8s-node-01", "asset_id": "f1a2b3c4"},
    {"plugin_id": "167890", "name": "Redis < 7.2.3 Authentication Bypass", "severity": "high", "state": "open", "cve": ["CVE-2024-3456"], "asset": "cache-01", "asset_id": "d5e6f7a8"},
    {"plugin_id": "189012", "name": "Python 3.11.x < 3.11.8 Path Traversal", "severity": "medium", "state": "open", "cve": ["CVE-2024-7890"], "asset": "api-gateway-01", "asset_id": "e5f6a7b8"},
]

DEMO_COMPLIANCE = [
    {"check": "Ensure password minimum length is 14 characters", "status": "PASSED", "expected": "14", "actual": "14", "asset": "dc-01"},
    {"check": "Ensure MFA is enabled for all admin accounts", "status": "PASSED", "expected": "Enabled", "actual": "Enabled", "asset": "idp-01"},
    {"check": "Ensure audit logging is enabled for all systems", "status": "PASSED", "expected": "Enabled", "actual": "Enabled", "asset": "siem-01"},
    {"check": "Ensure TLS 1.2 or higher is enforced", "status": "PASSED", "expected": "TLS 1.2+", "actual": "TLS 1.3", "asset": "lb-01"},
    {"check": "Ensure account lockout threshold is 5 attempts", "status": "PASSED", "expected": "5", "actual": "5", "asset": "dc-01"},
    {"check": "Ensure firewall rules block unauthorized inbound traffic", "status": "FAILED", "expected": "Deny All Inbound", "actual": "Allow 0.0.0.0/0:22", "asset": "web-server-01"},
    {"check": "Ensure remote desktop access requires MFA", "status": "FAILED", "expected": "MFA Required", "actual": "Password Only", "asset": "jump-01"},
    {"check": "Ensure antivirus definitions are updated within 24 hours", "status": "FAILED", "expected": "<24 hours", "actual": "72 hours", "asset": "ws-fleet"},
    {"check": "Ensure session timeout is 15 minutes or less", "status": "PASSED", "expected": "<=15 min", "actual": "10 min", "asset": "app-server-01"},
    {"check": "Ensure backup encryption is enabled", "status": "PASSED", "expected": "AES-256", "actual": "AES-256", "asset": "backup-01"},
    {"check": "Ensure privileged access is reviewed quarterly", "status": "FAILED", "expected": "Quarterly", "actual": "Last review: 8 months ago", "asset": "dc-01"},
    {"check": "Ensure baseline configuration is documented", "status": "PASSED", "expected": "Documented", "actual": "CIS Level 1 Benchmark Applied", "asset": "all-servers"},
]


async def _sync_demo(org_id: str, now: str, user_id: str) -> dict:
    """Generate demo Tenable data for demonstration purposes."""
    mapped_controls = set()

    # Process demo vulnerabilities
    for v in DEMO_VULNS:
        severity = v["severity"]
        state = v["state"]
        if state == "fixed":
            mapping = VULN_FIXED_CONTROLS
        else:
            mapping = VULN_SEVERITY_TO_CONTROLS.get(severity, VULN_SEVERITY_TO_CONTROLS["medium"])

        finding_doc = {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "source": "tenable-demo",
            "finding_type": "vulnerability",
            "tenable_plugin_id": v["plugin_id"],
            "title": v["name"],
            "severity": severity,
            "state": state,
            "cves": v.get("cve", []),
            "asset_uuid": v["asset_id"],
            "asset_hostname": v["asset"],
            "control_ids": mapping["controls"],
            "compliance_status": mapping["status"],
            "reason": mapping["reason"],
            "collected_at": now,
        }
        await db.tenable_findings.update_one(
            {"organization_id": org_id, "tenable_plugin_id": v["plugin_id"], "asset_uuid": v["asset_id"]},
            {"$set": finding_doc},
            upsert=True,
        )
        mapped_controls.update(mapping["controls"])

    # Process demo compliance checks
    for c in DEMO_COMPLIANCE:
        control_ids = _map_compliance_check_to_controls(c["check"])
        compliance_status = "compliant" if c["status"] == "PASSED" else "non_compliant"

        finding_doc = {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "source": "tenable-demo",
            "finding_type": "compliance",
            "title": c["check"],
            "status": c["status"],
            "expected_value": c["expected"],
            "actual_value": c["actual"],
            "asset_uuid": "",
            "asset_hostname": c["asset"],
            "control_ids": control_ids,
            "compliance_status": compliance_status,
            "reason": f"Compliance check {'passed' if c['status'] == 'PASSED' else 'failed'}: {c['check']}",
            "collected_at": now,
        }
        await db.tenable_findings.update_one(
            {"organization_id": org_id, "title": c["check"], "finding_type": "compliance"},
            {"$set": finding_doc},
            upsert=True,
        )
        mapped_controls.update(control_ids)

    # Store sync run
    run_doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "mode": "demo",
        "vulns_processed": len(DEMO_VULNS),
        "compliance_processed": len(DEMO_COMPLIANCE),
        "controls_updated": len(mapped_controls),
        "created_at": now,
    }
    await db.tenable_sync_runs.insert_one(run_doc)

    return {
        "mode": "demo",
        "message": f"Demo sync: {len(DEMO_VULNS)} vulnerabilities and {len(DEMO_COMPLIANCE)} compliance checks loaded",
        "vulns_processed": len(DEMO_VULNS),
        "compliance_processed": len(DEMO_COMPLIANCE),
        "controls_updated": len(mapped_controls),
    }


# ─── Data Endpoints ─────────────────────────────────────

@router.get("/findings")
async def list_tenable_findings(
    finding_type: Optional[str] = None,
    severity: Optional[str] = None,
    status: Optional[str] = None,
    current_user: Dict = Depends(get_current_user)
):
    """List Tenable findings with optional filters."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    query = {"organization_id": org_id}
    if finding_type:
        query["finding_type"] = finding_type
    if severity:
        query["severity"] = severity
    if status:
        query["compliance_status"] = status

    findings = await db.tenable_findings.find(query, {"_id": 0}).sort("collected_at", -1).to_list(500)
    return findings


@router.get("/dashboard")
async def get_tenable_dashboard(current_user: Dict = Depends(get_current_user)):
    """Get Tenable integration dashboard data."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    findings = await db.tenable_findings.find(
        {"organization_id": org_id}, {"_id": 0}
    ).to_list(1000)

    vulns = [f for f in findings if f.get("finding_type") == "vulnerability"]
    compliance = [f for f in findings if f.get("finding_type") == "compliance"]

    # Vuln stats
    vuln_by_severity = {"critical": 0, "high": 0, "medium": 0}
    vuln_by_state = {"open": 0, "reopened": 0, "fixed": 0}
    for v in vulns:
        sev = v.get("severity", "medium")
        if sev in vuln_by_severity:
            vuln_by_severity[sev] += 1
        state = v.get("state", "open")
        if state in vuln_by_state:
            vuln_by_state[state] += 1

    # Compliance stats
    comp_passed = sum(1 for c in compliance if c.get("status") == "PASSED")
    comp_failed = sum(1 for c in compliance if c.get("status") == "FAILED")

    # Control impact
    control_impact = {}
    for f in findings:
        for cid in f.get("control_ids", []):
            if cid not in control_impact:
                control_impact[cid] = {"compliant": 0, "non_compliant": 0, "partial": 0}
            cs = f.get("compliance_status", "non_compliant")
            control_impact[cid][cs] = control_impact[cid].get(cs, 0) + 1

    # Assets
    assets = set()
    for f in findings:
        hostname = f.get("asset_hostname", "")
        if hostname:
            assets.add(hostname)

    # Sync history
    runs = await db.tenable_sync_runs.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(10)

    return {
        "total_findings": len(findings),
        "vulnerabilities": {
            "total": len(vulns),
            "by_severity": vuln_by_severity,
            "by_state": vuln_by_state,
            "open_critical": sum(1 for v in vulns if v.get("severity") == "critical" and v.get("state") in ("open", "reopened")),
        },
        "compliance": {
            "total": len(compliance),
            "passed": comp_passed,
            "failed": comp_failed,
            "pass_rate": round(comp_passed / max(len(compliance), 1) * 100, 1),
        },
        "controls_impacted": len(control_impact),
        "control_impact": dict(sorted(control_impact.items(), key=lambda x: -x[1].get("non_compliant", 0))[:20]),
        "assets_scanned": len(assets),
        "assets": sorted(assets),
        "sync_history": runs,
    }


@router.get("/control-evidence/{control_id}")
async def get_control_evidence(control_id: str, current_user: Dict = Depends(get_current_user)):
    """Get all Tenable evidence for a specific NIST control."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    findings = await db.tenable_findings.find(
        {"organization_id": org_id, "control_ids": control_id}, {"_id": 0}
    ).to_list(200)

    vulns = [f for f in findings if f.get("finding_type") == "vulnerability"]
    compliance = [f for f in findings if f.get("finding_type") == "compliance"]

    return {
        "control_id": control_id,
        "total_evidence": len(findings),
        "vulnerabilities": vulns,
        "compliance_checks": compliance,
        "summary": {
            "vuln_open": sum(1 for v in vulns if v.get("state") in ("open", "reopened")),
            "vuln_fixed": sum(1 for v in vulns if v.get("state") == "fixed"),
            "compliance_passed": sum(1 for c in compliance if c.get("status") == "PASSED"),
            "compliance_failed": sum(1 for c in compliance if c.get("status") == "FAILED"),
        }
    }


@router.get("/sync-history")
async def get_sync_history(current_user: Dict = Depends(get_current_user)):
    """Get Tenable sync run history."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    runs = await db.tenable_sync_runs.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return runs
