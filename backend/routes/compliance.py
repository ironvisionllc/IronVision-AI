from fastapi import APIRouter, Depends
from typing import Dict

from database import db
from utils import get_current_user, get_compliance_grade

router = APIRouter()


@router.get("/compliance/score/{framework_id}")
async def get_compliance_score(framework_id: str, current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    all_controls = await db.controls.find({"framework_id": framework_id}, {"_id": 0}).to_list(10000)
    total_controls = len(all_controls)

    if total_controls == 0:
        return {"score": 0, "message": "No controls found for this framework"}

    mappings = await db.mappings.find({
        "organization_id": org_id,
        "framework_id": framework_id
    }, {"_id": 0}).to_list(10000)

    mapped_control_ids = set(m["control_id"] for m in mappings)
    mapped_controls = len(mapped_control_ids)
    score = int((mapped_controls / total_controls) * 100) if total_controls > 0 else 0

    framework = await db.frameworks.find_one({"id": framework_id}, {"_id": 0})

    return {
        "framework_id": framework_id,
        "framework_name": framework.get("name", "Unknown") if framework else "Unknown",
        "total_controls": total_controls,
        "mapped_controls": mapped_controls,
        "unmapped_controls": total_controls - mapped_controls,
        "compliance_score": score,
        "grade": get_compliance_grade(score)
    }


@router.get("/compliance/scores/all")
async def get_all_compliance_scores(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    frameworks = await db.frameworks.find({}, {"_id": 0}).to_list(100)

    scores = []
    for fw in frameworks:
        controls_count = await db.controls.count_documents({"framework_id": fw["id"]})

        mappings = await db.mappings.find({
            "organization_id": org_id,
            "framework_id": fw["id"]
        }, {"_id": 0}).to_list(10000)

        mapped_control_ids = set(m["control_id"] for m in mappings)
        mapped_count = len(mapped_control_ids)
        score = int((mapped_count / controls_count) * 100) if controls_count > 0 else 0

        scores.append({
            "framework_id": fw["id"],
            "framework_name": fw["name"],
            "total_controls": controls_count,
            "mapped_controls": mapped_count,
            "compliance_score": score,
            "grade": get_compliance_grade(score)
        })

    overall_score = int(sum(s["compliance_score"] for s in scores) / len(scores)) if scores else 0

    return {
        "overall_compliance_score": overall_score,
        "overall_grade": get_compliance_grade(overall_score),
        "frameworks": scores
    }


@router.get("/compliance/coverage-matrix")
async def get_coverage_matrix(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    frameworks = await db.frameworks.find({}, {"_id": 0, "name": 1, "id": 1}).to_list(100)
    policies = await db.policies.find({"organization_id": org_id}, {"_id": 0, "id": 1, "title": 1}).to_list(1000)

    matrix = []
    for policy in policies:
        policy_row = {
            "policy_id": policy["id"],
            "policy_title": policy["title"],
            "framework_coverage": {}
        }

        for fw in frameworks:
            mapping_count = await db.mappings.count_documents({
                "organization_id": org_id,
                "policy_id": policy["id"],
                "framework_id": fw["id"]
            })
            policy_row["framework_coverage"][fw["name"]] = mapping_count

        matrix.append(policy_row)

    return {
        "frameworks": [fw["name"] for fw in frameworks],
        "coverage_matrix": matrix
    }
