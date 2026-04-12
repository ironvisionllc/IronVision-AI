"""
Policy Templates — Pre-built GRC policy templates with org profile,
cross-framework mapping, and SIEM threshold suggestions.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Optional, List
from datetime import datetime, timezone
import uuid
import os
import re
import json
import logging
import difflib

from emergentintegrations.llm.chat import LlmChat, UserMessage
from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/policy-templates", tags=["policy-templates"])

# ─── Template Catalog ───
TEMPLATES = [
    {
        "id": "access-control",
        "title": "Access Control Policy",
        "description": "Defines rules for user access provisioning, authentication, authorization, and account management.",
        "category": "Security",
        "frameworks": {"NIST 800-53": ["AC-1","AC-2","AC-3","AC-6","AC-7","AC-17"], "NIST CSF": ["PR.AC-1","PR.AC-3","PR.AC-4","PR.AC-5","PR.AC-7"], "GDPR": ["Art.25","Art.32"]},
        "siem_controls": ["AC-2","AC-3","AC-6","AC-7","AC-17"],
        "sections": ["Purpose","Scope","Roles & Responsibilities","Account Management","Authentication Requirements","Authorization & Least Privilege","Remote Access","Review & Monitoring","Enforcement & Exceptions"],
    },
    {
        "id": "incident-response",
        "title": "Incident Response Policy",
        "description": "Establishes procedures for detecting, reporting, and responding to security incidents.",
        "category": "Security",
        "frameworks": {"NIST 800-53": ["IR-1","IR-4","IR-5","IR-6"], "NIST CSF": ["RS.AN-1","RS.AN-2","RS.MI-1","RS.MI-2","DE.AE-2","DE.AE-5"], "GDPR": ["Art.33","Art.34"]},
        "siem_controls": ["IR-4","IR-5","IR-6"],
        "sections": ["Purpose","Scope","Roles & Responsibilities","Incident Classification","Detection & Reporting","Response Procedures","Evidence Preservation","Notification Requirements","Post-Incident Review","Enforcement"],
    },
    {
        "id": "risk-management",
        "title": "Risk Management Policy",
        "description": "Framework for identifying, assessing, and mitigating organizational risks.",
        "category": "Governance",
        "frameworks": {"NIST 800-53": ["RA-1","RA-3","RA-5","PM-9"], "NIST CSF": ["ID.RA-1","ID.RA-3","ID.RA-5","ID.RM-1"], "GDPR": ["Art.35"]},
        "siem_controls": ["RA-3","RA-5"],
        "sections": ["Purpose","Scope","Roles & Responsibilities","Risk Assessment Methodology","Risk Appetite & Tolerance","Risk Treatment Options","Vulnerability Management","Continuous Monitoring","Reporting","Enforcement"],
    },
    {
        "id": "data-protection",
        "title": "Data Protection & Privacy Policy",
        "description": "Controls for classifying, handling, storing, and disposing of sensitive data.",
        "category": "Privacy",
        "frameworks": {"NIST 800-53": ["SC-8","SC-12","SC-13","SC-28","MP-2","MP-4","MP-6"], "NIST CSF": ["PR.DS-1","PR.DS-2","PR.DS-5"], "GDPR": ["Art.5","Art.25","Art.30","Art.32"]},
        "siem_controls": [],
        "sections": ["Purpose","Scope","Roles & Responsibilities","Data Classification","Data Handling & Storage","Encryption Requirements","Data Retention & Disposal","Cross-Border Transfers","Data Subject Rights","Enforcement"],
    },
    {
        "id": "system-integrity",
        "title": "System & Information Integrity Policy",
        "description": "Ensures systems are protected against malicious code, patched, and monitored.",
        "category": "Security",
        "frameworks": {"NIST 800-53": ["SI-1","SI-2","SI-3","SI-4","SI-7"], "NIST CSF": ["DE.CM-1","DE.CM-4","DE.CM-8","PR.IP-12"], "GDPR": ["Art.32"]},
        "siem_controls": ["SI-2","SI-4","SI-7"],
        "sections": ["Purpose","Scope","Roles & Responsibilities","Flaw Remediation & Patching","Malicious Code Protection","Security Monitoring","Software & Firmware Integrity","Alert Thresholds","Enforcement"],
    },
    {
        "id": "configuration-management",
        "title": "Configuration Management Policy",
        "description": "Baseline configurations, change control, and system hardening standards.",
        "category": "Operations",
        "frameworks": {"NIST 800-53": ["CM-1","CM-2","CM-3","CM-5","CM-6","CM-7"], "NIST CSF": ["PR.IP-1","PR.IP-3"], "GDPR": ["Art.25"]},
        "siem_controls": ["CM-3","CM-5","CM-6"],
        "sections": ["Purpose","Scope","Roles & Responsibilities","Baseline Configurations","Change Control Process","Access Restrictions for Changes","Configuration Settings","Least Functionality","Enforcement"],
    },
    {
        "id": "audit-accountability",
        "title": "Audit & Accountability Policy",
        "description": "Requirements for logging, monitoring, and retaining audit records.",
        "category": "Security",
        "frameworks": {"NIST 800-53": ["AU-1","AU-2","AU-3","AU-6","AU-12"], "NIST CSF": ["DE.AE-3","DE.CM-3","DE.CM-7","PR.PT-1"], "GDPR": ["Art.5","Art.30"]},
        "siem_controls": ["AU-3","AU-6","AU-12"],
        "sections": ["Purpose","Scope","Roles & Responsibilities","Auditable Events","Audit Record Content","Log Review & Analysis","Log Retention","Automated Alerts","Enforcement"],
    },
    {
        "id": "personnel-security",
        "title": "Personnel Security & Training Policy",
        "description": "Background checks, security training, and role-based awareness programs.",
        "category": "Governance",
        "frameworks": {"NIST 800-53": ["PS-1","PS-2","PS-3","PS-4","PS-6","AT-1","AT-2","AT-3"], "NIST CSF": ["PR.AT-1","PR.AT-2","PR.IP-11"], "GDPR": []},
        "siem_controls": [],
        "sections": ["Purpose","Scope","Roles & Responsibilities","Position Risk Designation","Personnel Screening","Access Agreements","Personnel Termination","Security Awareness Training","Role-Based Training","Enforcement"],
    },
    {
        "id": "contingency-planning",
        "title": "Contingency Planning & Business Continuity Policy",
        "description": "Disaster recovery, backup procedures, and business continuity planning.",
        "category": "Operations",
        "frameworks": {"NIST 800-53": ["CP-1","CP-2","CP-4","CP-6","CP-9","CP-10"], "NIST CSF": ["PR.IP-4","PR.IP-9","RC.RP-1","RC.IM-1"], "GDPR": ["Art.32"]},
        "siem_controls": [],
        "sections": ["Purpose","Scope","Roles & Responsibilities","Business Impact Analysis","Recovery Objectives (RTO/RPO)","Backup Procedures","Alternate Processing Sites","Contingency Plan Testing","Information System Recovery","Enforcement"],
    },
    {
        "id": "physical-security",
        "title": "Physical & Environmental Security Policy",
        "description": "Physical access controls, facility protection, and environmental safeguards.",
        "category": "Security",
        "frameworks": {"NIST 800-53": ["PE-1","PE-2","PE-3","PE-6","PE-8"], "NIST CSF": ["PR.AC-2","PR.IP-5"], "GDPR": ["Art.32"]},
        "siem_controls": [],
        "sections": ["Purpose","Scope","Roles & Responsibilities","Physical Access Authorizations","Physical Access Control","Visitor Management","Monitoring Physical Access","Environmental Controls","Enforcement"],
    },
]

SIEM_THRESHOLDS = {
    "AC-2": {"description": "Account Management", "threshold": "Alert on: new account creation, privilege escalation, dormant account activation (>90 days inactive)", "best_practice": "Review all account changes within 24 hours. Disable accounts after 90 days of inactivity."},
    "AC-3": {"description": "Access Enforcement", "threshold": "Alert on: unauthorized access attempts, privilege boundary violations", "best_practice": "Block unauthorized access in real-time. Log all denied access attempts."},
    "AC-6": {"description": "Least Privilege", "threshold": "Alert on: admin/root access usage, privilege escalation events", "best_practice": "Review privileged access monthly. Alert on any use of emergency/break-glass accounts."},
    "AC-7": {"description": "Unsuccessful Logon Attempts", "threshold": "Lock account after 5 consecutive failed attempts within 15 minutes", "best_practice": "Enforce 30-minute lockout. Alert SOC on 3+ failed attempts for privileged accounts."},
    "AC-17": {"description": "Remote Access", "threshold": "Alert on: remote access from new geolocations, after-hours VPN connections, concurrent sessions", "best_practice": "Require MFA for all remote access. Terminate idle sessions after 30 minutes."},
    "IR-4": {"description": "Incident Handling", "threshold": "Auto-escalate: critical severity incidents within 15 minutes, high severity within 1 hour", "best_practice": "Acknowledge all incidents within 30 minutes. Contain critical incidents within 4 hours."},
    "IR-5": {"description": "Incident Monitoring", "threshold": "Track: mean-time-to-detect <24h, mean-time-to-respond <4h for critical", "best_practice": "Review incident trends weekly. Report metrics to leadership monthly."},
    "IR-6": {"description": "Incident Reporting", "threshold": "Report to management within 1 hour for critical, 4 hours for high", "best_practice": "Notify affected parties within 72 hours (GDPR Art.33 requirement)."},
    "RA-3": {"description": "Risk Assessment", "threshold": "Trigger reassessment on: new critical vulnerability, major system change, breach event", "best_practice": "Conduct comprehensive risk assessment annually. Update on significant changes."},
    "RA-5": {"description": "Vulnerability Scanning", "threshold": "Critical vulnerabilities: remediate within 24h. High: within 7 days. Medium: within 30 days.", "best_practice": "Scan all systems weekly. Scan internet-facing assets daily."},
    "SI-2": {"description": "Flaw Remediation", "threshold": "Critical patches: apply within 48h. High: within 14 days. Medium: within 30 days.", "best_practice": "Emergency patching process for zero-day exploits within 24 hours."},
    "SI-4": {"description": "System Monitoring", "threshold": "Alert on: unusual outbound traffic >500MB, unauthorized port usage, known-bad IP connections", "best_practice": "Monitor all network perimeter traffic. Alert on traffic to sanctioned countries."},
    "SI-7": {"description": "Software & Information Integrity", "threshold": "Alert on: unauthorized file changes, binary hash mismatches, rootkit signatures", "best_practice": "Verify integrity of critical system files daily. Alert immediately on changes."},
    "CM-3": {"description": "Configuration Change Control", "threshold": "Alert on: unauthorized configuration changes, changes outside maintenance windows", "best_practice": "All changes require CAB approval. Emergency changes documented within 24 hours."},
    "CM-5": {"description": "Access Restrictions for Change", "threshold": "Alert on: configuration changes by non-authorized personnel", "best_practice": "Separate development, test, and production environments. Enforce dual-approval for production changes."},
    "CM-6": {"description": "Configuration Settings", "threshold": "Alert on: deviation from approved baseline, disabled security controls", "best_practice": "Scan for configuration drift weekly. Auto-remediate deviations where possible."},
    "AU-3": {"description": "Content of Audit Records", "threshold": "Ensure all events include: who, what, when, where, outcome", "best_practice": "Log all authentication, authorization, and data access events with full context."},
    "AU-6": {"description": "Audit Review & Analysis", "threshold": "Review security logs daily. Investigate anomalies within 4 hours.", "best_practice": "Use automated correlation. Escalate patterns of 3+ related anomalies."},
    "AU-12": {"description": "Audit Record Generation", "threshold": "Alert on: logging service failure, log tampering attempts, storage >80% capacity", "best_practice": "Ensure log integrity with hashing. Retain logs for minimum 1 year."},
}


class OrgProfile(BaseModel):
    org_name: str
    industry: Optional[str] = ""
    ciso_name: Optional[str] = ""
    ciso_title: Optional[str] = "Chief Information Security Officer"
    data_owner: Optional[str] = ""
    policy_owner: Optional[str] = ""
    compliance_officer: Optional[str] = ""
    effective_date: Optional[str] = ""
    review_frequency: Optional[str] = "Annually"

class GenerateRequest(BaseModel):
    template_id: str
    org_profile: Optional[Dict] = None
    selected_frameworks: Optional[List[str]] = None
    custom_sections: Optional[Dict] = None


class VersionCreateRequest(BaseModel):
    change_summary: Optional[str] = ""


class StatusUpdateRequest(BaseModel):
    status: str
    comment: Optional[str] = ""


class DiffRequest(BaseModel):
    version_id_1: str
    version_id_2: str


@router.get("")
async def get_templates(current_user: Dict = Depends(get_current_user)):
    """Return all policy templates with framework mappings."""
    result = []
    for t in TEMPLATES:
        fw_count = sum(len(ctrls) for ctrls in t["frameworks"].values())
        siem_thresholds = [SIEM_THRESHOLDS[c] | {"control_id": c} for c in t.get("siem_controls", []) if c in SIEM_THRESHOLDS]
        result.append({
            "id": t["id"],
            "title": t["title"],
            "description": t["description"],
            "category": t["category"],
            "frameworks": t["frameworks"],
            "framework_count": len(t["frameworks"]),
            "control_count": fw_count,
            "sections": t["sections"],
            "siem_controls": t.get("siem_controls", []),
            "siem_thresholds": siem_thresholds,
            "has_siem": len(t.get("siem_controls", [])) > 0,
        })
    return result


@router.get("/org-profile")
async def get_org_profile(current_user: Dict = Depends(get_current_user)):
    """Get saved org profile."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    profile = await db.org_profiles.find_one({"organization_id": org_id}, {"_id": 0})
    return profile or {}


