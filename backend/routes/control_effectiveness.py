"""
Control Effectiveness Score - Calculates real-time effectiveness scores (0-100)
for controls based on evidence, mappings, test results, and attestation data.
Supports manual override.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Optional, List
from datetime import datetime, timezone
import uuid
import logging

from database import db
from utils import get_current_user, guard_demo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/control-effectiveness", tags=["control-effectiveness"])


class OverrideRequest(BaseModel):
    score: int
    reason: str


class EffectivenessResponse(BaseModel):
    framework_id: str
    control_id: str
    auto_score: int
    manual_override: Optional[int] = None
    override_reason: Optional[str] = None
    final_score: int
    grade: str
    factors: dict
    last_updated: str


def _calc_grade(score: int) -> str:
    if score >= 90:
        return "Excellent"
    elif score >= 75:
        return "Good"
    elif score >= 60:
        return "Fair"
    elif score >= 40:
        return "Needs Improvement"
    else:
        return "Critical"


async def _calculate_auto_score(framework_id: str, control_id: str, org_id: str) -> tuple:
    """Calculate the automatic effectiveness score. Returns (score, factors_dict)."""

    factors = {
        "policy_mapping": 0,
        "evidence_coverage": 0,
        "cci_completion": 0,
        "risk_exposure": 0,
        "recency": 0,
    }

    # 1. Policy Mapping (0-25 pts) — Does this control have mapped policies?
    mapping_count = await db.mappings.count_documents({
        "organization_id": org_id,
        "framework_id": framework_id,
        "control_id": control_id,
    })
    if mapping_count >= 3:
        factors["policy_mapping"] = 25
    elif mapping_count >= 2:
        factors["policy_mapping"] = 20
    elif mapping_count >= 1:
        factors["policy_mapping"] = 15
    else:
        factors["policy_mapping"] = 0

    # 2. Evidence Coverage (0-25 pts)
    evidence_count = await db.evidence.count_documents({
        "organization_id": org_id,
        "framework_id": framework_id,
    })
    if evidence_count >= 5:
        factors["evidence_coverage"] = 25
    elif evidence_count >= 3:
        factors["evidence_coverage"] = 20
    elif evidence_count >= 1:
        factors["evidence_coverage"] = 12
    else:
        factors["evidence_coverage"] = 0

    # 3. CCI Completion (0-20 pts) — How many sub-controls (CCIs) are addressed?
    total_ccis = await db.ccis.count_documents({
        "framework_id": framework_id,
        "parent_control_id": control_id,
    })
    if total_ccis > 0:
        # Check for CCI answers/attestations
        from ironvision_db import get_ironvision_db
        iv_db = get_ironvision_db()
        answered_ccis = 0
        if iv_db is not None:
            answered_ccis = await iv_db.controlquestionanswers.count_documents({
                "frameworkId": framework_id,
            })
        completion_ratio = min(answered_ccis / max(total_ccis, 1), 1.0)
        factors["cci_completion"] = int(completion_ratio * 20)
    else:
        factors["cci_completion"] = 10  # No CCIs = neutral

    # 4. Risk Exposure (0-15 pts) — Fewer associated open risks = higher score
    open_risks = await db.risks.count_documents({
        "organization_id": org_id,
        "status": {"$in": ["open", "identified"]},
    })
    if open_risks == 0:
        factors["risk_exposure"] = 15
    elif open_risks <= 2:
        factors["risk_exposure"] = 10
    elif open_risks <= 5:
        factors["risk_exposure"] = 5
    else:
        factors["risk_exposure"] = 0

    # 5. Recency (0-15 pts) — Recent activity indicates active management
    recent_tasks = await db.tasks.count_documents({
        "organization_id": org_id,
        "status": "done",
    })
    if recent_tasks >= 5:
        factors["recency"] = 15
    elif recent_tasks >= 2:
        factors["recency"] = 10
    elif recent_tasks >= 1:
        factors["recency"] = 5
    else:
        factors["recency"] = 0

    total = sum(factors.values())
    return min(total, 100), factors


# NOTE: Summary route MUST be defined BEFORE the generic /{framework_id}/{control_id} route
# to prevent "summary" from being matched as a framework_id
@router.get("/summary/{framework_id}")
async def get_framework_effectiveness_summary(
    framework_id: str,
    current_user: Dict = Depends(get_current_user)
):
    """Get aggregated effectiveness summary for a framework."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    controls = await db.controls.find(
        {"framework_id": framework_id},
        {"_id": 0, "control_id": 1, "title": 1, "category": 1}
    ).to_list(500)

    results = []
    total_score = 0
    for ctrl in controls[:50]:  # Limit to first 50 for performance
        auto_score, factors = await _calculate_auto_score(framework_id, ctrl["control_id"], org_id)
        override = await db.control_overrides.find_one(
            {"framework_id": framework_id, "control_id": ctrl["control_id"], "organization_id": org_id},
            {"_id": 0}
        )
        final_score = override["score"] if override else auto_score
        total_score += final_score
        results.append({
            "control_id": ctrl["control_id"],
            "title": ctrl.get("title", ""),
            "category": ctrl.get("category", ""),
            "score": final_score,
            "grade": _calc_grade(final_score),
            "has_override": override is not None,
        })

    avg_score = int(total_score / max(len(results), 1))

    return {
        "framework_id": framework_id,
        "average_score": avg_score,
        "average_grade": _calc_grade(avg_score),
        "total_controls": len(results),
        "controls": results,
        "distribution": {
            "excellent": len([r for r in results if r["score"] >= 90]),
            "good": len([r for r in results if 75 <= r["score"] < 90]),
            "fair": len([r for r in results if 60 <= r["score"] < 75]),
            "needs_improvement": len([r for r in results if 40 <= r["score"] < 60]),
            "critical": len([r for r in results if r["score"] < 40]),
        }
    }


