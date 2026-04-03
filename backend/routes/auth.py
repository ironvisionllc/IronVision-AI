from fastapi import APIRouter, Depends
from typing import Dict
from datetime import datetime, timezone, timedelta
import uuid

from database import db
from models import User, UserRole, UserCreate, UserLogin, Organization
from utils import hash_password, verify_password, create_access_token, get_current_user, is_demo_account

router = APIRouter()


@router.post("/auth/register")
async def register(data: UserCreate):
    existing = await db.users.find_one({"email": data.email})
    if existing:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Email already registered")

    org_id = str(uuid.uuid4())
    if data.organization_name:
        trial_start = datetime.now(timezone.utc)
        trial_end = trial_start + timedelta(days=14)

        org = Organization(
            id=org_id,
            name=data.organization_name,
            trial_start_date=trial_start,
            trial_end_date=trial_end,
            subscription_status="trial"
        )

        org_doc = org.model_dump()
        org_doc["created_at"] = org_doc["created_at"].isoformat()
        org_doc["trial_start_date"] = org_doc["trial_start_date"].isoformat()
        org_doc["trial_end_date"] = org_doc["trial_end_date"].isoformat()
        await db.organizations.insert_one(org_doc)

    user = User(
        email=data.email,
        name=data.name,
        roles=[UserRole(role="admin", organization_id=org_id)]
    )

    user_doc = user.model_dump()
    user_doc["password_hash"] = hash_password(data.password)
    user_doc["created_at"] = user_doc["created_at"].isoformat()

    await db.users.insert_one(user_doc)

    token = create_access_token(user.id)
    return {"token": token, "user": user.model_dump()}


@router.post("/auth/login")
async def login(data: UserLogin):
    from fastapi import HTTPException
    user = await db.users.find_one({"email": data.email}, {"_id": 0})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token = create_access_token(user["id"])
    user.pop("password_hash", None)
    user["is_demo"] = is_demo_account(user)
    return {"token": token, "user": user}


@router.get("/auth/me")
async def get_me(current_user: Dict = Depends(get_current_user)):
    current_user.pop("password_hash", None)
    current_user["is_demo"] = is_demo_account(current_user)
    return current_user


@router.get("/organizations")
async def get_organizations(current_user: Dict = Depends(get_current_user)):
    org_ids = [role["organization_id"] for role in current_user.get("roles", [])]
    orgs = await db.organizations.find({"id": {"$in": org_ids}}, {"_id": 0}).to_list(100)
    return orgs