@router.post("/org-profile")
async def save_org_profile(data: OrgProfile, current_user: Dict = Depends(get_current_user)):
    """Save org profile for policy generation."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()
    profile = data.dict()
    profile["organization_id"] = org_id
    profile["updated_at"] = now
    await db.org_profiles.update_one(
        {"organization_id": org_id},
        {"$set": profile, "$setOnInsert": {"created_at": now}},
        upsert=True
    )
    return {"message": "Profile saved"}


@router.post("/generate")
async def generate_policy(data: GenerateRequest, current_user: Dict = Depends(get_current_user)):
    """Generate a full policy document from template + org profile using LLM."""
    template = next((t for t in TEMPLATES if t["id"] == data.template_id), None)
    if not template:
        raise HTTPException(404, "Template not found")

    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    # Get org profile
    org = data.org_profile or {}
    if not org:
        saved = await db.org_profiles.find_one({"organization_id": org_id}, {"_id": 0})
        if saved:
            org = saved

    # Get SIEM thresholds for this template
    thresholds_text = ""
    for ctrl_id in template.get("siem_controls", []):
        if ctrl_id in SIEM_THRESHOLDS:
            t = SIEM_THRESHOLDS[ctrl_id]
            thresholds_text += f"\n- {ctrl_id} ({t['description']}): {t['threshold']}. Best practice: {t['best_practice']}"

    # Determine which frameworks to include
    selected_fws = data.selected_frameworks or list(template["frameworks"].keys())
    fw_text = ""
    for fw_name in selected_fws:
        if fw_name in template["frameworks"]:
            ctrls = template["frameworks"][fw_name]
            fw_text += f"\n- {fw_name}: {', '.join(ctrls)}"

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    chat = LlmChat(
        api_key=api_key,
        session_id=f"template-{uuid.uuid4()}",
        system_message="You are an expert GRC policy writer. Generate professional, comprehensive policy documents that are ready for executive approval. Use formal language."
    ).with_model("openai", "gpt-5.2")

    prompt = f"""Generate a complete {template['title']} document for {org.get('org_name', 'the organization')}.

