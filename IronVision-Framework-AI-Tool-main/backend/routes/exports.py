from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from typing import Dict
from datetime import datetime, timezone
import io
import csv
import json

from database import db
from utils import get_current_user

router = APIRouter()


@router.get("/export/policies")
async def export_policies(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    policies = await db.policies.find({"organization_id": org_id}, {"_id": 0}).to_list(10000)

    output = io.StringIO()
    if policies:
        writer = csv.DictWriter(output, fieldnames=policies[0].keys())
        writer.writeheader()
        writer.writerows(policies)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=policies_export.csv"}
    )


@router.get("/export/risks")
async def export_risks(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    risks = await db.risks.find({"organization_id": org_id}, {"_id": 0}).to_list(10000)

    output = io.StringIO()
    if risks:
        writer = csv.DictWriter(output, fieldnames=risks[0].keys())
        writer.writeheader()
        writer.writerows(risks)

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=risks_export.csv"}
    )


@router.get("/export/compliance-report")
async def export_compliance_report(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    policies_count = await db.policies.count_documents({"organization_id": org_id})
    mappings_count = await db.mappings.count_documents({"organization_id": org_id})
    risks_count = await db.risks.count_documents({"organization_id": org_id})
    frameworks = await db.frameworks.find({}, {"_id": 0, "name": 1}).to_list(100)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "organization_id": org_id,
        "summary": {
            "total_policies": policies_count,
            "total_control_mappings": mappings_count,
            "total_risks": risks_count,
            "frameworks_count": len(frameworks)
        },
        "frameworks": [f["name"] for f in frameworks]
    }

    return StreamingResponse(
        iter([json.dumps(report, indent=2)]),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=compliance_report.json"}
    )
