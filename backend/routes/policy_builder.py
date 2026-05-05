"""
Policy Builder backend routes.
Supports questionnaire-based policy creation for NIST 800-53 control families.
Answers are stored locally; policy generation can invoke IronVision Lambda.
"""
import asyncio
import json
import logging
import pathlib
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from typing import Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
import uuid
import os

from database import db
from utils import get_current_user, guard_demo, log_activity

logger = logging.getLogger(__name__)
router = APIRouter()

# Module-level cached clients (avoid 1-2s cold init per request)
_lambda_client = None
_atlas_client = None


def _get_lambda_client():
    """Lazy-initialize boto3 Lambda client once per worker."""
    global _lambda_client
    if _lambda_client is None:
        import boto3
        from botocore.config import Config
        _lambda_client = boto3.client(
            "lambda",
            region_name=os.environ.get("AWS_REGION", "us-east-1"),
            aws_access_key_id=os.environ.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("AWS_SECRET_ACCESS_KEY"),
            config=Config(connect_timeout=5, read_timeout=10, retries={"max_attempts": 2}),
        )
    return _lambda_client


def _get_atlas_db():
    """Lazy-initialize Atlas client once per worker."""
    global _atlas_client
    if _atlas_client is None:
        from motor.motor_asyncio import AsyncIOMotorClient
        atlas_uri = os.environ.get("IRONVISION_MONGO_URI")
        if not atlas_uri:
            return None
        _atlas_client = AsyncIOMotorClient(atlas_uri)
    return _atlas_client["ironvision"]

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

async def _invoke_lambda_background(lambda_fn: str, payload: dict, job_id: str):
    """
    Fire the Lambda invoke in a background task so the HTTP handler can
    return the job_id to the client immediately (client starts polling).
    Wraps the sync boto3 call in asyncio.to_thread so the event loop stays free.
    On failure, write a 'failed' status to analysisprogresses so the polling
    endpoint reports the error instead of hanging in 'unknown' forever.
    """
    try:
        client = _get_lambda_client()
        await asyncio.to_thread(
            client.invoke,
            FunctionName=lambda_fn,
            InvocationType="Event",
            Payload=json.dumps(payload).encode(),
        )
        logger.info(f"Lambda invoke dispatched for job {job_id}")
    except Exception as e:
        logger.error(f"Lambda invoke failed for job {job_id}: {e}")
        # Surface the failure to the polling endpoint
        try:
            atlas_db = _get_atlas_db()
            if atlas_db is not None:
                await atlas_db.analysisprogresses.update_one(
                    {"jobId": job_id},
                    {"$set": {
                        "status": f"Failed to invoke generator: {str(e)[:200]}",
                        "progress": 0,
                        "updatedAt": datetime.now(timezone.utc),
                    }},
                )
        except Exception as write_err:
            logger.error(f"Failed to write failure status for job {job_id}: {write_err}")