Organization Details:
- Name: {org.get('org_name', '[Organization Name]')}
- Industry: {org.get('industry', '[Industry]')}
- CISO: {org.get('ciso_name', '[CISO Name]')}, {org.get('ciso_title', 'CISO')}
- Data Owner: {org.get('data_owner', '[Data Owner]')}
- Policy Owner: {org.get('policy_owner', '[Policy Owner]')}
- Compliance Officer: {org.get('compliance_officer', '[Compliance Officer]')}
- Effective Date: {org.get('effective_date', '[Effective Date]')}
- Review Frequency: {org.get('review_frequency', 'Annually')}

This policy must address these compliance frameworks and controls:{fw_text}

Required sections: {', '.join(template['sections'])}
{f'SIEM Monitoring Thresholds (include these specific thresholds in the monitoring/enforcement sections):{thresholds_text}' if thresholds_text else ''}

Return ONLY a JSON object with:
- "title": Policy title
- "version": "1.0"
- "sections": Array of objects, each with "heading" (string) and "content" (string with the full section text, use \\n for line breaks)
- "frameworks_addressed": Array of framework names this policy covers
- "controls_addressed": Object mapping framework name to array of control IDs addressed

Generate professional, specific content - not generic placeholders. Reference the org name and roles throughout. Include specific thresholds and metrics where applicable."""

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        response_text = response if isinstance(response, str) else str(response)

        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            policy = json.loads(json_match.group())
        else:
            policy = {"title": template["title"], "version": "1.0", "sections": [{"heading": "Policy", "content": response_text}], "frameworks_addressed": selected_fws, "controls_addressed": {}}

        # Save to DB
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "template_id": data.template_id,
            "title": policy.get("title", template["title"]),
            "version": policy.get("version", "1.0"),
            "sections": policy.get("sections", []),
            "frameworks_addressed": policy.get("frameworks_addressed", selected_fws),
            "controls_addressed": policy.get("controls_addressed", {}),
            "org_profile": org,
            "status": "draft",
            "created_at": now,
            "updated_at": now,
            "created_by": current_user["id"],
        }
        await db.generated_templates.insert_one(doc)
        # Auto-create version 1 snapshot
        version_doc = {
            "id": str(uuid.uuid4()),
            "policy_id": doc["id"],
            "organization_id": org_id,
            "version_number": 1,
            "title": doc["title"],
            "sections": doc["sections"],
            "frameworks_addressed": doc.get("frameworks_addressed", []),
            "controls_addressed": doc.get("controls_addressed", {}),
            "status": "draft",
            "change_summary": "Initial policy generation",
            "created_at": now,
            "created_by": current_user["id"],
            "created_by_name": current_user.get("name", current_user.get("email", "Unknown")),
        }
        await db.policy_versions.insert_one(version_doc)
        del doc["_id"]
        return doc
    except Exception as e:
        logger.error(f"Policy generation failed: {e}")
        raise HTTPException(500, f"Generation failed: {str(e)}")


@router.get("/generated")
async def list_generated_policies(current_user: Dict = Depends(get_current_user)):
    """List all generated template-based policies."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    docs = await db.generated_templates.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return docs


