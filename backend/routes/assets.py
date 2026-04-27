"""
Asset Inventory Module
- First-class assets collection (hardware + software + metadata)
- Auto-populated from Tenable sync; supports manual CRUD
- Asset criticality (low/medium/high/critical) drives Risk Scoring multiplier
- Per-asset vulnerability + compliance lookup
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from datetime import datetime, timezone
import uuid
import logging

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/assets", tags=["assets"])


# ─── Models ─────────────────────────────────────────────

CRITICALITY_OPTIONS = ["low", "medium", "high", "critical"]
ENVIRONMENT_OPTIONS = ["production", "staging", "development", "test", "dr", "unknown"]


class AssetCreate(BaseModel):
    hostname: str
    fqdn: Optional[str] = None
    ip_addresses: List[str] = Field(default_factory=list)
    mac_addresses: List[str] = Field(default_factory=list)
    operating_system: Optional[str] = None
    os_version: Optional[str] = None
    system_type: Optional[str] = None  # server, workstation, container, network-device, mobile, iot
    installed_software: List[Dict] = Field(default_factory=list)  # [{name, version}]
    services: List[Dict] = Field(default_factory=list)  # [{name, port, protocol}]
    open_ports: List[int] = Field(default_factory=list)
    criticality: str = "medium"
    environment: str = "production"
    owner: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    notes: Optional[str] = None


class AssetUpdate(BaseModel):
    hostname: Optional[str] = None
    fqdn: Optional[str] = None
    ip_addresses: Optional[List[str]] = None
    mac_addresses: Optional[List[str]] = None
    operating_system: Optional[str] = None
    os_version: Optional[str] = None
    system_type: Optional[str] = None
    installed_software: Optional[List[Dict]] = None
    services: Optional[List[Dict]] = None
    open_ports: Optional[List[int]] = None
    criticality: Optional[str] = None
    environment: Optional[str] = None
    owner: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None


# ─── Helper: Upsert Asset (used by Tenable sync) ─────────

async def upsert_asset_from_tenable(
    org_id: str,
    asset_uuid: str,
    hostname: str,
    now: str,
    extra: Optional[Dict] = None,
) -> str:
    """
    Idempotent: creates an asset record on first sight, updates last_seen on subsequent sights.
    Returns the internal asset id.
    Manual fields (criticality, owner, environment, notes, tags) are NEVER overwritten by Tenable.
    """
    if not hostname and not asset_uuid:
        return ""

    extra = extra or {}
    # Match by tenable uuid first, then hostname
    query = {"organization_id": org_id}
    if asset_uuid:
        query["asset_uuid"] = asset_uuid
    else:
        query["hostname"] = hostname

    existing = await db.assets.find_one(query, {"_id": 0})

    if existing:
        # Update only Tenable-discovered fields; preserve user metadata
        update_set = {
            "last_seen": now,
            "hostname": hostname or existing.get("hostname"),
        }
        if asset_uuid and not existing.get("asset_uuid"):
            update_set["asset_uuid"] = asset_uuid
        for k in (
            "fqdn", "ip_addresses", "mac_addresses",
            "operating_system", "os_version", "system_type",
            "installed_software", "services", "open_ports",
        ):
            if extra.get(k) is not None:
                update_set[k] = extra[k]

        await db.assets.update_one(
            {"id": existing["id"]},
            {"$set": update_set, "$addToSet": {"sources": "tenable"}},
        )
        return existing["id"]

    # New asset
    asset_id = str(uuid.uuid4())
    doc = {
        "id": asset_id,
        "organization_id": org_id,
        "hostname": hostname,
        "asset_uuid": asset_uuid or "",
        "fqdn": extra.get("fqdn", ""),
        "ip_addresses": extra.get("ip_addresses", []),
        "mac_addresses": extra.get("mac_addresses", []),
        "operating_system": extra.get("operating_system", ""),
        "os_version": extra.get("os_version", ""),
        "system_type": extra.get("system_type", "server"),
        "installed_software": extra.get("installed_software", []),
        "services": extra.get("services", []),
        "open_ports": extra.get("open_ports", []),
        "criticality": "medium",
        "environment": "production",
        "owner": "",
        "tags": [],
        "notes": "",
        "sources": ["tenable"],
        "first_seen": now,
        "last_seen": now,
        "created_at": now,
        "updated_at": now,
    }
    await db.assets.insert_one(doc)
    return asset_id


# ─── List + Stats ────────────────────────────────────────

@router.get("/stats")
async def get_asset_stats(current_user: Dict = Depends(get_current_user)):
    """Asset inventory summary stats."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    assets = await db.assets.find(
        {"organization_id": org_id}, {"_id": 0}
    ).to_list(5000)

    by_criticality = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    by_environment = {}
    by_os = {}
    by_system_type = {}

    for a in assets:
        c = a.get("criticality", "medium")
        by_criticality[c] = by_criticality.get(c, 0) + 1
        e = a.get("environment", "unknown")
        by_environment[e] = by_environment.get(e, 0) + 1
        os_full = (a.get("operating_system") or "").strip()
        if not os_full:
            os_name = "Unknown"
        else:
            # Take first 2 tokens for friendly family ("Amazon Linux", "Red Hat", "Ubuntu 22.04")
            tokens = os_full.split(" ")
            if len(tokens) >= 2 and tokens[0] in ("Red", "Amazon", "Alpine", "Kali", "Oracle"):
                os_name = " ".join(tokens[:2])
            else:
                os_name = tokens[0]
        by_os[os_name] = by_os.get(os_name, 0) + 1
        st = a.get("system_type", "server")
        by_system_type[st] = by_system_type.get(st, 0) + 1

    # Vulnerable asset count (any open vuln finding)
    vuln_assets = await db.tenable_findings.distinct(
        "asset_hostname",
        {
            "organization_id": org_id,
            "finding_type": "vulnerability",
            "state": {"$in": ["open", "reopened"]},
        },
    )

    return {
        "total_assets": len(assets),
        "vulnerable_assets": len([h for h in vuln_assets if h]),
        "by_criticality": by_criticality,
        "by_environment": by_environment,
        "by_os": by_os,
        "by_system_type": by_system_type,
    }


