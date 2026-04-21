"""
CI/CD Pipeline Integration - DevSecOps Compliance Gate
- Webhook endpoint for receiving scan results from CI/CD tools
- Compliance gate evaluation against mapped controls
- Pipeline run tracking and findings management
- API key authentication for pipeline tools
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone
import uuid
import hashlib
import secrets
import logging

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/pipeline", tags=["pipeline"])


# ─── Models ─────────────────────────────────────────────

class ScanFinding(BaseModel):
    id: Optional[str] = None
    title: str
    description: Optional[str] = ""
    severity: str = "medium"  # critical, high, medium, low, info
    category: str = "general"  # sast, dast, sca, container, iac, secret, compliance
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    cwe_id: Optional[str] = None
    cve_id: Optional[str] = None
    package_name: Optional[str] = None
    package_version: Optional[str] = None
    tool: Optional[str] = None
    remediation: Optional[str] = None

class WebhookPayload(BaseModel):
    pipeline_name: str
    run_id: Optional[str] = None
    repo: Optional[str] = None
    branch: Optional[str] = None
    commit_sha: Optional[str] = None
    scan_type: str  # sast, dast, sca, container, iac, mixed
    tool_name: Optional[str] = None
    findings: List[ScanFinding] = []
    metadata: Optional[Dict[str, Any]] = {}
    artifact_url: Optional[str] = None

class GateRequest(BaseModel):
    run_id: str
    policy: Optional[str] = "default"  # default, strict, permissive

class ApiKeyCreate(BaseModel):
    name: str
    description: Optional[str] = ""


# ─── Severity scoring ─────────────────────────────────────

SEVERITY_WEIGHTS = {"critical": 10, "high": 5, "medium": 2, "low": 1, "info": 0}

# Control category mappings for scan types
SCAN_TO_CONTROL_CATEGORIES = {
    "sast": ["system", "policy_change"],
    "dast": ["authentication", "authorization", "data_access"],
    "sca": ["system", "risk_management"],
    "container": ["system", "policy_change"],
    "iac": ["policy_change", "authorization", "system"],
    "secret": ["authentication", "data_access"],
    "compliance": ["risk_management", "policy_change"],
    "mixed": ["system", "authentication", "data_access", "policy_change"],
}


# ─── API Key Auth ─────────────────────────────────────────

async def verify_pipeline_key(x_pipeline_key: str = Header(None), authorization: str = Header(None)):
    """Verify pipeline API key or fall back to JWT auth."""
    if x_pipeline_key:
        key_hash = hashlib.sha256(x_pipeline_key.encode()).hexdigest()
        key_doc = await db.pipeline_api_keys.find_one({"key_hash": key_hash, "active": True})
        if not key_doc:
            raise HTTPException(401, "Invalid pipeline API key")
        # Update last used
        await db.pipeline_api_keys.update_one(
            {"key_hash": key_hash},
            {"$set": {"last_used": datetime.now(timezone.utc).isoformat()}, "$inc": {"usage_count": 1}}
        )
        return {"id": key_doc["created_by"], "org_id": key_doc["organization_id"], "source": "pipeline_key"}
    raise HTTPException(401, "Pipeline API key required (X-Pipeline-Key header)")


# ─── Webhook Endpoint ─────────────────────────────────────

@router.post("/webhook")
async def receive_scan_results(payload: WebhookPayload, auth=Depends(verify_pipeline_key)):
    """Receive scan results from CI/CD pipeline tools."""
    org_id = auth.get("org_id", "")
    now = datetime.now(timezone.utc).isoformat()
    run_id = payload.run_id or str(uuid.uuid4())

    # Calculate severity summary
    severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0}
    for f in payload.findings:
        sev = f.severity.lower()
        if sev in severity_counts:
            severity_counts[sev] += 1

    risk_score = sum(severity_counts[s] * SEVERITY_WEIGHTS[s] for s in severity_counts)

    # Store pipeline run
    run_doc = {
        "id": run_id,
        "organization_id": org_id,
        "pipeline_name": payload.pipeline_name,
        "repo": payload.repo or "",
        "branch": payload.branch or "",
        "commit_sha": payload.commit_sha or "",
        "scan_type": payload.scan_type,
        "tool_name": payload.tool_name or "",
        "total_findings": len(payload.findings),
        "severity_counts": severity_counts,
        "risk_score": risk_score,
        "status": "received",
        "gate_result": None,
        "metadata": payload.metadata or {},
        "artifact_url": payload.artifact_url or "",
        "created_at": now,
        "created_by": auth["id"],
    }

    # Check if run already exists (update)
    existing = await db.pipeline_runs.find_one({"id": run_id, "organization_id": org_id})
    if existing:
        await db.pipeline_runs.update_one(
            {"id": run_id},
            {"$set": {
                "total_findings": len(payload.findings),
                "severity_counts": severity_counts,
                "risk_score": risk_score,
                "updated_at": now,
            }}
        )
    else:
        await db.pipeline_runs.insert_one(run_doc)

    # Store individual findings
    for f in payload.findings:
        finding_doc = {
            "id": f.id or str(uuid.uuid4()),
            "run_id": run_id,
            "organization_id": org_id,
            "title": f.title,
            "description": f.description or "",
            "severity": f.severity.lower(),
            "category": f.category.lower(),
            "file_path": f.file_path or "",
            "line_number": f.line_number,
            "cwe_id": f.cwe_id or "",
            "cve_id": f.cve_id or "",
            "package_name": f.package_name or "",
            "package_version": f.package_version or "",
            "tool": f.tool or payload.tool_name or "",
            "remediation": f.remediation or "",
            "control_mappings": [],
            "created_at": now,
        }
        await db.pipeline_findings.insert_one(finding_doc)

    # Map findings to SIEM categories for cross-reference
    siem_categories = SCAN_TO_CONTROL_CATEGORIES.get(payload.scan_type, ["system"])

    if existing:
        del run_doc["_id"]

    return {
        "run_id": run_id,
        "status": "received",
        "total_findings": len(payload.findings),
        "severity_counts": severity_counts,
        "risk_score": risk_score,
        "siem_categories": siem_categories,
        "message": f"Received {len(payload.findings)} findings from {payload.pipeline_name}"
    }


# ─── Compliance Gate ──────────────────────────────────────

@router.post("/gate")
async def evaluate_compliance_gate(req: GateRequest, auth=Depends(verify_pipeline_key)):
    """Evaluate compliance gate for a pipeline run. Returns pass/fail/warn."""
    org_id = auth.get("org_id", "")

    run = await db.pipeline_runs.find_one({"id": req.run_id, "organization_id": org_id}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Pipeline run not found")

    sev = run.get("severity_counts", {})

    # Policy thresholds
    policies = {
        "strict": {"critical": 0, "high": 0, "medium": 5, "risk_score": 10},
        "default": {"critical": 0, "high": 3, "medium": 10, "risk_score": 30},
        "permissive": {"critical": 1, "high": 10, "medium": 50, "risk_score": 100},
    }
    thresholds = policies.get(req.policy, policies["default"])

    # Evaluate
    violations = []
    if sev.get("critical", 0) > thresholds["critical"]:
        violations.append(f"Critical findings: {sev['critical']} (max: {thresholds['critical']})")
    if sev.get("high", 0) > thresholds["high"]:
        violations.append(f"High findings: {sev['high']} (max: {thresholds['high']})")
    if sev.get("medium", 0) > thresholds["medium"]:
        violations.append(f"Medium findings: {sev['medium']} (max: {thresholds['medium']})")
    if run.get("risk_score", 0) > thresholds["risk_score"]:
        violations.append(f"Risk score: {run['risk_score']} (max: {thresholds['risk_score']})")

    if not violations:
        gate_result = "pass"
    elif sev.get("critical", 0) > thresholds["critical"]:
        gate_result = "fail"
    else:
        gate_result = "warn"

    # Update run with gate result
    await db.pipeline_runs.update_one(
        {"id": req.run_id, "organization_id": org_id},
        {"$set": {
            "gate_result": gate_result,
            "gate_policy": req.policy,
            "gate_violations": violations,
            "gate_evaluated_at": datetime.now(timezone.utc).isoformat(),
        }}
    )

    return {
        "run_id": req.run_id,
        "gate_result": gate_result,
        "policy": req.policy,
        "violations": violations,
        "severity_counts": sev,
        "risk_score": run.get("risk_score", 0),
        "thresholds": thresholds,
    }


# ─── Pipeline Runs ────────────────────────────────────────

@router.get("/runs")
async def list_pipeline_runs(current_user: Dict = Depends(get_current_user)):
    """List all pipeline runs for the organization."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    runs = await db.pipeline_runs.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)
    return runs


