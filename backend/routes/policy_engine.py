"""
Policy-as-Code Engine & Compliance Drift Detection
- Define compliance policies as YAML rules
- Evaluate infrastructure configs against policies
- Detect compliance drift from baseline
- Map policy violations to framework controls
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone
import uuid
import re
import json
import logging

import yaml

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/policy-engine", tags=["policy-engine"])


# ─── Models ─────────────────────────────────────────────

class PolicyRule(BaseModel):
    name: str
    description: Optional[str] = ""
    severity: str = "medium"
    category: str = "general"
    condition: str  # YAML or simple rule expression
    control_ids: List[str] = []  # mapped framework control IDs
    tags: List[str] = []

class PolicyRuleSet(BaseModel):
    name: str
    description: Optional[str] = ""
    rules: List[PolicyRule]

class EvaluationRequest(BaseModel):
    config: Dict[str, Any]  # Infrastructure config to evaluate
    config_type: Optional[str] = "generic"  # terraform, k8s, cloudformation, generic
    source: Optional[str] = ""  # e.g., "terraform plan output" or "k8s manifest"


# ─── Built-in Policy Rules ─────────────────────────────────

DEFAULT_RULES = [
    {
        "id": "PAC-001",
        "name": "Encryption at rest required",
        "description": "All storage resources must have encryption enabled",
        "severity": "high",
        "category": "data_protection",
        "check_keys": ["encryption", "encrypted", "kms_key_id", "server_side_encryption"],
        "expected": True,
        "control_ids": ["SC-28", "3.13.16", "Art.32", "164.312(a)(2)(iv)"],
    },
    {
        "id": "PAC-002",
        "name": "MFA required for admin access",
        "description": "Multi-factor authentication must be enabled for administrative accounts",
        "severity": "critical",
        "category": "access_control",
        "check_keys": ["mfa", "mfa_enabled", "multi_factor", "two_factor"],
        "expected": True,
        "control_ids": ["IA-2", "3.5.3", "8.5", "164.312(d)"],
    },
    {
        "id": "PAC-003",
        "name": "Public access restricted",
        "description": "Resources must not be publicly accessible unless explicitly allowed",
        "severity": "high",
        "category": "network_security",
        "check_keys": ["public", "publicly_accessible", "public_access", "ingress_0.0.0.0"],
        "expected": False,
        "control_ids": ["AC-3", "3.1.3", "CC6.6", "SR-AC-3"],
    },
    {
        "id": "PAC-004",
        "name": "Logging enabled",
        "description": "Audit logging must be enabled on all resources",
        "severity": "high",
        "category": "logging",
        "check_keys": ["logging", "audit_logging", "access_logging", "cloudtrail", "flow_logs"],
        "expected": True,
        "control_ids": ["AU-2", "AU-3", "3.3.1", "164.312(b)"],
    },
    {
        "id": "PAC-005",
        "name": "TLS 1.2+ required",
        "description": "All network connections must use TLS 1.2 or higher",
        "severity": "high",
        "category": "network_security",
        "check_keys": ["tls_version", "ssl_version", "min_tls_version", "protocol_version"],
        "expected_values": ["1.2", "1.3", "TLSv1.2", "TLSv1.3", "tls1.2", "tls1.3"],
        "control_ids": ["SC-8", "3.13.8", "4.1", "Art.32"],
    },
    {
        "id": "PAC-006",
        "name": "Backup configuration required",
        "description": "Data backup must be configured with appropriate retention",
        "severity": "medium",
        "category": "availability",
        "check_keys": ["backup", "backup_enabled", "backup_retention", "snapshot"],
        "expected": True,
        "control_ids": ["CP-9", "3.8.9", "A1.2"],
    },
    {
        "id": "PAC-007",
        "name": "No hardcoded secrets",
        "description": "Configuration must not contain hardcoded credentials or API keys",
        "severity": "critical",
        "category": "secret_management",
        "check_patterns": [
            r"(?i)(password|secret|api_key|access_key)\s*[:=]\s*['\"][^'\"]{8,}['\"]",
            r"(?i)(AKIA[A-Z0-9]{16})",
            r"(?i)(sk-[a-zA-Z0-9]{20,})",
        ],
        "control_ids": ["IA-5", "3.5.10", "8.2"],
    },
    {
        "id": "PAC-008",
        "name": "Resource tagging required",
        "description": "All resources must have required tags (environment, owner, project)",
        "severity": "low",
        "category": "governance",
        "check_keys": ["tags"],
        "required_tags": ["environment", "owner", "project"],
        "control_ids": ["CM-8", "3.4.1"],
    },
]


def evaluate_config(config: dict, config_str: str = "") -> list:
    """Evaluate a config against all policy rules."""
    violations = []
    config_flat = _flatten_dict(config)
    config_text = config_str or json.dumps(config)

    for rule in DEFAULT_RULES:
        violation = _check_rule(rule, config, config_flat, config_text)
        if violation:
            violations.append(violation)

    return violations


def _flatten_dict(d: dict, parent_key: str = "", sep: str = ".") -> dict:
    """Flatten nested dict for key searching."""
    items = {}
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(_flatten_dict(v, new_key, sep))
        elif isinstance(v, list):
            for i, item in enumerate(v):
                if isinstance(item, dict):
                    items.update(_flatten_dict(item, f"{new_key}[{i}]", sep))
                else:
                    items[f"{new_key}[{i}]"] = item
        else:
            items[new_key] = v
    return items


def _check_rule(rule: dict, config: dict, config_flat: dict, config_text: str) -> dict | None:
    """Check a single rule against config. Returns violation dict or None."""
    rule_id = rule["id"]

    # Pattern-based check (e.g., hardcoded secrets)
    if "check_patterns" in rule:
        for pattern in rule["check_patterns"]:
            matches = re.findall(pattern, config_text)
            if matches:
                return {
                    "rule_id": rule_id,
                    "name": rule["name"],
                    "description": rule["description"],
                    "severity": rule["severity"],
                    "category": rule["category"],
                    "violation": f"Pattern match found: {matches[0][:30]}...",
                    "control_ids": rule.get("control_ids", []),
                }
        return None

    # Key-based check
    if "check_keys" not in rule:
        return None

    found_keys = {}
    for check_key in rule["check_keys"]:
        for flat_key, flat_val in config_flat.items():
            if check_key.lower() in flat_key.lower():
                found_keys[flat_key] = flat_val

    if not found_keys:
        # Key not found — could be a violation if expected to be True
        if rule.get("expected") is True:
            return {
                "rule_id": rule_id,
                "name": rule["name"],
                "description": rule["description"],
                "severity": rule["severity"],
                "category": rule["category"],
                "violation": f"Required configuration not found: {rule['check_keys']}",
                "control_ids": rule.get("control_ids", []),
            }
        return None

    # Check expected values
    if "expected_values" in rule:
        for key, val in found_keys.items():
            if str(val) not in [str(ev) for ev in rule["expected_values"]]:
                return {
                    "rule_id": rule_id,
                    "name": rule["name"],
                    "description": rule["description"],
                    "severity": rule["severity"],
                    "category": rule["category"],
                    "violation": f"{key} = {val} (expected one of: {rule['expected_values']})",
                    "control_ids": rule.get("control_ids", []),
                }
        return None

    # Check expected boolean
    if "expected" in rule:
        expected = rule["expected"]
        for key, val in found_keys.items():
            actual = _to_bool(val)
            if actual != expected:
                return {
                    "rule_id": rule_id,
                    "name": rule["name"],
                    "description": rule["description"],
                    "severity": rule["severity"],
                    "category": rule["category"],
                    "violation": f"{key} = {val} (expected: {expected})",
                    "control_ids": rule.get("control_ids", []),
                }

    # Tag check
    if "required_tags" in rule:
        for key, val in found_keys.items():
            if isinstance(val, dict):
                missing = [t for t in rule["required_tags"] if t not in val]
                if missing:
                    return {
                        "rule_id": rule_id,
                        "name": rule["name"],
                        "description": rule["description"],
                        "severity": rule["severity"],
                        "category": rule["category"],
                        "violation": f"Missing required tags: {missing}",
                        "control_ids": rule.get("control_ids", []),
                    }

    return None


def _to_bool(val) -> bool:
    """Convert various values to boolean."""
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("true", "yes", "1", "enabled", "on")
    return bool(val)


# ─── Endpoints ─────────────────────────────────────────────

@router.get("/rules")
async def list_policy_rules(current_user: Dict = Depends(get_current_user)):
    """List all active policy-as-code rules."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    # Get custom rules
    custom = await db.policy_rules.find(
        {"organization_id": org_id}, {"_id": 0}
    ).to_list(200)

    return {
        "builtin_rules": DEFAULT_RULES,
        "custom_rules": custom,
        "total": len(DEFAULT_RULES) + len(custom),
    }


