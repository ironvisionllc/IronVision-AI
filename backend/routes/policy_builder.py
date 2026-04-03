"""
Policy Builder backend routes.
Supports questionnaire-based policy creation for NIST 800-53 control families.
Answers are stored locally; policy generation can invoke IronVision Lambda.
"""
import json
import pathlib
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
import uuid
import os
import json

from database import db
from utils import get_current_user, guard_demo, log_activity

router = APIRouter()

CONTROL_FAMILY_NAMES = {
    "AC": "Access Control",
    "AT": "Awareness and Training",
    "AU": "Audit and Accountability",
    "CA": "Assessment, Authorization, and Monitoring",
    "CM": "Configuration Management",
    "CP": "Contingency Planning",
    "IA": "Identification and Authentication",
    "IR": "Incident Response",
    "MA": "Maintenance",
    "MP": "Media Protection",
    "PE": "Physical and Environmental Protection",
    "PL": "Planning",
    "PM": "Program Management",
    "PS": "Personnel Security",
    "PT": "PII Processing and Transparency",
    "RA": "Risk Assessment",
    "SA": "System and Services Acquisition",
    "SC": "System and Communications Protection",
    "SI": "System and Information Integrity",
    "SR": "Supply Chain Risk Management",
}


class DraftCreate(BaseModel):
    policy_name: str
    framework: str = "nist-800-53"
    control_family: str
    answers: Dict[str, str] = {}


class DraftUpdate(BaseModel):
    policy_name: Optional[str] = None
    answers: Optional[Dict[str, str]] = None
    status: Optional[str] = None


class GenerateRequest(BaseModel):
    draft_id: str


# Load questionnaire data
_QUESTIONS_PATH = pathlib.Path(__file__).parent.parent / "nist_questionnaire_data.json"
_QUESTIONS_CACHE = None

def _load_questions():
    global _QUESTIONS_CACHE
    if _QUESTIONS_CACHE is None:
        with open(_QUESTIONS_PATH) as f:
            _QUESTIONS_CACHE = json.load(f)
    return _QUESTIONS_CACHE


@router.get("/policy-builder/questions/{control_family}")
async def get_questions(control_family: str, current_user: Dict = Depends(get_current_user)):
    questions = _load_questions()
    cf = control_family.upper()
    if cf not in questions:
        raise HTTPException(status_code=404, detail=f"No questions for control family: {cf}")
    return {
        "control_family": cf,
        "control_family_name": CONTROL_FAMILY_NAMES.get(cf, cf),
        "questions": questions[cf],
        "total": len(questions[cf]),
    }


# ── Control Families ─────────────────────────────────────────────────
@router.get("/policy-builder/control-families")
async def get_control_families(current_user: Dict = Depends(get_current_user)):
    return [{"id": k, "name": v} for k, v in CONTROL_FAMILY_NAMES.items()]


# ── Drafts CRUD ──────────────────────────────────────────────────────
@router.get("/policy-builder/drafts")
async def list_drafts(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    drafts = await db.policy_drafts.find({"organization_id": org_id}, {"_id": 0}).sort("updated_at", -1).to_list(200)
    return drafts


@router.get("/policy-builder/drafts/{draft_id}")
async def get_draft(draft_id: str, current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    draft = await db.policy_drafts.find_one({"id": draft_id, "organization_id": org_id}, {"_id": 0})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")
    return draft


@router.post("/policy-builder/drafts")
async def create_draft(data: DraftCreate, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "user_id": current_user["id"],
        "policy_name": data.policy_name,
        "framework": data.framework,
        "control_family": data.control_family,
        "control_family_name": CONTROL_FAMILY_NAMES.get(data.control_family, data.control_family),
        "answers": data.answers,
        "status": "draft",
        "answered_count": sum(1 for v in data.answers.values() if v.strip()),
        "created_at": now,
        "updated_at": now,
    }
    await db.policy_drafts.insert_one(doc)
    await log_activity(org_id, current_user["id"], current_user.get("name", ""), "policy_created", f"Started policy draft: {data.policy_name}")
    doc.pop("_id", None)
    return doc


@router.put("/policy-builder/drafts/{draft_id}")
async def update_draft(draft_id: str, data: DraftUpdate, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    existing = await db.policy_drafts.find_one({"id": draft_id, "organization_id": org_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Draft not found")

    update = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if data.policy_name is not None:
        update["policy_name"] = data.policy_name
    if data.answers is not None:
        update["answers"] = data.answers
        update["answered_count"] = sum(1 for v in data.answers.values() if v.strip())
    if data.status is not None:
        update["status"] = data.status

    await db.policy_drafts.update_one({"id": draft_id}, {"$set": update})
    updated = await db.policy_drafts.find_one({"id": draft_id}, {"_id": 0})
    return updated


@router.delete("/policy-builder/drafts/{draft_id}")
async def delete_draft(draft_id: str, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    result = await db.policy_drafts.delete_one({"id": draft_id, "organization_id": org_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Draft not found")
    return {"message": "Draft deleted"}


# ── Generate Policy (invoke Lambda or local generation) ──────────────
@router.post("/policy-builder/generate")
async def generate_policy(data: GenerateRequest, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    draft = await db.policy_drafts.find_one({"id": data.draft_id, "organization_id": org_id}, {"_id": 0})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Mark as generating
    await db.policy_drafts.update_one({"id": data.draft_id}, {"$set": {"status": "generating"}})

    # Try to invoke IronVision's Lambda for generation
    try:
        import boto3
        lambda_fn = os.environ.get("POLICY_GENERATION_LAMBDA_FUNCTION_NAME")
        if lambda_fn:
            client = boto3.client(
                "lambda",
                region_name=os.environ.get("AWS_REGION", "us-east-1"),
                aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            )
            payload = {
                "userId": current_user["id"],
                "policyName": draft["policy_name"],
                "framework": draft["framework"],
                "controlFamily": draft["control_family"],
                "answers": draft["answers"],
            }
            response = client.invoke(
                FunctionName=lambda_fn,
                InvocationType="Event",
                Payload=json.dumps(payload).encode(),
            )
            await db.policy_drafts.update_one(
                {"id": data.draft_id},
                {"$set": {"status": "generating", "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            await log_activity(org_id, current_user["id"], current_user.get("name", ""), "policy_created", f"Submitted for generation: {draft['policy_name']}")
            return {"message": "Policy generation started via Lambda", "status": "generating", "draft_id": data.draft_id}
    except Exception as e:
        # Lambda not available - mark as submitted
        pass

    # Fallback: mark as submitted (Lambda not configured or failed)
    await db.policy_drafts.update_one(
        {"id": data.draft_id},
        {"$set": {"status": "submitted", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    await log_activity(org_id, current_user["id"], current_user.get("name", ""), "policy_created", f"Policy generation requested: {draft['policy_name']}")
    return {"message": "Policy generation submitted", "status": "submitted", "draft_id": data.draft_id}
