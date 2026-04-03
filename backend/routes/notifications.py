from fastapi import APIRouter, Depends
from typing import Dict, Any
from datetime import datetime, timezone
import uuid

from database import db
from utils import get_current_user

router = APIRouter()


async def create_notification(org_id: str, user_id: str, title: str, message: str, notification_type: str = "info", link: str = ""):
    """Create a notification for a user. Called internally from other routes."""
    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "link": link,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.notifications.insert_one(doc)


async def notify_org_admins(org_id: str, title: str, message: str, notification_type: str = "info", link: str = ""):
    """Notify all admin users in an organization."""
    admins = await db.users.find(
        {"roles": {"$elemMatch": {"organization_id": org_id, "role": "admin"}}},
        {"_id": 0, "id": 1}
    ).to_list(100)
    for admin in admins:
        await create_notification(org_id, admin["id"], title, message, notification_type, link)


@router.get("/notifications")
async def get_notifications(current_user: Dict = Depends(get_current_user)):
    user_id = current_user["id"]
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    notifications = await db.notifications.find(
        {"$or": [{"user_id": user_id}, {"user_id": "all", "organization_id": org_id}]},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return notifications


@router.get("/notifications/unread-count")
async def get_unread_count(current_user: Dict = Depends(get_current_user)):
    user_id = current_user["id"]
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    count = await db.notifications.count_documents(
        {"$or": [{"user_id": user_id}, {"user_id": "all", "organization_id": org_id}], "read": False}
    )
    return {"unread_count": count}


@router.put("/notifications/{notification_id}/read")
async def mark_notification_read(notification_id: str, current_user: Dict = Depends(get_current_user)):
    await db.notifications.update_one(
        {"id": notification_id},
        {"$set": {"read": True}}
    )
    return {"message": "Notification marked as read"}


@router.put("/notifications/read-all")
async def mark_all_read(current_user: Dict = Depends(get_current_user)):
    user_id = current_user["id"]
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    await db.notifications.update_many(
        {"$or": [{"user_id": user_id}, {"user_id": "all", "organization_id": org_id}], "read": False},
        {"$set": {"read": True}}
    )
    return {"message": "All notifications marked as read"}