@router.post("/rules")
async def create_custom_rule(rule: PolicyRule, current_user: Dict = Depends(get_current_user)):
    """Create a custom policy-as-code rule."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()

    rule_doc = {
        "id": f"CUSTOM-{str(uuid.uuid4())[:8].upper()}",
        "organization_id": org_id,
        "name": rule.name,
        "description": rule.description,
        "severity": rule.severity,
        "category": rule.category,
        "condition": rule.condition,
        "control_ids": rule.control_ids,
        "tags": rule.tags,
        "active": True,
        "created_at": now,
        "created_by": current_user["id"],
    }
    await db.policy_rules.insert_one(rule_doc)
    del rule_doc["_id"]
    return rule_doc


@router.post("/evaluate")
async def evaluate_config_endpoint(req: EvaluationRequest, current_user: Dict = Depends(get_current_user)):
    """Evaluate an infrastructure config against policy rules."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    violations = evaluate_config(req.config)

    # Store evaluation result
    now = datetime.now(timezone.utc).isoformat()
    eval_id = str(uuid.uuid4())
    eval_doc = {
        "id": eval_id,
        "organization_id": org_id,
        "config_type": req.config_type,
        "source": req.source,
        "total_rules_checked": len(DEFAULT_RULES),
        "violations": violations,
        "violation_count": len(violations),
        "severity_counts": {
            "critical": sum(1 for v in violations if v["severity"] == "critical"),
            "high": sum(1 for v in violations if v["severity"] == "high"),
            "medium": sum(1 for v in violations if v["severity"] == "medium"),
            "low": sum(1 for v in violations if v["severity"] == "low"),
        },
        "pass": len(violations) == 0,
        "created_at": now,
        "created_by": current_user["id"],
    }
    await db.policy_evaluations.insert_one(eval_doc)
    del eval_doc["_id"]
    return eval_doc