@router.get("/{framework_id}/{control_id}")
async def get_effectiveness(
    framework_id: str, control_id: str,
    current_user: Dict = Depends(get_current_user)
):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    auto_score, factors = await _calculate_auto_score(framework_id, control_id, org_id)

    # Check for manual override
    override = await db.control_overrides.find_one(
        {"framework_id": framework_id, "control_id": control_id, "organization_id": org_id},
        {"_id": 0}
    )

    manual_score = override.get("score") if override else None
    override_reason = override.get("reason") if override else None
    final_score = manual_score if manual_score is not None else auto_score

    return EffectivenessResponse(
        framework_id=framework_id,
        control_id=control_id,
        auto_score=auto_score,
        manual_override=manual_score,
        override_reason=override_reason,
        final_score=final_score,
        grade=_calc_grade(final_score),
        factors=factors,
        last_updated=datetime.now(timezone.utc).isoformat(),
    )


@router.put("/{framework_id}/{control_id}/override")
async def set_override(
    framework_id: str, control_id: str,
    req: OverrideRequest,
    current_user: Dict = Depends(get_current_user)
):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    if req.score < 0 or req.score > 100:
        raise HTTPException(status_code=400, detail="Score must be between 0 and 100")

    now = datetime.now(timezone.utc).isoformat()
    await db.control_overrides.update_one(
        {"framework_id": framework_id, "control_id": control_id, "organization_id": org_id},
        {"$set": {
            "framework_id": framework_id,
            "control_id": control_id,
            "organization_id": org_id,
            "score": req.score,
            "reason": req.reason,
            "overridden_by": current_user["id"],
            "overridden_by_name": current_user.get("name", ""),
            "updated_at": now,
        }, "$setOnInsert": {"created_at": now}},
        upsert=True
    )
    return {"status": "saved", "score": req.score, "grade": _calc_grade(req.score)}


@router.delete("/{framework_id}/{control_id}/override")
async def clear_override(
    framework_id: str, control_id: str,
    current_user: Dict = Depends(get_current_user)
):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    await db.control_overrides.delete_one(
        {"framework_id": framework_id, "control_id": control_id, "organization_id": org_id}
    )
    return {"status": "cleared"}
