from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from datetime import datetime, timezone, timedelta

from database import db
from utils import get_current_user, guard_demo, hash_password, verify_password

router = APIRouter()


# === Admin User Management ===

@router.get("/admin/users")
async def get_all_users(current_user: Dict = Depends(get_current_user)):
    if current_user["roles"][0]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    org_id = current_user["roles"][0]["organization_id"]
    users = await db.users.find(
        {"roles.organization_id": org_id},
        {"_id": 0, "password_hash": 0}
    ).to_list(1000)
    return users


@router.post("/admin/users")
async def create_user(data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    if current_user["roles"][0]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    existing = await db.users.find_one({"email": data["email"]})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    org_id = current_user["roles"][0]["organization_id"]
    from models import User, UserRole

    user = User(
        email=data["email"],
        name=data["name"],
        roles=[UserRole(role=data["role"], organization_id=org_id)]
    )

    user_doc = user.model_dump()
    user_doc["password_hash"] = hash_password(data["password"])
    user_doc["created_at"] = user_doc["created_at"].isoformat()

    await db.users.insert_one(user_doc)
    user_doc.pop("password_hash")
    return user_doc


@router.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, current_user: Dict = Depends(get_current_user)):
    if current_user["roles"][0]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")

    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": "User deleted successfully"}


@router.put("/admin/users/{user_id}/role")
async def update_user_role(user_id: str, data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    if current_user["roles"][0]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    org_id = current_user["roles"][0]["organization_id"]
    new_role = data.get("role")

    if new_role not in ["admin", "auditor", "manager", "viewer"]:
        raise HTTPException(status_code=400, detail="Invalid role")

    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {"roles": [{"role": new_role, "organization_id": org_id}]}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="User not found")

    return {"message": "User role updated successfully"}


# === User Profile ===

@router.put("/users/profile")
async def update_profile(data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    update_data = {}
    if "name" in data:
        update_data["name"] = data["name"]
    if "email" in data:
        existing = await db.users.find_one({"email": data["email"], "id": {"$ne": current_user["id"]}})
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use")
        update_data["email"] = data["email"]

    if update_data:
        await db.users.update_one(
            {"id": current_user["id"]},
            {"$set": update_data}
        )

    return {"message": "Profile updated successfully"}


@router.post("/users/change-password")
async def change_password(data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    current_password = data.get("current_password")
    new_password = data.get("new_password")

    user = await db.users.find_one({"id": current_user["id"]})
    if not verify_password(current_password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    new_hash = hash_password(new_password)
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"password_hash": new_hash}}
    )

    return {"message": "Password changed successfully"}


@router.put("/admin/organization")
async def update_organization(data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    if current_user["roles"][0]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    org_id = current_user["roles"][0]["organization_id"]

    update_data = {}
    if "name" in data:
        update_data["name"] = data["name"]
    if "industry" in data:
        update_data["industry"] = data["industry"]
    if "size" in data:
        update_data["size"] = data["size"]
    if "country" in data:
        update_data["country"] = data["country"]

    if update_data:
        await db.organizations.update_one(
            {"id": org_id},
            {"$set": update_data}
        )

    return {"message": "Organization updated successfully"}


# === Trial Management ===

@router.get("/admin/trial/status")
async def get_trial_status(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"]
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})

    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    trial_end = org.get("trial_end_date")
    trial_start = org.get("trial_start_date")
    subscription_status = org.get("subscription_status", "trial")

    is_trial_active = False
    days_remaining = 0

    if trial_end:
        if isinstance(trial_end, str):
            trial_end = datetime.fromisoformat(trial_end.replace('Z', '+00:00'))

        now = datetime.now(timezone.utc)
        is_trial_active = now < trial_end and subscription_status == "trial"

        if is_trial_active:
            days_remaining = max(0, (trial_end - now).days)

    return {
        "organization_id": org_id,
        "organization_name": org.get("name"),
        "subscription_status": subscription_status,
        "trial_start_date": trial_start,
        "trial_end_date": trial_end,
        "is_trial_active": is_trial_active,
        "days_remaining": days_remaining,
        "is_expired": subscription_status == "expired"
    }


@router.post("/admin/trial/grant")
async def grant_trial(data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    if current_user["roles"][0]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    target_email = data.get("email")
    days = data.get("days", 14)

    if not target_email:
        raise HTTPException(status_code=400, detail="Email required")

    target_user = await db.users.find_one({"email": target_email})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    target_org_id = target_user["roles"][0]["organization_id"]

    trial_start = datetime.now(timezone.utc)
    trial_end = trial_start + timedelta(days=days)

    await db.organizations.update_one(
        {"id": target_org_id},
        {"$set": {
            "trial_start_date": trial_start.isoformat(),
            "trial_end_date": trial_end.isoformat(),
            "subscription_status": "trial"
        }}
    )

    return {
        "message": f"Trial granted to {target_email} for {days} days",
        "trial_end_date": trial_end.isoformat(),
        "days_granted": days
    }


@router.post("/admin/trial/extend")
async def extend_trial(data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    if current_user["roles"][0]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    org_id = current_user["roles"][0]["organization_id"]
    additional_days = data.get("days", 14)

    org = await db.organizations.find_one({"id": org_id})
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    current_end = org.get("trial_end_date")
    if current_end:
        if isinstance(current_end, str):
            current_end = datetime.fromisoformat(current_end.replace('Z', '+00:00'))
        now = datetime.now(timezone.utc)
        base_date = max(current_end, now)
    else:
        base_date = datetime.now(timezone.utc)

    new_end_date = base_date + timedelta(days=additional_days)

    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {
            "trial_end_date": new_end_date.isoformat(),
            "subscription_status": "trial"
        }}
    )

    return {
        "message": f"Trial extended by {additional_days} days",
        "new_trial_end_date": new_end_date.isoformat()
    }


@router.post("/admin/trial/activate-subscription")
async def activate_subscription(current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    if current_user["roles"][0]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    org_id = current_user["roles"][0]["organization_id"]

    await db.organizations.update_one(
        {"id": org_id},
        {"$set": {"subscription_status": "active"}}
    )

    return {"message": "Subscription activated successfully"}


@router.get("/admin/trial/all-users")
async def get_all_users_trial_status(current_user: Dict = Depends(get_current_user)):
    if current_user["roles"][0]["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    org_id = current_user["roles"][0]["organization_id"]

    users = await db.users.find(
        {"roles.organization_id": org_id},
        {"_id": 0, "password_hash": 0}
    ).to_list(1000)

    org = await db.organizations.find_one({"id": org_id}, {"_id": 0})

    trial_info = {
        "trial_end_date": org.get("trial_end_date") if org else None,
        "subscription_status": org.get("subscription_status", "trial") if org else "trial"
    }

    return {
        "users": users,
        "organization_trial": trial_info
    }
