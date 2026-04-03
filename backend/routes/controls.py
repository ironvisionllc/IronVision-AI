from fastapi import APIRouter, HTTPException, Depends
from typing import Dict

from database import db
from utils import get_current_user

router = APIRouter()


@router.get("/controls/{framework_id}/detail/{control_id}")
async def get_control_detail(framework_id: str, control_id: str, current_user: Dict = Depends(get_current_user)):
    """Get full detail of a control including CCIs and cross-framework mappings"""
    # Get the control
    control = await db.controls.find_one(
        {"framework_id": framework_id, "control_id": control_id},
        {"_id": 0}
    )
    if not control:
        raise HTTPException(status_code=404, detail="Control not found")

    # Get the framework
    framework = await db.frameworks.find_one({"id": framework_id}, {"_id": 0, "name": 1, "id": 1})

    # Get CCIs for this control
    ccis = await db.ccis.find(
        {"parent_control_id": control_id, "framework_id": framework_id},
        {"_id": 0}
    ).to_list(500)

    # Get cross-framework mappings where this control is source or target
    cross_mappings = await db.cross_framework_mappings.find({
        "$or": [
            {"source_control_id": control_id, "source_framework_id": framework_id},
            {"target_control_id": control_id, "target_framework_id": framework_id}
        ]
    }, {"_id": 0}).to_list(500)

    # Get org-level policy mappings for this control
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    policy_mappings = await db.mappings.find(
        {"organization_id": org_id, "control_id": control_id, "framework_id": framework_id},
        {"_id": 0}
    ).to_list(100)

    return {
        "control": control,
        "framework": framework,
        "ccis": ccis,
        "cci_count": len(ccis),
        "cross_framework_mappings": cross_mappings,
        "policy_mappings": policy_mappings
    }


@router.get("/ccis/{framework_id}/{control_id}")
async def get_ccis_for_control(framework_id: str, control_id: str, current_user: Dict = Depends(get_current_user)):
    """Get CCIs for a specific control"""
    ccis = await db.ccis.find(
        {"parent_control_id": control_id, "framework_id": framework_id},
        {"_id": 0}
    ).to_list(500)
    return ccis
