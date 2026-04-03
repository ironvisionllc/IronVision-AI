from fastapi import APIRouter, Depends
from typing import Dict
from datetime import datetime, timezone

from database import db
from models import Risk, RiskCreate
from utils import get_current_user, guard_demo, log_activity
from routes.notifications import notify_org_admins

router = APIRouter()


@router.get("/risks")
async def get_risks(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    risks = await db.risks.find({"organization_id": org_id}, {"_id": 0}).to_list(1000)
    return risks


@router.post("/risks")
async def create_risk(data: RiskCreate, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    risk = Risk(
        organization_id=org_id,
        title=data.title,
        description=data.description,
        category=data.category,
        likelihood=data.likelihood,
        impact=data.impact,
        status=data.status,
        owner=data.owner,
        risk_score=data.likelihood * data.impact
    )

    doc = risk.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    doc["updated_at"] = doc["updated_at"].isoformat()
    await db.risks.insert_one(doc)
    await log_activity(org_id, current_user["id"], current_user.get("name", ""), "risk_created", f"Created risk: {data.title}")

    # Notify admins of high/critical risks
    if risk.risk_score > 12:
        await notify_org_admins(
            org_id,
            "High-Risk Alert",
            f"New high-risk item: {data.title} (Score: {risk.risk_score})",
            "warning", "/risks"
        )

    return risk


@router.put("/risks/{risk_id}")
async def update_risk(risk_id: str, risk: Risk, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    risk.risk_score = risk.likelihood * risk.impact
    risk.updated_at = datetime.now(timezone.utc)

    doc = risk.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    doc["updated_at"] = doc["updated_at"].isoformat()

    await db.risks.update_one({"id": risk_id}, {"$set": doc})
    return risk
