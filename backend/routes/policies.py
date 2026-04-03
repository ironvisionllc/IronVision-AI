from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import Dict
from datetime import datetime, timezone
import io
import csv

from database import db
from models import Policy, PolicyCreate
from utils import get_current_user, guard_demo, log_activity

router = APIRouter()


@router.get("/policies")
async def get_policies(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    policies = await db.policies.find({"organization_id": org_id}, {"_id": 0}).to_list(1000)
    return policies


@router.post("/policies")
async def create_policy(data: PolicyCreate, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    policy = Policy(
        organization_id=org_id,
        title=data.title,
        content=data.content,
        version=data.version,
        status=data.status,
        created_by=current_user["id"]
    )

    doc = policy.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    doc["updated_at"] = doc["updated_at"].isoformat()
    await db.policies.insert_one(doc)
    await log_activity(org_id, current_user["id"], current_user.get("name", ""), "policy_created", f"Created policy: {data.title}")
    return policy


@router.put("/policies/{policy_id}")
async def update_policy(policy_id: str, policy: Policy, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    policy.updated_at = datetime.now(timezone.utc)
    doc = policy.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    doc["updated_at"] = doc["updated_at"].isoformat()

    await db.policies.update_one({"id": policy_id}, {"$set": doc})
    return policy


@router.post("/policies/bulk-upload")
async def bulk_upload_policies(file: UploadFile = File(...), current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    content = await file.read()
    decoded = content.decode('utf-8')
    csv_reader = csv.DictReader(io.StringIO(decoded))

    policies_created = 0
    for row in csv_reader:
        policy = Policy(
            organization_id=org_id,
            title=row.get("title", ""),
            content=row.get("content", ""),
            version=row.get("version", "1.0"),
            status=row.get("status", "draft"),
            created_by=current_user["id"]
        )

        doc = policy.model_dump()
        doc["created_at"] = doc["created_at"].isoformat()
        doc["updated_at"] = doc["updated_at"].isoformat()
        await db.policies.insert_one(doc)
        policies_created += 1

    return {"message": f"Successfully uploaded {policies_created} policies"}