@router.get("/generated/{policy_id}")
async def get_generated_policy(policy_id: str, current_user: Dict = Depends(get_current_user)):
    """Get a specific generated policy."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    doc = await db.generated_templates.find_one(
        {"organization_id": org_id, "id": policy_id}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(404, "Policy not found")
    return doc


@router.put("/generated/{policy_id}")
async def update_generated_policy(policy_id: str, current_user: Dict = Depends(get_current_user)):
    """Update a generated policy (sections, title, etc.)."""
    from fastapi import Request
    # We'll handle the body manually since it's flexible
    return {"message": "Use the sections update endpoint"}


@router.put("/generated/{policy_id}/sections")
async def update_policy_sections(policy_id: str, data: dict, current_user: Dict = Depends(get_current_user)):
    """Update specific sections of a generated policy."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()
    update = {"updated_at": now}
    if "sections" in data:
        update["sections"] = data["sections"]
    if "title" in data:
        update["title"] = data["title"]
    if "status" in data:
        update["status"] = data["status"]

    result = await db.generated_templates.update_one(
        {"organization_id": org_id, "id": policy_id},
        {"$set": update}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Policy not found")
    return {"message": "Updated"}


@router.post("/generated/{policy_id}/versions")
async def create_version(policy_id: str, data: VersionCreateRequest, current_user: Dict = Depends(get_current_user)):
    """Create a new version snapshot of the current policy state."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    policy = await db.generated_templates.find_one({"organization_id": org_id, "id": policy_id}, {"_id": 0})
    if not policy:
        raise HTTPException(404, "Policy not found")

    latest = await db.policy_versions.find({"policy_id": policy_id}).sort("version_number", -1).limit(1).to_list(1)
    next_ver = (latest[0]["version_number"] + 1) if latest else 1

    now = datetime.now(timezone.utc).isoformat()
    version = {
        "id": str(uuid.uuid4()),
        "policy_id": policy_id,
        "organization_id": org_id,
        "version_number": next_ver,
        "title": policy["title"],
        "sections": policy["sections"],
        "frameworks_addressed": policy.get("frameworks_addressed", []),
        "controls_addressed": policy.get("controls_addressed", {}),
        "status": policy.get("status", "draft"),
        "change_summary": data.change_summary or f"Version {next_ver}",
        "created_at": now,
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", current_user.get("email", "Unknown")),
    }
    await db.policy_versions.insert_one(version)
    del version["_id"]

    await db.generated_templates.update_one(
        {"id": policy_id},
        {"$set": {"version": f"{next_ver}.0", "updated_at": now}}
    )

    return version


@router.get("/generated/{policy_id}/versions")
async def list_versions(policy_id: str, current_user: Dict = Depends(get_current_user)):
    """List all version snapshots for a policy."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    versions = await db.policy_versions.find(
        {"policy_id": policy_id, "organization_id": org_id}, {"_id": 0}
    ).sort("version_number", -1).to_list(100)
    return versions


