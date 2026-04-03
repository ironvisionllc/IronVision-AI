from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from datetime import datetime, timezone
import os
import uuid

from emergentintegrations.llm.chat import LlmChat, UserMessage

from database import db
from utils import get_current_user

router = APIRouter()


@router.get("/analytics/dashboard")
async def get_dashboard_analytics(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    policies_count = await db.policies.count_documents({"organization_id": org_id})
    mappings_count = await db.mappings.count_documents({"organization_id": org_id})
    risks_count = await db.risks.count_documents({"organization_id": org_id, "status": "open"})
    audits_count = await db.audits.count_documents({"organization_id": org_id})

    risks = await db.risks.find({"organization_id": org_id}, {"_id": 0}).to_list(1000)
    risk_by_level = {"low": 0, "medium": 0, "high": 0, "critical": 0}
    # Build risk heatmap: 5x5 grid of likelihood x impact
    risk_heatmap = [[0]*5 for _ in range(5)]
    for risk in risks:
        score = risk.get("risk_score", 0)
        if score <= 5:
            risk_by_level["low"] += 1
        elif score <= 12:
            risk_by_level["medium"] += 1
        elif score <= 20:
            risk_by_level["high"] += 1
        else:
            risk_by_level["critical"] += 1
        lk = min(max(risk.get("likelihood", 1), 1), 5) - 1
        imp = min(max(risk.get("impact", 1), 1), 5) - 1
        risk_heatmap[lk][imp] += 1

    # Recent activity (last 8)
    recent_activity = await db.activity_log.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("timestamp", -1).to_list(8)

    # Upcoming deadlines: tasks not done with due_date in next 14 days
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from datetime import timedelta
    future_str = (datetime.now(timezone.utc) + timedelta(days=14)).strftime("%Y-%m-%d")
    tasks = await db.tasks.find(
        {"organization_id": org_id, "status": {"$ne": "done"}}, {"_id": 0}
    ).to_list(1000)
    upcoming_deadlines = []
    overdue_tasks = []
    for t in tasks:
        dd = t.get("due_date", "")
        if not dd:
            continue
        if dd < now_str:
            overdue_tasks.append({"id": t["id"], "title": t["title"], "due_date": dd, "priority": t.get("priority", "medium"), "status": t.get("status", "todo")})
        elif dd <= future_str:
            upcoming_deadlines.append({"id": t["id"], "title": t["title"], "due_date": dd, "priority": t.get("priority", "medium"), "status": t.get("status", "todo")})
    upcoming_deadlines.sort(key=lambda x: x["due_date"])
    overdue_tasks.sort(key=lambda x: x["due_date"])

    return {
        "policies_count": policies_count,
        "mappings_count": mappings_count,
        "open_risks_count": risks_count,
        "audits_count": audits_count,
        "risk_distribution": risk_by_level,
        "risk_heatmap": risk_heatmap,
        "recent_activity": recent_activity,
        "upcoming_deadlines": upcoming_deadlines[:6],
        "overdue_tasks": overdue_tasks[:6],
    }


@router.post("/analytics/predict")
async def predict_compliance_issues(data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    policies = await db.policies.find({"organization_id": org_id}, {"_id": 0}).to_list(100)
    risks = await db.risks.find({"organization_id": org_id, "status": "open"}, {"_id": 0}).to_list(100)
    mappings = await db.mappings.find({"organization_id": org_id}, {"_id": 0}).to_list(1000)

    context = f"""Organization has:
- {len(policies)} policies
- {len(risks)} open risks
- {len(mappings)} control mappings

Recent risks: {[r.get('title', '') for r in risks[:5]]}
"""

    api_key = os.environ.get('EMERGENT_LLM_KEY')
    chat = LlmChat(
        api_key=api_key,
        session_id=f"predict-{uuid.uuid4()}",
        system_message="You are a compliance analytics expert. Analyze organizational data and predict potential compliance issues."
    ).with_model("openai", "gpt-5.2")

    prompt = f"{context}\n\nBased on this data, predict 3-5 potential compliance issues or gaps that might arise. For each, provide severity (low/medium/high) and recommended action."

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        return {"predictions": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction failed: {str(e)}")