@router.get("/evaluations")
async def list_evaluations(current_user: Dict = Depends(get_current_user)):
    """List recent policy evaluations."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    evals = await db.policy_evaluations.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return evals


# ─── Compliance Drift Detection ───────────────────────────

@router.post("/drift/snapshot")
async def create_drift_snapshot(current_user: Dict = Depends(get_current_user)):
    """Create a compliance baseline snapshot for drift detection."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()

    # Capture current state of all compliance data
    frameworks = await db.frameworks.find({"type": "standard"}, {"_id": 0}).to_list(100)
    snapshot_data = {}

    for fw in frameworks:
        compliance = await db.control_compliance.find(
            {"organization_id": org_id, "framework_id": fw["id"]}, {"_id": 0}
        ).to_list(5000)

        controls_state = {}
        for c in compliance:
            controls_state[c["control_id"]] = {
                "status": c.get("status", "not_assessed"),
                "is_user_override": c.get("is_user_override", False),
            }

        total = await db.controls.count_documents({"framework_id": fw["id"]})
        compliant = sum(1 for c in controls_state.values() if c["status"] == "compliant")
        snapshot_data[fw["id"]] = {
            "framework_name": fw["name"],
            "total_controls": total,
            "compliant": compliant,
            "controls": controls_state,
        }

    # Pipeline state
    pipeline_runs = await db.pipeline_runs.find(
        {"organization_id": org_id}, {"_id": 0}
    ).to_list(100)
    pipeline_state = {
        "total_runs": len(pipeline_runs),
        "total_findings": sum(r.get("total_findings", 0) for r in pipeline_runs),
        "failed_gates": sum(1 for r in pipeline_runs if r.get("gate_result") == "fail"),
    }

    # Ingestion state
    ingested_total = await db.ingested_controls.count_documents({"organization_id": org_id})
    ingested_mapped = await db.ingested_controls.count_documents(
        {"organization_id": org_id, "status": "mapped"}
    )

    snapshot = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "frameworks": snapshot_data,
        "pipeline": pipeline_state,
        "ingestion": {"total": ingested_total, "mapped": ingested_mapped},
        "created_at": now,
        "created_by": current_user["id"],
    }
    await db.compliance_snapshots.insert_one(snapshot)
    del snapshot["_id"]
    return {"snapshot_id": snapshot["id"], "message": "Baseline snapshot created", "frameworks_captured": len(snapshot_data)}