@router.post("/generated/{policy_id}/versions/diff")
async def diff_versions(policy_id: str, data: DiffRequest, current_user: Dict = Depends(get_current_user)):
    """Compute section-by-section diff between two versions."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    v1 = await db.policy_versions.find_one(
        {"policy_id": policy_id, "organization_id": org_id, "id": data.version_id_1}, {"_id": 0}
    )
    v2 = await db.policy_versions.find_one(
        {"policy_id": policy_id, "organization_id": org_id, "id": data.version_id_2}, {"_id": 0}
    )
    if not v1 or not v2:
        raise HTTPException(404, "One or both versions not found")

    diffs = []
    s1_list = v1.get("sections", [])
    s2_list = v2.get("sections", [])
    max_sections = max(len(s1_list), len(s2_list))

    for i in range(max_sections):
        s1 = s1_list[i] if i < len(s1_list) else {"heading": "(removed)", "content": ""}
        s2 = s2_list[i] if i < len(s2_list) else {"heading": "(added)", "content": ""}
        diff_lines = list(difflib.unified_diff(
            (s1.get("content", "") or "").splitlines(keepends=False),
            (s2.get("content", "") or "").splitlines(keepends=False),
            lineterm=""
        ))
        diffs.append({
            "section_index": i,
            "heading_v1": s1.get("heading", ""),
            "heading_v2": s2.get("heading", ""),
            "has_changes": len(diff_lines) > 2,
            "diff_lines": diff_lines,
        })

    return {
        "version_1": {"id": v1["id"], "version_number": v1["version_number"], "created_at": v1["created_at"], "change_summary": v1.get("change_summary", "")},
        "version_2": {"id": v2["id"], "version_number": v2["version_number"], "created_at": v2["created_at"], "change_summary": v2.get("change_summary", "")},
        "sections": diffs,
        "total_changes": sum(1 for d in diffs if d["has_changes"]),
    }


@router.get("/generated/{policy_id}/versions/{version_id}")
async def get_version(policy_id: str, version_id: str, current_user: Dict = Depends(get_current_user)):
    """Get a specific version snapshot."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    version = await db.policy_versions.find_one(
        {"policy_id": policy_id, "organization_id": org_id, "id": version_id}, {"_id": 0}
    )
    if not version:
        raise HTTPException(404, "Version not found")
    return version


