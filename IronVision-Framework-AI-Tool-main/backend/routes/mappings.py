from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from datetime import datetime, timezone
import uuid
import os
import re
import json

from emergentintegrations.llm.chat import LlmChat, UserMessage

from database import db
from models import CrossFrameworkMapping
from utils import get_current_user, guard_demo, log_activity

router = APIRouter()


@router.post("/mappings/analyze")
async def analyze_policy_for_mapping(data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    policy_id = data.get("policy_id", "")

    if not policy_id:
        raise HTTPException(status_code=400, detail="Policy ID is required")

    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    policy = await db.policies.find_one({"id": policy_id, "organization_id": org_id}, {"_id": 0})
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    policy_content = policy.get("content", "")
    if not policy_content.strip():
        raise HTTPException(status_code=400, detail="Policy has no text content to analyze")

    all_controls = await db.controls.find({}, {"_id": 0}).to_list(10000)
    all_frameworks = {fw["id"]: fw["name"] for fw in await db.frameworks.find({}, {"_id": 0}).to_list(100)}

    controls_text = "\n".join([
        f"[{all_frameworks.get(c['framework_id'], '')}] {c['control_id']}: {c['title']} - {c['description'][:150]}"
        for c in all_controls[:80]
    ])

    api_key = os.environ.get('EMERGENT_LLM_KEY')
    chat = LlmChat(
        api_key=api_key,
        session_id=f"mapping-{uuid.uuid4()}",
        system_message="You are a GRC compliance expert. Analyze policy text and identify which compliance framework controls it addresses. Return ONLY a valid JSON array."
    ).with_model("openai", "gpt-5.2")

    prompt = f"""Analyze this policy and map it to the most relevant controls.

Policy Title: {policy.get('title', 'Untitled')}
Policy Content:
{policy_content[:3000]}

Available Controls:
{controls_text}

Return a JSON array of the top 5-10 most relevant controls:
[{{"control_id": "AC-1", "framework_id": "...", "confidence": 0.92, "reason": "Brief explanation"}}]

IMPORTANT: Only return the JSON array, nothing else. Use control_id and framework_id exactly as shown above."""

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        response_text = response if isinstance(response, str) else str(response)

        json_match = re.search(r'\[[\s\S]*?\]', response_text)
        suggestions = []
        if json_match:
            try:
                parsed = json.loads(json_match.group())
                controls_map = {c["control_id"]: c for c in all_controls}
                for s in parsed:
                    ctrl = controls_map.get(s.get("control_id", ""))
                    if ctrl:
                        suggestions.append({
                            "control_id": ctrl["control_id"],
                            "control_title": ctrl.get("title", ""),
                            "framework_id": ctrl["framework_id"],
                            "framework_name": all_frameworks.get(ctrl["framework_id"], ""),
                            "confidence": min(max(float(s.get("confidence", 0.7)), 0.0), 1.0),
                            "reason": s.get("reason", "")
                        })
            except json.JSONDecodeError:
                pass

        return {
            "policy_id": policy_id,
            "policy_name": policy.get("title", ""),
            "suggestions": suggestions,
            "controls_analyzed": len(all_controls)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI analysis failed: {str(e)}")


@router.get("/mappings")
async def get_mappings(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    mappings = await db.mappings.find({"organization_id": org_id}, {"_id": 0}).to_list(10000)
    return mappings


@router.post("/mappings")
async def create_mapping(data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    policy = await db.policies.find_one({"id": data.get("policy_id")}, {"_id": 0, "title": 1})
    control = await db.controls.find_one({"control_id": data.get("control_id"), "framework_id": data.get("framework_id")}, {"_id": 0, "title": 1})
    framework = await db.frameworks.find_one({"id": data.get("framework_id")}, {"_id": 0, "name": 1})

    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "policy_id": data.get("policy_id", ""),
        "policy_name": policy.get("title", "") if policy else "",
        "control_id": data.get("control_id", ""),
        "control_title": control.get("title", "") if control else "",
        "framework_id": data.get("framework_id", ""),
        "framework_name": framework.get("name", "") if framework else "",
        "confidence_score": 1.0,
        "status": "approved",
        "source": "manual",
        "notes": data.get("notes", ""),
        "ai_reason": "",
        "mapped_by": current_user["id"],
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    await db.mappings.insert_one(doc)
    await log_activity(org_id, current_user["id"], current_user.get("name", ""), "mapping_created", f"Mapped policy to control: {doc['control_id']}")
    doc.pop("_id", None)
    return doc


@router.post("/mappings/bulk-create")
async def bulk_create_mappings(data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    suggestions = data.get("suggestions", [])
    policy_id = data.get("policy_id", "")
    policy_name = data.get("policy_name", "")

    created = []
    for s in suggestions:
        doc = {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "policy_id": policy_id,
            "policy_name": policy_name,
            "control_id": s.get("control_id", ""),
            "control_title": s.get("control_title", ""),
            "framework_id": s.get("framework_id", ""),
            "framework_name": s.get("framework_name", ""),
            "confidence_score": s.get("confidence", 0.7),
            "status": "pending",
            "source": "ai",
            "notes": "",
            "ai_reason": s.get("reason", ""),
            "mapped_by": current_user["id"],
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.mappings.insert_one(doc)
        doc.pop("_id", None)
        created.append(doc)

    await log_activity(org_id, current_user["id"], current_user.get("name", ""), "ai_mappings_created", f"AI created {len(created)} pending mappings for policy: {policy_name}")
    return {"created": len(created), "mappings": created}


@router.put("/mappings/{mapping_id}/status")
async def update_mapping_status(mapping_id: str, data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    new_status = data.get("status", "")
    if new_status not in ["approved", "rejected"]:
        raise HTTPException(status_code=400, detail="Status must be 'approved' or 'rejected'")

    result = await db.mappings.update_one(
        {"id": mapping_id, "organization_id": org_id},
        {"$set": {"status": new_status}}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Mapping not found")

    await log_activity(org_id, current_user["id"], current_user.get("name", ""), f"mapping_{new_status}", f"Mapping {mapping_id} {new_status}")
    return {"message": f"Mapping {new_status}"}


@router.delete("/mappings/{mapping_id}")
async def delete_mapping(mapping_id: str, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    result = await db.mappings.delete_one({"id": mapping_id, "organization_id": org_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"message": "Mapping deleted"}


@router.get("/mappings/gaps")
async def get_mapping_gaps(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    mappings = await db.mappings.find({"organization_id": org_id}, {"_id": 0}).to_list(10000)
    mapped_control_ids = set(m["control_id"] for m in mappings)
    all_controls = await db.controls.find({}, {"_id": 0}).to_list(10000)
    gaps = [c for c in all_controls if c["id"] not in mapped_control_ids]
    return gaps


# === Cross-Framework Mapping Routes ===

@router.post("/cross-framework-mappings")
async def create_cross_framework_mapping(data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    mapping = CrossFrameworkMapping(
        organization_id=org_id,
        source_control_id=data["source_control_id"],
        source_framework_id=data["source_framework_id"],
        target_control_id=data["target_control_id"],
        target_framework_id=data["target_framework_id"],
        mapping_strength=data.get("mapping_strength", "related"),
        notes=data.get("notes", ""),
        created_by=current_user["id"]
    )

    doc = mapping.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.cross_framework_mappings.insert_one(doc)
    return mapping


@router.get("/cross-framework-mappings")
async def get_cross_framework_mappings(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    mappings = await db.cross_framework_mappings.find({"organization_id": org_id}, {"_id": 0}).to_list(10000)
    return mappings


@router.get("/cross-framework-mappings/control/{control_id}")
async def get_control_cross_mappings(control_id: str, current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    mappings = await db.cross_framework_mappings.find({
        "organization_id": org_id,
        "$or": [
            {"source_control_id": control_id},
            {"target_control_id": control_id}
        ]
    }, {"_id": 0}).to_list(1000)
    return mappings


@router.get("/cross-framework-mappings/matrix")
async def get_cross_framework_matrix(current_user: Dict = Depends(get_current_user)):
    mappings = await db.cross_framework_mappings.find({}, {"_id": 0}).to_list(50000)
    frameworks = await db.frameworks.find({}, {"_id": 0, "id": 1, "name": 1}).to_list(100)
    fw_map = {fw["id"]: fw["name"] for fw in frameworks}

    matrix = {}
    for fw1 in frameworks:
        for fw2 in frameworks:
            if fw1["id"] != fw2["id"]:
                key = f"{fw1['id']}|{fw2['id']}"
                count = sum(1 for m in mappings
                    if m.get("source_framework_id") == fw1["id"] and m.get("target_framework_id") == fw2["id"])
                matrix[key] = count

    grouped = {}
    for m in mappings:
        src_fw = fw_map.get(m.get("source_framework_id"), "")
        if src_fw not in grouped:
            grouped[src_fw] = []
        grouped[src_fw].append({
            "source_control_id": m.get("source_control_id", ""),
            "source_control_title": m.get("source_control_title", ""),
            "source_framework": src_fw,
            "target_control_id": m.get("target_control_id", ""),
            "target_control_title": m.get("target_control_title", ""),
            "target_framework": fw_map.get(m.get("target_framework_id"), ""),
            "relationship_type": m.get("relationship_type", "related"),
            "confidence_score": m.get("confidence_score", 0.8)
        })

    return {
        "frameworks": [{"id": fw["id"], "name": fw["name"]} for fw in frameworks],
        "matrix_counts": matrix,
        "mappings": mappings[:500],
        "grouped": grouped,
        "total": len(mappings)
    }


@router.post("/ai/suggest-cross-framework-mappings")
async def ai_suggest_cross_framework_mappings(data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    source_control_id = data.get("source_control_id")
    target_framework_ids = data.get("target_framework_ids", [])

    if not source_control_id or not target_framework_ids:
        raise HTTPException(status_code=400, detail="Source control ID and target framework IDs required")

    source_control = await db.controls.find_one({"id": source_control_id}, {"_id": 0})
    if not source_control:
        raise HTTPException(status_code=404, detail="Source control not found")

    source_framework = await db.frameworks.find_one({"id": source_control["framework_id"]}, {"_id": 0})

    target_controls = await db.controls.find(
        {"framework_id": {"$in": target_framework_ids}},
        {"_id": 0}
    ).to_list(10000)

    target_frameworks = await db.frameworks.find(
        {"id": {"$in": target_framework_ids}},
        {"_id": 0}
    ).to_list(100)

    source_text = f"{source_framework['name']} - {source_control['control_id']}: {source_control['title']}\n{source_control['description']}"

    target_text = "\\n\\n".join([
        f"{fw['name']}:\\n" + "\\n".join([
            f"  - {c['control_id']}: {c['title']} - {c['description'][:150]}"
            for c in target_controls if c['framework_id'] == fw['id']
        ][:20])
        for fw in target_frameworks
    ])

    api_key = os.environ.get('EMERGENT_LLM_KEY')
    chat = LlmChat(
        api_key=api_key,
        session_id=f"cross-map-{uuid.uuid4()}",
        system_message="You are a compliance expert that maps controls across different frameworks. Analyze controls and suggest which ones are related, indicating the strength of the relationship (direct, partial, related)."
    ).with_model("openai", "gpt-5.2")

    prompt = f"""Analyze this source control and suggest mappings to related controls in the target frameworks.

SOURCE CONTROL:
{source_text}

TARGET FRAMEWORKS AND CONTROLS:
{target_text}

For each relevant mapping, provide:
1. Target control ID
2. Mapping strength: "direct" (nearly identical), "partial" (overlapping), or "related" (complementary)
3. Brief explanation of the relationship

Format as JSON array: [{{"control_id": "...", "strength": "direct|partial|related", "explanation": "..."}}]"""

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        return {
            "source_control": source_control,
            "suggested_mappings": response,
            "target_frameworks": [fw['name'] for fw in target_frameworks]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI mapping failed: {str(e)}")
