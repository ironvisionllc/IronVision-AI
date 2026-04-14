"""
Control Compliance - AI-powered compliance assessment per control.
Tracks compliance status, user notes, SIEM evidence, and policy suggestions.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone, timedelta
import uuid
import os
import re
import json
import logging

from emergentintegrations.llm.chat import LlmChat, UserMessage

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/control-compliance", tags=["control-compliance"])

# SIEM control mappings — ALL frameworks
SIEM_CONTROL_MAP = {
    "authentication": [
        # NIST SP 800-53
        "AC-2", "AC-7", "IA-2", "IA-5",
        # NIST CSF
        "PR.AC-1", "PR.AC-7", "DE.CM-1",
        # GDPR
        "Art.32",
        # NIST SP 800-171
        "3.1.1", "3.1.2", "3.1.8", "3.1.9", "3.1.10", "3.1.11",
        "3.5.1", "3.5.2", "3.5.3", "3.5.4", "3.5.5", "3.5.6", "3.5.7", "3.5.8", "3.5.9", "3.5.10", "3.5.11",
        # ISO 27001
        "5.15", "5.16", "5.17", "8.2", "8.3", "8.5",
        # HIPAA
        "164.312(a)(1)", "164.312(a)(2)(i)", "164.312(a)(2)(iii)", "164.312(d)",
        "164.308(a)(3)(ii)(A)", "164.308(a)(4)(i)", "164.308(a)(4)(ii)(B)", "164.308(a)(4)(ii)(C)",
        # SOC 2
        "CC6.1", "CC6.2", "CC6.3",
        # CMMC
        "AC.L1-3.1.1", "AC.L1-3.1.2", "AC.L2-3.1.8", "AC.L2-3.1.9", "AC.L2-3.1.10", "AC.L2-3.1.11",
        "IA.L1-3.5.1", "IA.L1-3.5.2", "IA.L2-3.5.3",
        # NIS2
        "NIS2-8", "NIS2-9",
        # StateRAMP
        "SR-AC-1", "SR-AC-2", "SR-AC-7", "SR-AC-8", "SR-AC-11", "SR-AC-12",
        "SR-IA-1", "SR-IA-2", "SR-IA-4", "SR-IA-5", "SR-IA-6", "SR-IA-8",
        # NERC CIP
        "CIP-004-R4", "CIP-004-R5", "CIP-005-R1", "CIP-005-R2", "CIP-005-R3", "CIP-007-R5",
    ],
    "authorization": [
        # NIST SP 800-53
        "AC-3", "AC-6", "AC-17",
        # NIST CSF
        "PR.AC-3", "PR.AC-4", "PR.AC-5",
        # GDPR
        "Art.25", "Art.32",
        # NIST SP 800-171
        "3.1.3", "3.1.4", "3.1.5", "3.1.6", "3.1.7", "3.1.12", "3.1.13", "3.1.14", "3.1.15",
        "3.1.16", "3.1.17", "3.1.18", "3.1.19", "3.1.20", "3.1.21", "3.1.22",
        # ISO 27001
        "5.3", "5.10", "5.18", "8.1", "8.4", "8.18", "8.33",
        # HIPAA
        "164.312(a)(2)(ii)", "164.312(a)(2)(iv)", "164.308(a)(3)(i)", "164.308(a)(3)(ii)(B)", "164.308(a)(3)(ii)(C)",
        # SOC 2
        "CC6.6", "CC6.7", "CC6.8",
        # CMMC
        "AC.L2-3.1.3", "AC.L2-3.1.4", "AC.L2-3.1.5", "AC.L2-3.1.6", "AC.L2-3.1.7",
        "AC.L2-3.1.12", "AC.L2-3.1.13", "AC.L2-3.1.14", "AC.L2-3.1.15",
        "AC.L1-3.1.20", "AC.L1-3.1.22",
        # NIS2
        "NIS2-10",
        # StateRAMP
        "SR-AC-3", "SR-AC-4", "SR-AC-5", "SR-AC-6", "SR-AC-17", "SR-AC-18", "SR-AC-20",
        # NERC CIP
        "CIP-006-R1", "CIP-006-R2", "CIP-006-R3", "CIP-011-R1",
        # FS AI
        "FS-SP-1",
    ],
    "data_access": [
        # NIST SP 800-53
        "AU-3", "AU-6", "AU-12", "SI-4",
        # NIST CSF
        "PR.DS-1", "PR.DS-2", "PR.DS-5", "DE.AE-3", "DE.CM-3", "DE.CM-7",
        # GDPR
        "Art.5", "Art.30",
        # NIST SP 800-171
        "3.3.1", "3.3.2", "3.3.3", "3.3.4", "3.3.5", "3.3.6", "3.3.7", "3.3.8", "3.3.9",
        "3.8.1", "3.8.2", "3.8.3", "3.8.4", "3.8.5", "3.8.6", "3.8.7", "3.8.8", "3.8.9",
        # ISO 27001
        "5.12", "5.13", "5.14", "5.33", "5.34", "8.9", "8.10", "8.11", "8.12", "8.13",
        # HIPAA
        "164.312(b)", "164.312(c)(1)", "164.312(c)(2)", "164.312(e)(1)", "164.312(e)(2)(i)", "164.312(e)(2)(ii)",
        "164.308(a)(1)(ii)(D)", "164.308(a)(5)(ii)(C)",
        # SOC 2
        "CC4.1", "CC4.2", "CC5.1", "CC7.1", "C1.1", "C1.2",
        # CMMC
        "AU.L2-3.3.1", "AU.L2-3.3.2", "AU.L2-3.3.3", "AU.L2-3.3.4", "AU.L2-3.3.5",
        "AU.L2-3.3.6", "AU.L2-3.3.7", "AU.L2-3.3.8", "AU.L2-3.3.9",
        # NIS2
        "NIS2-5",
        # StateRAMP
        "SR-AU-1", "SR-AU-2", "SR-AU-3", "SR-AU-4", "SR-AU-5", "SR-AU-6", "SR-AU-8", "SR-AU-9", "SR-AU-12",
        # NERC CIP
        "CIP-007-R4", "CIP-011-R2",
        # NERC 693
        "PRC-002",
        # FS AI
        "FS-SP-3", "FS-SP-4", "FS-DM-1", "FS-DM-2",
    ],
    "policy_change": [
        # NIST SP 800-53
        "CM-3", "CM-5", "CM-6",
        # NIST CSF
        "PR.IP-1", "PR.IP-3",
        # GDPR
        "Art.25",
        # NIST SP 800-171
        "3.4.1", "3.4.2", "3.4.3", "3.4.4", "3.4.5", "3.4.6", "3.4.7", "3.4.8", "3.4.9",
        # ISO 27001
        "5.1", "5.2", "5.37", "8.8", "8.9", "8.32",
        # HIPAA
        "164.308(a)(1)(i)", "164.308(a)(1)(ii)(C)",
        # SOC 2
        "CC8.1", "CC5.2", "CC5.3",
        # CMMC
        "CM.L2-3.4.1", "CM.L2-3.4.2", "CM.L2-3.4.3", "CM.L2-3.4.4", "CM.L2-3.4.5",
        "CM.L2-3.4.6", "CM.L2-3.4.7", "CM.L2-3.4.8", "CM.L2-3.4.9",
        # NIS2
        "NIS2-6",
        # StateRAMP
        "SR-CM-1", "SR-CM-2", "SR-CM-3", "SR-CM-4", "SR-CM-6", "SR-CM-7", "SR-CM-8",
        # NERC CIP
        "CIP-010-R1", "CIP-010-R2", "CIP-010-R4",
        # NERC 693
        "TOP-003",
        # NIST AI RMF
        "GV-1.2", "GV-1.3",
    ],
    "risk_management": [
        # NIST SP 800-53
        "RA-3", "RA-5", "PM-9",
        # NIST CSF
        "ID.RA-1", "ID.RA-3", "ID.RA-5", "ID.RM-1",
        # GDPR
        "Art.35",
        # NIST SP 800-171
        "3.11.1", "3.11.2", "3.11.3",
        "3.12.1", "3.12.2", "3.12.3", "3.12.4",
        # ISO 27001
        "5.7", "5.23", "5.24", "5.29", "5.30",
        # HIPAA
        "164.308(a)(1)(ii)(A)", "164.308(a)(1)(ii)(B)", "164.308(a)(8)",
        # SOC 2
        "CC3.1", "CC3.2", "CC3.3", "CC3.4", "CC9.1", "CC9.2",
        # CMMC
        "RE.L2-3.13.1", "RE.L2-3.13.2", "RE.L2-3.13.3",
        # NIS2
        "NIS2-1", "NIS2-4", "NIS2-16",
        # StateRAMP
        "SR-CA-1", "SR-CA-2", "SR-CA-3", "SR-CA-5", "SR-CA-6", "SR-CA-7",
        # NERC CIP
        "CIP-010-R3", "CIP-013-R1", "CIP-013-R2", "CIP-014-R1", "CIP-014-R4",
        # NERC 693
        "IRO-001", "IRO-002", "IRO-008", "FAC-014", "TPL-001",
        # NIST AI RMF
        "GV-1.5", "GV-3.2", "MP-2.1", "MP-2.2", "MP-2.3", "MS-1.1", "MS-1.2", "MS-2.1",
        # FS AI
        "FS-GV-3", "FS-GV-7", "FS-DM-4", "FS-DM-5", "FS-DM-6",
    ],
    "incident": [
        # NIST SP 800-53
        "IR-4", "IR-5", "IR-6",
        # NIST CSF
        "RS.AN-1", "RS.AN-2", "RS.MI-1", "RS.MI-2", "DE.AE-2", "DE.AE-5",
        # GDPR
        "Art.33", "Art.34",
        # NIST SP 800-171
        "3.6.1", "3.6.2", "3.6.3",
        # ISO 27001
        "5.24", "5.25", "5.26", "5.27", "5.28", "6.8",
        # HIPAA
        "164.308(a)(6)(i)", "164.308(a)(6)(ii)",
        # SOC 2
        "CC7.2", "CC7.3",
        # CMMC
        "IR.L2-3.6.1", "IR.L2-3.6.2", "IR.L2-3.6.3",
        # NIS2
        "NIS2-2", "NIS2-11", "NIS2-12", "NIS2-13",
        # StateRAMP
        "SR-IR-1", "SR-IR-2", "SR-IR-3", "SR-IR-4", "SR-IR-5", "SR-IR-6", "SR-IR-8",
        # NERC CIP
        "CIP-008-R1", "CIP-008-R2", "CIP-008-R3",
        # NERC 693
        "EOP-004", "EOP-008", "EOP-011",
    ],
    "system": [
        # NIST SP 800-53
        "SI-2", "SI-4", "SI-7",
        # NIST CSF
        "PR.MA-1", "DE.CM-4", "DE.CM-8",
        # GDPR
        "Art.32",
        # NIST SP 800-171
        "3.13.1", "3.13.2", "3.13.3", "3.13.4", "3.13.5", "3.13.6", "3.13.7", "3.13.8",
        "3.13.9", "3.13.10", "3.13.11", "3.13.12", "3.13.13", "3.13.14", "3.13.15", "3.13.16",
        "3.14.1", "3.14.2", "3.14.3", "3.14.4", "3.14.5", "3.14.6", "3.14.7",
        "3.7.1", "3.7.2", "3.7.3", "3.7.4", "3.7.5", "3.7.6",
        # ISO 27001
        "8.6", "8.7", "8.8", "8.15", "8.16", "8.19", "8.20", "8.22", "8.23", "8.24", "8.25",
        # HIPAA
        "164.310(a)(1)", "164.310(d)(1)", "164.310(d)(2)(iii)",
        # SOC 2
        "CC7.1", "A1.1", "A1.2", "A1.3",
        # CMMC
        "MA.L2-3.7.1", "MA.L2-3.7.2", "MA.L2-3.7.3", "MA.L2-3.7.4", "MA.L2-3.7.5", "MA.L2-3.7.6",
        # NIS2
        "NIS2-3", "NIS2-7",
        # StateRAMP
        "SR-SI-1", "SR-SI-2", "SR-SI-3", "SR-SI-4", "SR-SI-5", "SR-SI-10", "SR-SI-12",
        "SR-SC-1", "SR-SC-5", "SR-SC-7", "SR-SC-8", "SR-SC-12", "SR-SC-13", "SR-SC-28",
        "SR-CP-1", "SR-CP-2", "SR-CP-3", "SR-CP-4", "SR-CP-9", "SR-CP-10",
        # NERC CIP
        "CIP-003-R1", "CIP-007-R1", "CIP-007-R2", "CIP-007-R3", "CIP-009-R1", "CIP-009-R2", "CIP-009-R3", "CIP-012-R1",
        # NERC 693
        "COM-001", "COM-002", "EOP-005", "EOP-006", "TOP-001", "TOP-010", "BAL-001", "BAL-005", "PRC-005",
        # NIST AI RMF
        "MS-2.2", "MS-2.3", "MS-3.1", "MG-2.1", "MG-2.2",
        # FS AI
        "FS-OR-1", "FS-OR-2", "FS-OR-3", "FS-OR-4",
    ],
}

# Reverse map: control_id -> [siem_categories]
CONTROL_TO_SIEM = {}
for cat, ctrls in SIEM_CONTROL_MAP.items():
    for c in ctrls:
        CONTROL_TO_SIEM.setdefault(c, []).append(cat)


class StatusUpdate(BaseModel):
    status: str
    reason: Optional[str] = ""

class NotesUpdate(BaseModel):
    notes: str

class ComplianceOverride(BaseModel):
    status: str
    notes: Optional[str] = ""
    policy_suggestion: Optional[str] = ""


@router.get("/{framework_id}")
async def get_compliance_overview(framework_id: str, current_user: Dict = Depends(get_current_user)):
    """Get compliance status for all controls in a framework, with SIEM evidence counts."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    controls = await db.controls.find(
        {"framework_id": framework_id}, {"_id": 0}
    ).to_list(2000)

    if not controls:
        return {"controls": [], "summary": {}}

    # Get saved compliance data for this org + framework
    saved = await db.control_compliance.find(
        {"organization_id": org_id, "framework_id": framework_id}, {"_id": 0}
    ).to_list(2000)
    saved_map = {s["control_id"]: s for s in saved}

    # Get SIEM event counts (last 30 days) per category
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    siem_pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {"_id": "$category", "count": {"$sum": 1},
                    "critical": {"$sum": {"$cond": [{"$eq": ["$severity", "critical"]}, 1, 0]}},
                    "high": {"$sum": {"$cond": [{"$eq": ["$severity", "high"]}, 1, 0]}},
        }}
    ]
    siem_cats = {}
    async for doc in db.siem_events.aggregate(siem_pipeline):
        siem_cats[doc["_id"]] = {"count": doc["count"], "critical": doc["critical"], "high": doc["high"]}

    # Get policy mappings per control
    policy_mappings = await db.mappings.find(
        {"organization_id": org_id, "framework_id": framework_id}, {"_id": 0}
    ).to_list(5000)
    policy_map = {}
    for pm in policy_mappings:
        policy_map.setdefault(pm["control_id"], []).append(pm)

    # Build per-control compliance data
    result = []
    counts = {"compliant": 0, "partial": 0, "non_compliant": 0, "not_assessed": 0}

    for ctrl in controls:
        cid = ctrl["control_id"]
        saved_data = saved_map.get(cid, {})

        # SIEM evidence for this control
        siem_categories = CONTROL_TO_SIEM.get(cid, [])
        siem_events_count = sum(siem_cats.get(cat, {}).get("count", 0) for cat in siem_categories)
        siem_critical = sum(siem_cats.get(cat, {}).get("critical", 0) for cat in siem_categories)
        siem_high = sum(siem_cats.get(cat, {}).get("high", 0) for cat in siem_categories)

        # Policy mappings
        ctrl_policies = policy_map.get(cid, [])

        # Determine compliance status
        status = saved_data.get("status", "not_assessed")
        is_technical = len(siem_categories) > 0

        result.append({
            "control_id": cid,
            "title": ctrl.get("title", ""),
            "description": ctrl.get("description", ""),
            "category": ctrl.get("category", ""),
            "status": status,
            "is_user_override": saved_data.get("is_user_override", False),
            "notes": saved_data.get("notes", ""),
            "ai_assessment": saved_data.get("ai_assessment", ""),
            "policy_suggestion": saved_data.get("policy_suggestion", ""),
            "is_technical": is_technical,
            "siem_categories": siem_categories,
            "siem_events_count": siem_events_count,
            "siem_critical": siem_critical,
            "siem_high": siem_high,
            "policy_mappings": ctrl_policies,
            "policy_count": len(ctrl_policies),
            "updated_at": saved_data.get("updated_at", ""),
        })
        counts[status] = counts.get(status, 0) + 1

    return {
        "framework_id": framework_id,
        "controls": result,
        "summary": counts,
        "total": len(controls),
    }