@router.put("/generated/{policy_id}/versions/{version_id}/restore")
async def restore_version(policy_id: str, version_id: str, current_user: Dict = Depends(get_current_user)):
    """Restore a policy to a previous version's state."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    version = await db.policy_versions.find_one(
        {"policy_id": policy_id, "organization_id": org_id, "id": version_id}, {"_id": 0}
    )
    if not version:
        raise HTTPException(404, "Version not found")

    now = datetime.now(timezone.utc).isoformat()
    await db.generated_templates.update_one(
        {"organization_id": org_id, "id": policy_id},
        {"$set": {
            "title": version["title"],
            "sections": version["sections"],
            "status": "draft",
            "updated_at": now,
        }}
    )

    latest = await db.policy_versions.find({"policy_id": policy_id}).sort("version_number", -1).limit(1).to_list(1)
    next_ver = (latest[0]["version_number"] + 1) if latest else 1

    restore_doc = {
        "id": str(uuid.uuid4()),
        "policy_id": policy_id,
        "organization_id": org_id,
        "version_number": next_ver,
        "title": version["title"],
        "sections": version["sections"],
        "frameworks_addressed": version.get("frameworks_addressed", []),
        "controls_addressed": version.get("controls_addressed", {}),
        "status": "draft",
        "change_summary": f"Restored from version {version['version_number']}",
        "created_at": now,
        "created_by": current_user["id"],
        "created_by_name": current_user.get("name", current_user.get("email", "Unknown")),
    }
    await db.policy_versions.insert_one(restore_doc)
    del restore_doc["_id"]

    await db.generated_templates.update_one(
        {"id": policy_id},
        {"$set": {"version": f"{next_ver}.0"}}
    )

    return restore_doc


@router.put("/generated/{policy_id}/status")
async def update_policy_status(policy_id: str, data: StatusUpdateRequest, current_user: Dict = Depends(get_current_user)):
    """Update policy approval status with workflow validation."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    valid_statuses = ["draft", "under_review", "approved"]
    if data.status not in valid_statuses:
        raise HTTPException(400, f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    policy = await db.generated_templates.find_one({"organization_id": org_id, "id": policy_id}, {"_id": 0})
    if not policy:
        raise HTTPException(404, "Policy not found")

    current_status = policy.get("status", "draft")
    valid_transitions = {
        "draft": ["under_review"],
        "under_review": ["approved", "draft"],
        "approved": ["draft"],
    }
    if data.status != current_status and data.status not in valid_transitions.get(current_status, []):
        raise HTTPException(400, f"Cannot transition from '{current_status}' to '{data.status}'")

    now = datetime.now(timezone.utc).isoformat()
    update_fields = {"status": data.status, "updated_at": now}
    if data.status == "approved":
        update_fields["approved_by"] = current_user["id"]
        update_fields["approved_by_name"] = current_user.get("name", current_user.get("email", "Unknown"))
        update_fields["approved_at"] = now

    await db.generated_templates.update_one(
        {"organization_id": org_id, "id": policy_id},
        {"$set": update_fields}
    )

    # Auto-link approved policy to framework controls
    if data.status == "approved":
        controls_addressed = policy.get("controls_addressed", {})
        frameworks_addressed = policy.get("frameworks_addressed", [])
        # Remove old mappings for this policy
        await db.mappings.delete_many({"organization_id": org_id, "source_policy_id": policy_id})
        # Pre-fetch all frameworks for fuzzy matching
        all_fws = await db.frameworks.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(100)
        # Create new mappings per framework/control
        for fw_name in frameworks_addressed:
            # Fuzzy match: try exact, then substring, then first word
            fw_id = fw_name
            for db_fw in all_fws:
                db_name_lower = db_fw["name"].lower()
                fw_name_lower = fw_name.lower()
                if db_name_lower == fw_name_lower or db_name_lower in fw_name_lower or fw_name_lower in db_name_lower:
                    fw_id = db_fw["id"]
                    break
            ctrl_ids = controls_addressed.get(fw_name, [])
            for ctrl_id in ctrl_ids:
                mapping = {
                    "id": str(uuid.uuid4()),
                    "organization_id": org_id,
                    "framework_id": fw_id,
                    "control_id": ctrl_id,
                    "policy_name": policy.get("title", "Unnamed Policy"),
                    "source_policy_id": policy_id,
                    "source": "Generated Policy",
                    "confidence_score": 1.0,
                    "status": "approved",
                    "created_at": now,
                }
                await db.mappings.insert_one(mapping)

    return {"message": f"Status updated to {data.status}", "status": data.status}


class AssigneeUpdateRequest(BaseModel):
    reviewers: Optional[List[str]] = None
    approvers: Optional[List[str]] = None


@router.put("/generated/{policy_id}/assignees")
async def update_policy_assignees(policy_id: str, data: AssigneeUpdateRequest, current_user: Dict = Depends(get_current_user)):
    """Assign reviewers and approvers to a policy."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    policy = await db.generated_templates.find_one({"organization_id": org_id, "id": policy_id}, {"_id": 0})
    if not policy:
        raise HTTPException(404, "Policy not found")

    now = datetime.now(timezone.utc).isoformat()
    update = {"updated_at": now}
    if data.reviewers is not None:
        # Resolve user names
        reviewer_details = []
        for uid in data.reviewers:
            user = await db.users.find_one({"id": uid}, {"_id": 0, "id": 1, "email": 1, "name": 1})
            if user:
                reviewer_details.append({"id": user["id"], "email": user.get("email", ""), "name": user.get("name", user.get("email", ""))})
        update["reviewers"] = reviewer_details
    if data.approvers is not None:
        approver_details = []
        for uid in data.approvers:
            user = await db.users.find_one({"id": uid}, {"_id": 0, "id": 1, "email": 1, "name": 1})
            if user:
                approver_details.append({"id": user["id"], "email": user.get("email", ""), "name": user.get("name", user.get("email", ""))})
        update["approvers"] = approver_details

    await db.generated_templates.update_one(
        {"organization_id": org_id, "id": policy_id},
        {"$set": update}
    )
    return {"message": "Assignees updated", "reviewers": update.get("reviewers", policy.get("reviewers", [])), "approvers": update.get("approvers", policy.get("approvers", []))}


@router.get("/org-users")
async def get_org_users(current_user: Dict = Depends(get_current_user)):
    """Get all users in the organization for assignment."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    users = await db.users.find(
        {"roles.organization_id": org_id},
        {"_id": 0, "id": 1, "email": 1, "name": 1, "roles": 1}
    ).to_list(100)
    return [{"id": u["id"], "email": u.get("email", ""), "name": u.get("name", u.get("email", "")), "role": u.get("roles", [{}])[0].get("role", "")} for u in users]


@router.post("/document-tags")
async def tag_document(data: dict, current_user: Dict = Depends(get_current_user)):
    """Tag an uploaded document to specific framework controls."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()

    tag = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "document_id": data.get("document_id"),
        "document_name": data.get("document_name", ""),
        "framework_id": data.get("framework_id"),
        "framework_name": data.get("framework_name", ""),
        "control_ids": data.get("control_ids", []),
        "notes": data.get("notes", ""),
        "created_at": now,
        "created_by": current_user["id"],
    }
    await db.document_tags.insert_one(tag)
    del tag["_id"]
    return tag


@router.get("/document-tags")
async def get_document_tags(current_user: Dict = Depends(get_current_user)):
    """Get all document-control tags."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    tags = await db.document_tags.find(
        {"organization_id": org_id}, {"_id": 0}
    ).to_list(500)
    return tags


@router.delete("/document-tags/{tag_id}")
async def delete_document_tag(tag_id: str, current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    await db.document_tags.delete_one({"organization_id": org_id, "id": tag_id})
    return {"message": "Tag removed"}
