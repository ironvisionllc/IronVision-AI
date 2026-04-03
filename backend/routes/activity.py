from fastapi import APIRouter, Depends
from typing import Dict

from database import db
from utils import get_current_user

router = APIRouter()


@router.get("/activity")
async def get_activity_log(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    activities = await db.activity_log.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("timestamp", -1).to_list(100)
    return activities
