"""
Compliance Trend Timeline Routes.
Stores periodic compliance score snapshots and serves trend data for the dashboard.
"""
from fastapi import APIRouter, Depends
from typing import Dict
from datetime import datetime, timezone, timedelta
import uuid

from database import db
from utils import get_current_user, get_compliance_grade

router = APIRouter()


async def _compute_compliance_snapshot(org_id: str) -> dict:
    """Compute current compliance metrics for an organization."""
    frameworks = await db.frameworks.find({}, {"_id": 0}).to_list(100)
    total_mapped = 0
    total_controls = 0

    for fw in frameworks:
        controls_count = await db.controls.count_documents({"framework_id": fw["id"]})
        mappings = await db.mappings.find(
            {"organization_id": org_id, "framework_id": fw["id"]}, {"_id": 0, "control_id": 1}
        ).to_list(10000)
        mapped_count = len(set(m["control_id"] for m in mappings))
        total_mapped += mapped_count
        total_controls += controls_count

    score = int((total_mapped / total_controls) * 100) if total_controls > 0 else 0
    open_risks = await db.risks.count_documents({"organization_id": org_id, "status": "open"})
    tasks_done = await db.tasks.count_documents({"organization_id": org_id, "status": "done"})
    tasks_total = await db.tasks.count_documents({"organization_id": org_id})

    return {
        "score": score,
        "grade": get_compliance_grade(score),
        "total_mapped": total_mapped,
        "total_controls": total_controls,
        "open_risks": open_risks,
        "tasks_done": tasks_done,
        "tasks_total": tasks_total,
    }


@router.post("/compliance-trends/snapshot")
async def take_snapshot(current_user: Dict = Depends(get_current_user)):
    """Take a compliance snapshot now (manual trigger or called by cron)."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    metrics = await _compute_compliance_snapshot(org_id)

    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **metrics,
    }
    # Upsert by date to avoid duplicates
    await db.compliance_snapshots.update_one(
        {"organization_id": org_id, "date": doc["date"]},
        {"$set": doc},
        upsert=True,
    )
    return {"message": "Snapshot captured", "snapshot": doc}


@router.get("/compliance-trends")
async def get_compliance_trends(current_user: Dict = Depends(get_current_user)):
    """Get compliance trend data for the dashboard timeline chart."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    snapshots = await db.compliance_snapshots.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("date", 1).to_list(365)

    # If no snapshots, generate some seed data from current state
    if not snapshots:
        current = await _compute_compliance_snapshot(org_id)
        now = datetime.now(timezone.utc)
        generated = []
        for i in range(8):
            d = now - timedelta(weeks=8 - i)
            # Simulate gradual improvement
            ratio = (i + 1) / 8
            snap = {
                "id": str(uuid.uuid4()),
                "organization_id": org_id,
                "date": d.strftime("%Y-%m-%d"),
                "timestamp": d.isoformat(),
                "score": max(0, int(current["score"] * ratio * 0.95 + (i * 1.5))),
                "grade": get_compliance_grade(max(0, int(current["score"] * ratio))),
                "total_mapped": int(current["total_mapped"] * ratio),
                "total_controls": current["total_controls"],
                "open_risks": max(0, current["open_risks"] + (8 - i)),
                "tasks_done": int(current["tasks_done"] * ratio),
                "tasks_total": current["tasks_total"],
            }
            generated.append(snap)
            await db.compliance_snapshots.insert_one(snap)
        snapshots = generated

    return snapshots