@router.put("/{framework_id}/{control_id}/status")
async def update_compliance_status(
    framework_id: str, control_id: str,
    data: StatusUpdate,
    current_user: Dict = Depends(get_current_user)
):
    """User overrides compliance status for a control."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    valid = ["compliant", "partial", "non_compliant", "not_assessed"]
    if data.status not in valid:
        raise HTTPException(400, f"Status must be one of: {valid}")

    now = datetime.now(timezone.utc).isoformat()
    await db.control_compliance.update_one(
        {"organization_id": org_id, "framework_id": framework_id, "control_id": control_id},
        {"$set": {
            "status": data.status,
            "is_user_override": True,
            "override_reason": data.reason or "",
            "updated_at": now,
            "updated_by": current_user["id"],
        },
         "$setOnInsert": {
             "organization_id": org_id,
             "framework_id": framework_id,
             "control_id": control_id,
             "notes": "",
             "ai_assessment": "",
             "policy_suggestion": "",
             "created_at": now,
         }},
        upsert=True
    )
    return {"message": "Status updated", "status": data.status}


@router.put("/{framework_id}/{control_id}/notes")
async def update_control_notes(
    framework_id: str, control_id: str,
    data: NotesUpdate,
    current_user: Dict = Depends(get_current_user)
):
    """Save user notes for a control."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()
    await db.control_compliance.update_one(
        {"organization_id": org_id, "framework_id": framework_id, "control_id": control_id},
        {"$set": {"notes": data.notes, "updated_at": now, "updated_by": current_user["id"]},
         "$setOnInsert": {
             "organization_id": org_id,
             "framework_id": framework_id,
             "control_id": control_id,
             "status": "not_assessed",
             "is_user_override": False,
             "ai_assessment": "",
             "policy_suggestion": "",
             "created_at": now,
         }},
        upsert=True
    )
    return {"message": "Notes saved"}