@router.get("")
async def list_assets(
    criticality: Optional[str] = None,
    environment: Optional[str] = None,
    search: Optional[str] = None,
    has_open_vulns: Optional[bool] = None,
    current_user: Dict = Depends(get_current_user),
):
    """List all assets with optional filters + per-asset vuln summary."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    query = {"organization_id": org_id}
    if criticality:
        query["criticality"] = criticality
    if environment:
        query["environment"] = environment
    if search:
        query["$or"] = [
            {"hostname": {"$regex": search, "$options": "i"}},
            {"fqdn": {"$regex": search, "$options": "i"}},
            {"owner": {"$regex": search, "$options": "i"}},
            {"tags": {"$regex": search, "$options": "i"}},
        ]

    assets = await db.assets.find(query, {"_id": 0}).sort("last_seen", -1).to_list(2000)

    # Annotate with vulnerability counts
    findings = await db.tenable_findings.find(
        {"organization_id": org_id, "finding_type": "vulnerability"}, {"_id": 0}
    ).to_list(10000)

    vuln_by_host = {}
    for f in findings:
        h = f.get("asset_hostname", "")
        if not h:
            continue
        bucket = vuln_by_host.setdefault(h, {"open_critical": 0, "open_high": 0, "open_medium": 0, "fixed": 0, "total_open": 0})
        sev = f.get("severity", "medium")
        state = f.get("state", "open")
        if state == "fixed":
            bucket["fixed"] += 1
        elif state in ("open", "reopened"):
            bucket["total_open"] += 1
            if sev == "critical":
                bucket["open_critical"] += 1
            elif sev == "high":
                bucket["open_high"] += 1
            elif sev == "medium":
                bucket["open_medium"] += 1

    for a in assets:
        v = vuln_by_host.get(a.get("hostname", ""), {"open_critical": 0, "open_high": 0, "open_medium": 0, "fixed": 0, "total_open": 0})
        a["vuln_summary"] = v
        a["software_count"] = len(a.get("installed_software", []))

    if has_open_vulns is True:
        assets = [a for a in assets if a["vuln_summary"]["total_open"] > 0]
    elif has_open_vulns is False:
        assets = [a for a in assets if a["vuln_summary"]["total_open"] == 0]

    return assets


@router.get("/{asset_id}")
async def get_asset(asset_id: str, current_user: Dict = Depends(get_current_user)):
    """Get a single asset's full record with vulnerabilities + compliance."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    asset = await db.assets.find_one(
        {"id": asset_id, "organization_id": org_id}, {"_id": 0}
    )
    if not asset:
        raise HTTPException(404, "Asset not found")

    # Findings: match by asset_uuid OR hostname
    match_clauses = []
    if asset.get("asset_uuid"):
        match_clauses.append({"asset_uuid": asset["asset_uuid"]})
    if asset.get("hostname"):
        match_clauses.append({"asset_hostname": asset["hostname"]})

    findings = []
    if match_clauses:
        findings = await db.tenable_findings.find(
            {"organization_id": org_id, "$or": match_clauses}, {"_id": 0}
        ).sort("collected_at", -1).to_list(500)

    vulns = [f for f in findings if f.get("finding_type") == "vulnerability"]
    compliance = [f for f in findings if f.get("finding_type") == "compliance"]

    open_vulns = [v for v in vulns if v.get("state") in ("open", "reopened")]
    fixed_vulns = [v for v in vulns if v.get("state") == "fixed"]

    # POA&M entries for this asset
    poam = await db.poam_entries.find(
        {"organization_id": org_id, "asset": asset["hostname"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)

    return {
        "asset": asset,
        "vulnerabilities": {
            "open": open_vulns,
            "fixed": fixed_vulns,
            "summary": {
                "open_critical": sum(1 for v in open_vulns if v.get("severity") == "critical"),
                "open_high": sum(1 for v in open_vulns if v.get("severity") == "high"),
                "open_medium": sum(1 for v in open_vulns if v.get("severity") == "medium"),
                "fixed_total": len(fixed_vulns),
            },
        },
        "compliance_checks": compliance,
        "poam_entries": poam,
    }


@router.post("")
async def create_asset(payload: AssetCreate, current_user: Dict = Depends(get_current_user)):
    """Manually create an asset."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()

    if payload.criticality not in CRITICALITY_OPTIONS:
        raise HTTPException(400, f"criticality must be one of {CRITICALITY_OPTIONS}")
    if payload.environment not in ENVIRONMENT_OPTIONS:
        raise HTTPException(400, f"environment must be one of {ENVIRONMENT_OPTIONS}")

    asset_id = str(uuid.uuid4())
    doc = payload.model_dump()
    doc.update({
        "id": asset_id,
        "organization_id": org_id,
        "asset_uuid": "",
        "sources": ["manual"],
        "first_seen": now,
        "last_seen": now,
        "created_at": now,
        "updated_at": now,
    })
    await db.assets.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/{asset_id}")
async def update_asset(asset_id: str, payload: AssetUpdate, current_user: Dict = Depends(get_current_user)):
    """Update an asset (manual fields like criticality, owner, environment)."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()

    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if "criticality" in update and update["criticality"] not in CRITICALITY_OPTIONS:
        raise HTTPException(400, f"criticality must be one of {CRITICALITY_OPTIONS}")
    if "environment" in update and update["environment"] not in ENVIRONMENT_OPTIONS:
        raise HTTPException(400, f"environment must be one of {ENVIRONMENT_OPTIONS}")

    update["updated_at"] = now
    result = await db.assets.update_one(
        {"id": asset_id, "organization_id": org_id},
        {"$set": update},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Asset not found")

    asset = await db.assets.find_one({"id": asset_id}, {"_id": 0})
    return asset


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str, current_user: Dict = Depends(get_current_user)):
    """Delete an asset."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    result = await db.assets.delete_one({"id": asset_id, "organization_id": org_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Asset not found")
    return {"message": "Asset deleted"}


@router.post("/backfill-from-tenable")
async def backfill_assets_from_tenable(current_user: Dict = Depends(get_current_user)):
    """One-shot: build asset records from existing Tenable findings (for orgs that synced before assets module existed)."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()

    findings = await db.tenable_findings.find(
        {"organization_id": org_id}, {"_id": 0}
    ).to_list(10000)

    seen = {}
    for f in findings:
        host = f.get("asset_hostname", "")
        uid = f.get("asset_uuid", "")
        if not host:
            continue
        key = uid or host
        if key in seen:
            continue
        seen[key] = True
        await upsert_asset_from_tenable(org_id, uid, host, now)

    total = await db.assets.count_documents({"organization_id": org_id})
    return {"message": f"Backfilled {len(seen)} unique assets from findings", "total_assets": total}
