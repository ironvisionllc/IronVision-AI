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

# SIEM control mappings — all frameworks
SIEM_CONTROL_MAP = {
    # NIST SP 800-53
    "authentication": [
        "AC-2", "AC-7", "IA-2", "IA-5",
        "PR.AC-1", "PR.AC-7", "DE.CM-1",   # NIST CSF
        "Art.32",                              # GDPR
    ],
    "authorization": [
        "AC-3", "AC-6", "AC-17",
        "PR.AC-3", "PR.AC-4", "PR.AC-5",   # NIST CSF
        "Art.25", "Art.32",                    # GDPR
    ],
    "data_access": [
        "AU-3", "AU-6", "AU-12", "SI-4",
        "PR.DS-1", "PR.DS-2", "PR.DS-5", "DE.AE-3", "DE.CM-3", "DE.CM-7",  # NIST CSF
        "Art.5", "Art.30",                     # GDPR
    ],
    "policy_change": [
        "CM-3", "CM-5", "CM-6",
        "PR.IP-1", "PR.IP-3",               # NIST CSF
        "Art.25",                              # GDPR
    ],
    "risk_management": [
        "RA-3", "RA-5", "PM-9",
        "ID.RA-1", "ID.RA-3", "ID.RA-5", "ID.RM-1",  # NIST CSF
        "Art.35",                              # GDPR
    ],
    "incident": [
        "IR-4", "IR-5", "IR-6",
        "RS.AN-1", "RS.AN-2", "RS.MI-1", "RS.MI-2", "DE.AE-2", "DE.AE-5",  # NIST CSF
        "Art.33", "Art.34",                    # GDPR
    ],
    "system": [
        "SI-2", "SI-4", "SI-7",
        "PR.MA-1", "DE.CM-4", "DE.CM-8",   # NIST CSF
        "Art.32",                              # GDPR
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