@router.get("/runs/{run_id}")
async def get_pipeline_run(run_id: str, current_user: Dict = Depends(get_current_user)):
    """Get pipeline run details with findings."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    run = await db.pipeline_runs.find_one({"id": run_id, "organization_id": org_id}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Pipeline run not found")

    findings = await db.pipeline_findings.find(
        {"run_id": run_id, "organization_id": org_id}, {"_id": 0}
    ).to_list(1000)

    # Group findings by category
    by_category = {}
    for f in findings:
        cat = f.get("category", "general")
        by_category.setdefault(cat, []).append(f)

    return {
        "run": run,
        "findings": findings,
        "findings_by_category": {k: len(v) for k, v in by_category.items()},
    }


@router.delete("/runs/{run_id}")
async def delete_pipeline_run(run_id: str, current_user: Dict = Depends(get_current_user)):
    """Delete a pipeline run and its findings."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    result = await db.pipeline_runs.delete_one({"id": run_id, "organization_id": org_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Pipeline run not found")
    await db.pipeline_findings.delete_many({"run_id": run_id, "organization_id": org_id})
    return {"message": "Pipeline run deleted"}


# ─── Pipeline Stats ───────────────────────────────────────

@router.get("/stats")
async def get_pipeline_stats(current_user: Dict = Depends(get_current_user)):
    """Get aggregate pipeline statistics."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    runs = await db.pipeline_runs.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(200)

    total_runs = len(runs)
    total_findings = sum(r.get("total_findings", 0) for r in runs)
    gate_results = {"pass": 0, "fail": 0, "warn": 0, "pending": 0}
    scan_types = {}
    recent_risk_scores = []

    for r in runs:
        gr = r.get("gate_result")
        if gr in gate_results:
            gate_results[gr] += 1
        else:
            gate_results["pending"] += 1

        st = r.get("scan_type", "unknown")
        scan_types[st] = scan_types.get(st, 0) + 1

        if r.get("risk_score") is not None:
            recent_risk_scores.append({
                "run_id": r["id"],
                "pipeline": r.get("pipeline_name", ""),
                "risk_score": r["risk_score"],
                "date": r.get("created_at", ""),
            })

    avg_risk = sum(r["risk_score"] for r in recent_risk_scores) / len(recent_risk_scores) if recent_risk_scores else 0

    return {
        "total_runs": total_runs,
        "total_findings": total_findings,
        "gate_results": gate_results,
        "scan_types": scan_types,
        "average_risk_score": round(avg_risk, 1),
        "recent_risk_trend": recent_risk_scores[:10],
        "pass_rate": round(gate_results["pass"] / total_runs * 100, 1) if total_runs > 0 else 0,
    }


# ─── API Key Management ──────────────────────────────────

@router.post("/api-keys")
async def create_api_key(data: ApiKeyCreate, current_user: Dict = Depends(get_current_user)):
    """Generate a new pipeline API key."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    raw_key = f"iv-pipe-{secrets.token_hex(24)}"
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    key_doc = {
        "id": str(uuid.uuid4()),
        "name": data.name,
        "description": data.description or "",
        "key_hash": key_hash,
        "key_prefix": raw_key[:12] + "...",
        "organization_id": org_id,
        "active": True,
        "usage_count": 0,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user["id"],
        "last_used": None,
    }
    await db.pipeline_api_keys.insert_one(key_doc)
    del key_doc["_id"]

    return {
        "key": raw_key,
        "key_id": key_doc["id"],
        "name": data.name,
        "message": "API key created. Store it securely — it won't be shown again.",
    }


@router.get("/api-keys")
async def list_api_keys(current_user: Dict = Depends(get_current_user)):
    """List pipeline API keys (without the actual key)."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    keys = await db.pipeline_api_keys.find(
        {"organization_id": org_id}, {"_id": 0, "key_hash": 0}
    ).to_list(50)
    return keys


@router.delete("/api-keys/{key_id}")
async def revoke_api_key(key_id: str, current_user: Dict = Depends(get_current_user)):
    """Revoke (deactivate) a pipeline API key."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    result = await db.pipeline_api_keys.update_one(
        {"id": key_id, "organization_id": org_id},
        {"$set": {"active": False, "revoked_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.modified_count == 0:
        raise HTTPException(404, "API key not found")
    return {"message": "API key revoked"}