@router.post("/policy-builder/generate")
async def generate_policy(
    data: GenerateRequest,
    background_tasks: BackgroundTasks,
    current_user: Dict = Depends(get_current_user),
):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    draft = await db.policy_drafts.find_one({"id": data.draft_id, "organization_id": org_id}, {"_id": 0})
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found")

    # Mark as generating
    await db.policy_drafts.update_one({"id": data.draft_id}, {"$set": {"status": "generating"}})

    # Try to invoke IronVision's Lambda for generation
    try:
        from bson import ObjectId
        import time
        import random
        import string

        lambda_fn = os.environ.get("POLICY_GENERATION_LAMBDA_FUNCTION_NAME")
        atlas_db = _get_atlas_db()

        if lambda_fn and atlas_db is not None:
            # Generate job ID in IronVision's format
            timestamp = int(time.time() * 1000)
            random_suffix = ''.join(random.choices(string.hexdigits.lower(), k=8))
            job_id = f"policy_gen_{timestamp}_{random_suffix}"

            # Get or create a mapping user ID (use existing IronVision user)
            iv_user = await atlas_db.users.find_one({}, {"_id": 1})
            iv_user_id = iv_user["_id"] if iv_user else ObjectId()

            # Get the controlquestions document for this control family
            control_family = draft["control_family"]
            cq_doc = await atlas_db.controlquestions.find_one({"controlFamily": control_family})
            if not cq_doc:
                raise HTTPException(status_code=400, detail=f"Control family {control_family} not found in IronVision")

            cq_id = cq_doc["_id"]
            questions_list = cq_doc.get("questions", [])

            # Convert our answers dict to IronVision's format (indexed by question number)
            formatted_answers = {}
            for key, value in draft["answers"].items():
                if key.startswith("q"):
                    idx = int(key[1:]) - 1
                    formatted_answers[str(idx)] = value
                else:
                    formatted_answers[key] = value

            # Create controlquestionanswers record in Atlas
            cqa_doc = {
                "userId": str(iv_user_id),
                "policyName": draft["policy_name"],
                "framework": "NIST 800-53",
                "controlFamily": control_family,
                "controlQuestionsId": cq_id,
                "status": "generating",
                "answers": formatted_answers,
                "createdAt": datetime.now(timezone.utc),
                "updatedAt": datetime.now(timezone.utc),
                "generationJobId": job_id,
                "emergentDraftId": data.draft_id,
            }
            cqa_result = await atlas_db.controlquestionanswers.insert_one(cqa_doc)
            cqa_id = cqa_result.inserted_id

            # Build progress doc + local-update concurrently — saves ~500ms-1s
            progress_doc = {
                "jobId": job_id,
                "userId": iv_user_id,
                "filename": f"Policy: {draft['policy_name']}",
                "s3Key": f"policies/{str(cqa_id)}",
                "fileType": "policy-generation",
                "progress": 0,
                "status": "Initializing policy generation...",
                "metadata": {
                    "framework": "NIST 800-53",
                    "controlFamily": control_family,
                    "draftId": str(cqa_id),
                    "policyName": draft["policy_name"],
                    "emergentDraftId": data.draft_id,
                },
                "createdAt": datetime.now(timezone.utc),
                "updatedAt": datetime.now(timezone.utc),
                "__v": 0
            }
            await asyncio.gather(
                atlas_db.analysisprogresses.insert_one(progress_doc),
                db.policy_drafts.update_one(
                    {"id": data.draft_id},
                    {"$set": {
                        "atlas_job_id": job_id,
                        "atlas_cqa_id": str(cqa_id),
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }}
                ),
            )

            # Build answers array in Lambda's expected format
            answers_array = []
            for i, question_text in enumerate(questions_list):
                idx_str = str(i)
                if idx_str in formatted_answers:
                    answers_array.append({
                        "question": question_text,
                        "answer": formatted_answers[idx_str]
                    })

            payload = {
                "jobId": job_id,
                "draftId": str(cqa_id),
                "userId": str(iv_user_id),
                "policyName": draft["policy_name"],
                "framework": "NIST 800-53",
                "controlFamily": control_family,
                "answers": answers_array,
                "metadata": {
                    "framework": "NIST 800-53",
                    "controlFamily": control_family,
                    "draftId": str(cqa_id),
                    "policyName": draft["policy_name"],
                    "emergentDraftId": data.draft_id,
                    "organizationId": org_id,
                    "organizationName": draft.get("organization_name", "Organization"),
                    "userEmail": current_user.get("email", ""),
                    "userName": current_user.get("name", ""),
                    "source": "emergent-platform"
                }
            }

            # Fire Lambda invoke in background — handler returns IMMEDIATELY with job_id
            background_tasks.add_task(_invoke_lambda_background, lambda_fn, payload, job_id)

            await log_activity(org_id, current_user["id"], current_user.get("name", ""), "policy_created", f"Submitted for generation: {draft['policy_name']}")
            return {
                "message": "Policy generation started — poll for progress",
                "status": "generating",
                "draft_id": data.draft_id,
                "job_id": job_id,
                "atlas_cqa_id": str(cqa_id)
            }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Policy generation setup failed: {e}")
        # Revert status on error
        await db.policy_drafts.update_one({"id": data.draft_id}, {"$set": {"status": "draft"}})
        raise HTTPException(status_code=500, detail=f"Policy generation failed: {str(e)}")

    # Fallback: mark as submitted (Lambda not configured or failed)
    await db.policy_drafts.update_one(
        {"id": data.draft_id},
        {"$set": {"status": "submitted", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    await log_activity(org_id, current_user["id"], current_user.get("name", ""), "policy_created", f"Policy generation requested: {draft['policy_name']}")
    return {"message": "Policy generation submitted", "status": "submitted", "draft_id": data.draft_id}


# ── Live Job Status Polling ──────────────────────────────────────────
@router.get("/policy-builder/jobs/{job_id}/status")
async def get_generation_job_status(job_id: str, current_user: Dict = Depends(get_current_user)):
    """
    Poll the live status of a policy generation job.
    Reads `analysisprogresses` (live progress) and `createdpolicies` (final result)
    from IronVision Atlas. Returns:
      - status: 'generating' | 'completed' | 'failed' | 'unknown'
      - progress: 0-100
      - message: human-readable status text
      - policy_id: Atlas ObjectId (string) of completed policy, if done
      - policy_name: for display
    """
    atlas_db = _get_atlas_db()
    if atlas_db is None:
        raise HTTPException(status_code=503, detail="IronVision Atlas not configured")

    # Run both lookups in parallel for snappy polling
    progress_doc, policy_doc = await asyncio.gather(
        atlas_db.analysisprogresses.find_one({"jobId": job_id}, sort=[("updatedAt", -1)]),
        atlas_db.createdpolicies.find_one({"generationJobId": job_id}),
    )

    # Completed: a final policy document exists
    if policy_doc:
        return {
            "status": "completed",
            "progress": 100,
            "message": "Policy generation complete",
            "policy_id": str(policy_doc["_id"]),
            "policy_name": policy_doc.get("policyName", ""),
            "framework": policy_doc.get("framework", ""),
            "control_family": policy_doc.get("controlFamily", ""),
        }

    # Still in flight: read live progress
    if progress_doc:
        raw_status = (progress_doc.get("status") or "").lower()
        if "fail" in raw_status or "error" in raw_status:
            return {
                "status": "failed",
                "progress": progress_doc.get("progress", 0),
                "message": progress_doc.get("status", "Generation failed"),
                "policy_id": None,
            }
        return {
            "status": "generating",
            "progress": progress_doc.get("progress", 0),
            "message": progress_doc.get("status", "Generating policy..."),
            "policy_id": None,
        }

    # No record yet — Lambda hasn't picked it up
    return {
        "status": "unknown",
        "progress": 0,
        "message": "Waiting for generator to pick up the job...",
        "policy_id": None,
    }

