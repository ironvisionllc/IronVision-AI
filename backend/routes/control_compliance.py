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

# Reuse SIEM control mappings
SIEM_CONTROL_MAP = {
    "authentication": ["AC-2", "AC-7", "IA-2", "IA-5"],
    "authorization": ["AC-3", "AC-6", "AC-17"],
    "data_access": ["AU-3", "AU-6", "AU-12", "SI-4"],
    "policy_change": ["CM-3", "CM-5", "CM-6"],
    "risk_management": ["RA-3", "RA-5", "PM-9"],
    "incident": ["IR-4", "IR-5", "IR-6"],
    "system": ["SI-2", "SI-4", "SI-7"],
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

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    chat = LlmChat(
        api_key=api_key,
        session_id=f"suggest-{uuid.uuid4()}",
        system_message="You are a GRC policy expert. Suggest concise, actionable policy content to satisfy compliance controls."
    ).with_model("openai", "gpt-5.2")

    prompt = f"""Suggest a policy to satisfy this compliance control:

Framework: {fw_name}
Control: {control_id} - {control.get('title', '')}
Description: {control.get('description', '')}
{f'CCIs:{chr(10)}{cci_text}' if cci_text else ''}

Provide:
1. A suggested policy title
2. Key policy statements (3-5 bullet points) that would satisfy this control
3. Implementation guidance (2-3 sentences)

Return as JSON: {{"title": "...", "statements": ["..."], "guidance": "..."}}"""

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