@router.get("/drift/detect")
async def detect_compliance_drift(current_user: Dict = Depends(get_current_user)):
    """Compare current compliance state against last baseline snapshot."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    # Get latest snapshot
    snapshot = await db.compliance_snapshots.find_one(
        {"organization_id": org_id}, {"_id": 0},
        sort=[("created_at", -1)]
    )
    if not snapshot:
        return {"drift_detected": False, "message": "No baseline snapshot found. Create one first.", "changes": []}

    changes = []
    frameworks = await db.frameworks.find({"type": "standard"}, {"_id": 0}).to_list(100)

    for fw in frameworks:
        fw_id = fw["id"]
        baseline = snapshot.get("frameworks", {}).get(fw_id, {})
        if not baseline:
            continue

        # Current state
        compliance = await db.control_compliance.find(
            {"organization_id": org_id, "framework_id": fw_id}, {"_id": 0}
        ).to_list(5000)
        current_controls = {}
        for c in compliance:
            current_controls[c["control_id"]] = c.get("status", "not_assessed")

        baseline_controls = baseline.get("controls", {})

        # Detect changes
        for ctrl_id, current_status in current_controls.items():
            baseline_status = baseline_controls.get(ctrl_id, {}).get("status", "not_assessed")
            if current_status != baseline_status:
                is_improvement = (
                    (baseline_status == "non_compliant" and current_status in ["partial", "compliant"]) or
                    (baseline_status == "partial" and current_status == "compliant") or
                    (baseline_status == "not_assessed" and current_status in ["partial", "compliant"])
                )
                changes.append({
                    "framework_name": fw["name"],
                    "framework_id": fw_id,
                    "control_id": ctrl_id,
                    "previous_status": baseline_status,
                    "current_status": current_status,
                    "direction": "improved" if is_improvement else "degraded",
                })

    # Check pipeline drift
    pipeline_baseline = snapshot.get("pipeline", {})
    current_pipeline = await db.pipeline_runs.find(
        {"organization_id": org_id}, {"_id": 0}
    ).to_list(100)
    current_failed = sum(1 for r in current_pipeline if r.get("gate_result") == "fail")
    baseline_failed = pipeline_baseline.get("failed_gates", 0)
    if current_failed > baseline_failed:
        changes.append({
            "framework_name": "Pipeline Security",
            "framework_id": "pipeline",
            "control_id": "gate_failures",
            "previous_status": f"{baseline_failed} failures",
            "current_status": f"{current_failed} failures",
            "direction": "degraded",
        })

    improved = sum(1 for c in changes if c["direction"] == "improved")
    degraded = sum(1 for c in changes if c["direction"] == "degraded")

    return {
        "drift_detected": len(changes) > 0,
        "changes": changes,
        "summary": {
            "total_changes": len(changes),
            "improved": improved,
            "degraded": degraded,
        },
        "baseline_date": snapshot.get("created_at", ""),
    }


@router.get("/drift/snapshots")
async def list_snapshots(current_user: Dict = Depends(get_current_user)):
    """List all compliance snapshots."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    snapshots = await db.compliance_snapshots.find(
        {"organization_id": org_id}, {"_id": 0, "frameworks": 0}
    ).sort("created_at", -1).to_list(50)
    return snapshots