@router.get("/{framework_id}/{control_id}/siem-evidence")
async def get_siem_evidence(
    framework_id: str, control_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Get SIEM events related to a specific control."""
    siem_categories = CONTROL_TO_SIEM.get(control_id, [])
    if not siem_categories:
        return {"events": [], "categories": [], "message": "No SIEM mapping for this control"}

    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    events = await db.siem_events.find(
        {"category": {"$in": siem_categories}, "timestamp": {"$gte": cutoff}},
        {"_id": 0}
    ).sort("timestamp", -1).to_list(50)

    return {"events": events, "categories": siem_categories, "count": len(events)}


@router.post("/{framework_id}/ai-assess")
async def ai_bulk_assess(
    framework_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Use LLM to assess compliance status for all controls based on SIEM data + policies."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    controls = await db.controls.find(
        {"framework_id": framework_id}, {"_id": 0}
    ).to_list(2000)
    if not controls:
        raise HTTPException(404, "No controls found for this framework")

    framework = await db.frameworks.find_one({"id": framework_id}, {"_id": 0, "name": 1})
    fw_name = framework.get("name", "") if framework else ""

    # Gather SIEM evidence summary
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    siem_pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$category",
            "count": {"$sum": 1},
            "severities": {"$push": "$severity"},
            "sample_details": {"$first": "$details"},
        }}
    ]
    siem_summary = {}
    async for doc in db.siem_events.aggregate(siem_pipeline):
        sevs = doc.get("severities", [])
        siem_summary[doc["_id"]] = {
            "count": doc["count"],
            "critical": sevs.count("critical"),
            "high": sevs.count("high"),
            "sample": doc.get("sample_details", ""),
        }

    # Gather policy mappings
    mappings = await db.mappings.find(
        {"organization_id": org_id, "framework_id": framework_id}, {"_id": 0}
    ).to_list(5000)
    policy_map = {}
    for m in mappings:
        policy_map.setdefault(m["control_id"], []).append(m.get("policy_name", ""))

    # Build assessment context (limit to 40 controls per batch for token limits)
    controls_batch = controls[:40]
    controls_text = []
    for c in controls_batch:
        cid = c["control_id"]
        siem_cats = CONTROL_TO_SIEM.get(cid, [])
        siem_info = ""
        for cat in siem_cats:
            if cat in siem_summary:
                s = siem_summary[cat]
                siem_info += f" [{cat}: {s['count']} events, {s['critical']} critical, {s['high']} high]"
        policies = policy_map.get(cid, [])
        pol_info = f" Policies: {', '.join(policies[:3])}" if policies else " No policies mapped"
        controls_text.append(f"{cid}: {c.get('title','')} | SIEM:{siem_info or ' No events'} |{pol_info}")

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    chat = LlmChat(
        api_key=api_key,
        session_id=f"assess-{uuid.uuid4()}",
        system_message="You are a GRC compliance assessor. Analyze controls against SIEM evidence and policy coverage to determine compliance status. Be thorough but concise."
    ).with_model("openai", "gpt-5.2")

    prompt = f"""Assess compliance status for each control in {fw_name} based on SIEM data and policy coverage.

Controls with evidence:
{chr(10).join(controls_text)}

For each control, determine:
- status: "compliant" (has evidence + policy), "partial" (some evidence or policy), "non_compliant" (has violations or critical gaps), "not_assessed" (insufficient data)
- assessment: Brief 1-2 sentence explanation
- policy_suggestion: If non-compliant/partial, suggest what policy would help

Return ONLY a JSON array:
[{{"control_id": "AC-2", "status": "partial", "assessment": "SIEM shows authentication events but no formal access control policy mapped.", "policy_suggestion": "Access Control Policy covering user provisioning and review"}}]"""

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        response_text = response if isinstance(response, str) else str(response)

        json_match = re.search(r'\[[\s\S]*?\]', response_text)
        results = []
        if json_match:
            parsed = json.loads(json_match.group())
            now = datetime.now(timezone.utc).isoformat()

            for item in parsed:
                cid = item.get("control_id", "")
                if not cid:
                    continue
                status = item.get("status", "not_assessed")
                if status not in ["compliant", "partial", "non_compliant", "not_assessed"]:
                    status = "not_assessed"

                # Only update if not already user-overridden
                existing = await db.control_compliance.find_one(
                    {"organization_id": org_id, "framework_id": framework_id, "control_id": cid}
                )
                if existing and existing.get("is_user_override"):
                    results.append({"control_id": cid, "status": existing["status"], "skipped": True})
                    continue

                await db.control_compliance.update_one(
                    {"organization_id": org_id, "framework_id": framework_id, "control_id": cid},
                    {"$set": {
                        "status": status,
                        "ai_assessment": item.get("assessment", ""),
                        "policy_suggestion": item.get("policy_suggestion", ""),
                        "is_user_override": False,
                        "updated_at": now,
                        "updated_by": "ai",
                    },
                     "$setOnInsert": {
                         "organization_id": org_id,
                         "framework_id": framework_id,
                         "control_id": cid,
                         "notes": "",
                         "created_at": now,
                     }},
                    upsert=True
                )
                results.append({
                    "control_id": cid,
                    "status": status,
                    "assessment": item.get("assessment", ""),
                    "policy_suggestion": item.get("policy_suggestion", ""),
                })

        return {"assessed": len(results), "results": results}
    except Exception as e:
        logger.error(f"AI assessment failed: {e}")
        raise HTTPException(500, f"AI assessment failed: {str(e)}")


@router.post("/{framework_id}/{control_id}/suggest-policy")
async def suggest_policy_for_control(
    framework_id: str, control_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """AI suggests a policy to satisfy a specific control."""
    control = await db.controls.find_one(
        {"framework_id": framework_id, "control_id": control_id}, {"_id": 0}
    )
    if not control:
        raise HTTPException(404, "Control not found")

    framework = await db.frameworks.find_one({"id": framework_id}, {"_id": 0, "name": 1})
    fw_name = framework.get("name", "") if framework else ""

    # Get CCIs for context
    ccis = await db.ccis.find(
        {"parent_control_id": control_id, "framework_id": framework_id}, {"_id": 0}
    ).to_list(50)
    cci_text = "\n".join([f"- {c['cci_id']}: {c.get('definition','')[:150]}" for c in ccis[:10]])

    # Get existing mapped policies for context
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    mapped_policies = await db.mappings.find(
        {"organization_id": org_id, "framework_id": framework_id, "control_id": control_id}, {"_id": 0}
    ).to_list(10)
    existing_policy_text = ""
    if mapped_policies:
        names = [p.get("policy_name", "Unknown") for p in mapped_policies]
        existing_policy_text = f"\nExisting mapped policies: {', '.join(names)}"

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    chat = LlmChat(
        api_key=api_key,
        session_id=f"suggest-{uuid.uuid4()}",
        system_message="You are a GRC policy expert. Provide specific, actionable policy analysis showing exactly where requirements are met or not met."
    ).with_model("openai", "gpt-5.2")

    prompt = f"""Analyze this compliance control and provide a detailed policy recommendation:

Framework: {fw_name}
Control: {control_id} - {control.get('title', '')}
Description: {control.get('description', '')}
{f'CCIs:{chr(10)}{cci_text}' if cci_text else ''}
{existing_policy_text}

Provide a JSON response with:
1. "title": A suggested policy title that would satisfy this control
2. "statements": Array of 3-5 specific policy statements, each showing what requirement it addresses
3. "satisfied": Array describing WHERE in the policy each control requirement IS being addressed (be specific about sections/clauses). If no existing policy is mapped, describe what sections SHOULD exist.
4. "gaps": Array of specific requirements from this control that are NOT currently addressed by any policy
5. "guidance": 2-3 sentences of implementation guidance

Return ONLY valid JSON: {{"title": "...", "statements": ["..."], "satisfied": ["Section X.Y addresses requirement Z..."], "gaps": ["No policy covers requirement for..."], "guidance": "..."}}"""

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        response_text = response if isinstance(response, str) else str(response)

        json_match = re.search(r'\{[\s\S]*?\}', response_text)
        if json_match:
            suggestion = json.loads(json_match.group())
        else:
            suggestion = {"title": "Policy Suggestion", "statements": [response_text[:500]], "guidance": ""}

        # Save suggestion
        org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
        now = datetime.now(timezone.utc).isoformat()
        await db.control_compliance.update_one(
            {"organization_id": org_id, "framework_id": framework_id, "control_id": control_id},
            {"$set": {"policy_suggestion": json.dumps(suggestion), "updated_at": now},
             "$setOnInsert": {
                 "organization_id": org_id,
                 "framework_id": framework_id,
                 "control_id": control_id,
                 "status": "not_assessed",
                 "is_user_override": False,
                 "notes": "",
                 "ai_assessment": "",
                 "created_at": now,
             }},
            upsert=True
        )

        return suggestion
    except Exception as e:
        logger.error(f"Policy suggestion failed: {e}")
        raise HTTPException(500, f"AI suggestion failed: {str(e)}")


@router.post("/{framework_id}/{control_id}/implementation-guidance")
async def get_implementation_guidance(
    framework_id: str, control_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """AI generates implementation guidance and guidelines for a control."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    # Check cache first
    cached = await db.control_compliance.find_one(
        {"organization_id": org_id, "framework_id": framework_id, "control_id": control_id},
        {"_id": 0, "implementation_guidance": 1}
    )
    if cached and cached.get("implementation_guidance"):
        try:
            return json.loads(cached["implementation_guidance"])
        except (json.JSONDecodeError, TypeError):
            pass

    control = await db.controls.find_one(
        {"framework_id": framework_id, "control_id": control_id}, {"_id": 0}
    )
    if not control:
        raise HTTPException(404, "Control not found")

    framework = await db.frameworks.find_one({"id": framework_id}, {"_id": 0, "name": 1})
    fw_name = framework.get("name", "") if framework else ""

    ccis = await db.ccis.find(
        {"parent_control_id": control_id, "framework_id": framework_id}, {"_id": 0}
    ).to_list(50)
    cci_text = "\n".join([f"- {c['cci_id']}: {c.get('definition','')[:150]}" for c in ccis[:10]])

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    chat = LlmChat(
        api_key=api_key,
        session_id=f"impl-{uuid.uuid4()}",
        system_message="You are a compliance implementation expert. Provide practical, specific guidance."
    ).with_model("openai", "gpt-5.2")

    prompt = f"""Provide implementation guidance for this compliance control:

Framework: {fw_name}
Control: {control_id} - {control.get('title', '')}
Description: {control.get('description', '')}
{f'CCIs:{chr(10)}{cci_text}' if cci_text else ''}

Return JSON with:
1. "implementation_steps": Array of 3-5 specific steps to implement this control
2. "technical_guidelines": Array of 2-3 technical requirements or configurations needed
3. "assessment_criteria": Array of 2-3 criteria to verify the control is properly implemented
4. "common_pitfalls": Array of 1-2 common mistakes to avoid

Return ONLY valid JSON: {{"implementation_steps": ["..."], "technical_guidelines": ["..."], "assessment_criteria": ["..."], "common_pitfalls": ["..."]}}"""

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        response_text = response if isinstance(response, str) else str(response)

        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            guidance = json.loads(json_match.group())
        else:
            guidance = {"implementation_steps": [response_text[:500]], "technical_guidelines": [], "assessment_criteria": [], "common_pitfalls": []}

        # Cache it
        now = datetime.now(timezone.utc).isoformat()
        await db.control_compliance.update_one(
            {"organization_id": org_id, "framework_id": framework_id, "control_id": control_id},
            {"$set": {"implementation_guidance": json.dumps(guidance), "updated_at": now},
             "$setOnInsert": {
                 "organization_id": org_id, "framework_id": framework_id, "control_id": control_id,
                 "status": "not_assessed", "is_user_override": False, "notes": "", "ai_assessment": "", "policy_suggestion": "", "created_at": now,
             }},
            upsert=True
        )

        return guidance
    except Exception as e:
        logger.error(f"Implementation guidance failed: {e}")
        raise HTTPException(500, f"AI guidance failed: {str(e)}")


@router.post("/{framework_id}/{control_id}/link-document")
async def link_document_to_control(
    framework_id: str, control_id: str, data: dict,
    current_user: Dict = Depends(get_current_user)
):
    """Link a document from the library to a specific framework control."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    doc_id = data.get("document_id", "")
    doc_name = data.get("document_name", "")
    doc_type = data.get("document_type", "uploaded")

    if not doc_id:
        raise HTTPException(400, "document_id is required")

    now = datetime.now(timezone.utc).isoformat()
    # Check if already linked
    existing = await db.mappings.find_one({
        "organization_id": org_id, "framework_id": framework_id,
        "control_id": control_id, "source_document_id": doc_id
    })
    if existing:
        raise HTTPException(400, "Document already linked to this control")

    mapping = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "framework_id": framework_id,
        "control_id": control_id,
        "policy_name": doc_name,
        "source_document_id": doc_id,
        "source_policy_id": doc_id if doc_type == "generated" else "",
        "source": f"Linked ({doc_type.title()})",
        "confidence_score": 1.0,
        "status": "linked",
        "created_at": now,
        "created_by": current_user["id"],
    }
    await db.mappings.insert_one(mapping)
    del mapping["_id"]
    return mapping


@router.delete("/{framework_id}/{control_id}/unlink-document/{mapping_id}")
async def unlink_document_from_control(
    framework_id: str, control_id: str, mapping_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Remove a linked document from a control."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    result = await db.mappings.delete_one({
        "organization_id": org_id, "framework_id": framework_id,
        "control_id": control_id, "id": mapping_id
    })
    if result.deleted_count == 0:
        raise HTTPException(404, "Mapping not found")
    return {"message": "Document unlinked"}


@router.post("/{framework_id}/{control_id}/analyze-coverage")
async def analyze_document_coverage(
    framework_id: str, control_id: str, data: dict,
    current_user: Dict = Depends(get_current_user)
):
    """AI analyzes how well a linked document covers a specific control."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    doc_id = data.get("document_id", "")

    control = await db.controls.find_one(
        {"framework_id": framework_id, "control_id": control_id}, {"_id": 0}
    )
    if not control:
        raise HTTPException(404, "Control not found")

    framework = await db.frameworks.find_one({"id": framework_id}, {"_id": 0, "name": 1})
    fw_name = framework.get("name", "") if framework else ""

    # Get document content
    doc_content = ""
    doc_name = ""
    # Try uploaded document
    uploaded = await db.document_uploads.find_one({"id": doc_id, "organization_id": org_id}, {"_id": 0})
    if uploaded:
        doc_name = uploaded.get("filename", uploaded.get("original_name", "Unknown"))
        doc_content = uploaded.get("content", "")
        if not doc_content:
            doc_content = f"[Document: {doc_name} — content available in original file, file type: {uploaded.get('file_type', 'unknown')}]"
    else:
        # Try generated policy
        generated = await db.generated_templates.find_one({"id": doc_id, "organization_id": org_id}, {"_id": 0})
        if generated:
            doc_name = generated.get("title", "Unknown")
            sections = generated.get("sections", [])
            doc_content = "\n\n".join([f"## {s.get('heading','')}\n{s.get('content','')}" for s in sections])

    if not doc_content:
        raise HTTPException(404, "Document not found or has no content")

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    chat = LlmChat(
        api_key=api_key,
        session_id=f"coverage-{uuid.uuid4()}",
        system_message="You are a GRC compliance analyst. Analyze document coverage against control requirements precisely."
    ).with_model("openai", "gpt-5.2")

    prompt = f"""Analyze how well this document covers the requirements of the following compliance control.

Framework: {fw_name}
Control ID: {control_id}
Control Title: {control.get('title', '')}
Control Description: {control.get('description', '')}

Document: {doc_name}
Document Content (excerpt):
{doc_content[:4000]}

Return ONLY a JSON object with:
- "coverage_score": number 0-100 (how well the document addresses this control)
- "coverage_level": "full" | "partial" | "minimal" | "none"
- "addressed_requirements": array of strings listing what the document covers
- "gaps": array of strings listing what's missing or inadequate
- "recommendation": string with a brief recommendation"""

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        response_text = response if isinstance(response, str) else str(response)
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            analysis = json.loads(json_match.group())
        else:
            analysis = {"coverage_score": 0, "coverage_level": "none", "addressed_requirements": [], "gaps": ["Unable to parse analysis"], "recommendation": response_text[:300]}

        # Save to mapping
        await db.mappings.update_one(
            {"organization_id": org_id, "framework_id": framework_id, "control_id": control_id, "source_document_id": doc_id},
            {"$set": {
                "coverage_analysis": analysis,
                "confidence_score": analysis.get("coverage_score", 0) / 100,
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
            }}
        )

        return {"document_name": doc_name, "control_id": control_id, **analysis}
    except Exception as e:
        logger.error(f"Coverage analysis failed: {e}")
        raise HTTPException(500, f"Analysis failed: {str(e)}")
