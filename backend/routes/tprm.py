"""
Third-Party Risk Management (TPRM)
- Vendor risk intake form and assessment
- Map vendor risk scores against internal frameworks
- Track vendor compliance status
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Optional, List
from datetime import datetime, timezone
import uuid
import logging

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tprm", tags=["tprm"])


class VendorCreate(BaseModel):
    name: str
    contact_email: Optional[str] = ""
    website: Optional[str] = ""
    category: str = "technology"  # technology, cloud, consulting, data_processing, other
    data_access_level: str = "low"  # none, low, medium, high, critical
    description: Optional[str] = ""

class VendorAssessment(BaseModel):
    vendor_id: str
    responses: List[Dict]  # [{question_id, answer, score}]

class VendorStatusUpdate(BaseModel):
    status: str  # pending, approved, conditional, rejected, review_needed


RISK_QUESTIONNAIRE = [
    {"id": "Q1", "question": "Does the vendor have a SOC 2 Type II report?", "category": "Certification", "weight": 10, "control_ids": ["SA-9", "SA-12"]},
    {"id": "Q2", "question": "Does the vendor encrypt data at rest and in transit?", "category": "Data Protection", "weight": 10, "control_ids": ["SC-28", "SC-8"]},
    {"id": "Q3", "question": "Does the vendor enforce multi-factor authentication?", "category": "Access Control", "weight": 8, "control_ids": ["IA-2", "IA-5"]},
    {"id": "Q4", "question": "Does the vendor have an incident response plan?", "category": "Incident Response", "weight": 8, "control_ids": ["IR-4", "IR-6", "IR-8"]},
    {"id": "Q5", "question": "Does the vendor conduct regular vulnerability assessments?", "category": "Security Assessment", "weight": 8, "control_ids": ["RA-5", "CA-8"]},
    {"id": "Q6", "question": "Does the vendor have data backup and recovery procedures?", "category": "Availability", "weight": 7, "control_ids": ["CP-9", "CP-10"]},
    {"id": "Q7", "question": "Does the vendor provide security awareness training to employees?", "category": "Personnel", "weight": 5, "control_ids": ["AT-2", "AT-3"]},
    {"id": "Q8", "question": "Does the vendor have a formal change management process?", "category": "Change Management", "weight": 6, "control_ids": ["CM-3", "CM-4"]},
    {"id": "Q9", "question": "Does the vendor comply with applicable data privacy regulations (GDPR, CCPA)?", "category": "Privacy", "weight": 8, "control_ids": ["AR-1", "UL-1"]},
    {"id": "Q10", "question": "Does the vendor have a business continuity plan?", "category": "Continuity", "weight": 7, "control_ids": ["CP-2", "CP-4"]},
    {"id": "Q11", "question": "Does the vendor conduct background checks on employees with data access?", "category": "Personnel", "weight": 6, "control_ids": ["PS-3", "PS-7"]},
    {"id": "Q12", "question": "Does the vendor maintain audit logs for a minimum of 12 months?", "category": "Logging", "weight": 7, "control_ids": ["AU-11", "AU-4"]},
    {"id": "Q13", "question": "Does the vendor have a physical security program?", "category": "Physical", "weight": 5, "control_ids": ["PE-2", "PE-3"]},
    {"id": "Q14", "question": "Does the vendor support secure API integrations?", "category": "Integration", "weight": 6, "control_ids": ["SC-8", "SA-9"]},
    {"id": "Q15", "question": "Does the vendor have a sub-processor management policy?", "category": "Supply Chain", "weight": 7, "control_ids": ["SA-12", "SR-6"]},
]

ANSWER_SCORES = {
    "yes": 1.0,
    "partial": 0.5,
    "no": 0.0,
    "n/a": None,
}

DATA_ACCESS_RISK_MULTIPLIER = {
    "none": 0.5,
    "low": 0.8,
    "medium": 1.0,
    "high": 1.3,
    "critical": 1.6,
}


@router.get("/questionnaire")
async def get_questionnaire(current_user: Dict = Depends(get_current_user)):
    """Get the vendor risk assessment questionnaire."""
    return {"questions": RISK_QUESTIONNAIRE, "answer_options": list(ANSWER_SCORES.keys())}


@router.post("/vendors")
async def create_vendor(data: VendorCreate, current_user: Dict = Depends(get_current_user)):
    """Add a new vendor to the TPRM registry."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()

    vendor = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "name": data.name,
        "contact_email": data.contact_email,
        "website": data.website,
        "category": data.category,
        "data_access_level": data.data_access_level,
        "description": data.description,
        "risk_score": None,
        "risk_level": "not_assessed",
        "status": "pending",
        "last_assessed": None,
        "created_at": now,
        "created_by": current_user["id"],
    }
    await db.vendors.insert_one(vendor)
    del vendor["_id"]
    return vendor


@router.get("/vendors")
async def list_vendors(current_user: Dict = Depends(get_current_user)):
    """List all vendors."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    vendors = await db.vendors.find({"organization_id": org_id}, {"_id": 0}).sort("created_at", -1).to_list(200)
    return vendors


@router.get("/vendors/{vendor_id}")
async def get_vendor(vendor_id: str, current_user: Dict = Depends(get_current_user)):
    """Get vendor details with assessment history."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    vendor = await db.vendors.find_one({"id": vendor_id, "organization_id": org_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(404, "Vendor not found")

    assessments = await db.vendor_assessments.find(
        {"vendor_id": vendor_id, "organization_id": org_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(20)

    return {"vendor": vendor, "assessments": assessments}


@router.delete("/vendors/{vendor_id}")
async def delete_vendor(vendor_id: str, current_user: Dict = Depends(get_current_user)):
    """Delete a vendor."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    result = await db.vendors.delete_one({"id": vendor_id, "organization_id": org_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Vendor not found")
    await db.vendor_assessments.delete_many({"vendor_id": vendor_id, "organization_id": org_id})
    return {"message": "Vendor deleted"}


@router.put("/vendors/{vendor_id}/status")
async def update_vendor_status(vendor_id: str, data: VendorStatusUpdate, current_user: Dict = Depends(get_current_user)):
    """Update vendor approval status."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    result = await db.vendors.update_one(
        {"id": vendor_id, "organization_id": org_id},
        {"$set": {"status": data.status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    if result.modified_count == 0:
        raise HTTPException(404, "Vendor not found")
    return {"message": f"Vendor status updated to {data.status}"}


@router.post("/assess")
async def submit_vendor_assessment(data: VendorAssessment, current_user: Dict = Depends(get_current_user)):
    """Submit a vendor risk assessment."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()

    vendor = await db.vendors.find_one({"id": data.vendor_id, "organization_id": org_id}, {"_id": 0})
    if not vendor:
        raise HTTPException(404, "Vendor not found")

    # Calculate risk score
    q_map = {q["id"]: q for q in RISK_QUESTIONNAIRE}
    total_weight = 0
    weighted_score = 0
    control_impacts = {}

    for resp in data.responses:
        q_id = resp.get("question_id", "")
        answer = resp.get("answer", "no").lower()
        q = q_map.get(q_id)
        if not q:
            continue

        score = ANSWER_SCORES.get(answer)
        if score is None:
            continue  # N/A

        total_weight += q["weight"]
        weighted_score += score * q["weight"]

        for cid in q.get("control_ids", []):
            if cid not in control_impacts:
                control_impacts[cid] = {"passed": 0, "failed": 0}
            if score >= 0.5:
                control_impacts[cid]["passed"] += 1
            else:
                control_impacts[cid]["failed"] += 1

    raw_score = (weighted_score / max(total_weight, 1)) * 100

    # Apply data access risk multiplier
    multiplier = DATA_ACCESS_RISK_MULTIPLIER.get(vendor.get("data_access_level", "low"), 1.0)
    # Invert: higher score = lower risk. Apply multiplier to risk (100 - score)
    risk_component = (100 - raw_score) * multiplier
    final_risk = min(100, max(0, risk_component))
    compliance_score = 100 - final_risk

    # Determine risk level
    if final_risk >= 70:
        risk_level = "critical"
    elif final_risk >= 50:
        risk_level = "high"
    elif final_risk >= 30:
        risk_level = "medium"
    else:
        risk_level = "low"

    # Store assessment
    assessment = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "vendor_id": data.vendor_id,
        "responses": data.responses,
        "raw_score": round(raw_score, 1),
        "risk_score": round(final_risk, 1),
        "compliance_score": round(compliance_score, 1),
        "risk_level": risk_level,
        "control_impacts": control_impacts,
        "data_access_multiplier": multiplier,
        "created_at": now,
        "assessed_by": current_user["id"],
    }
    await db.vendor_assessments.insert_one(assessment)
    del assessment["_id"]

    # Update vendor
    await db.vendors.update_one(
        {"id": data.vendor_id, "organization_id": org_id},
        {"$set": {
            "risk_score": round(final_risk, 1),
            "risk_level": risk_level,
            "last_assessed": now,
        }}
    )

    return {
        "assessment": assessment,
        "message": f"Vendor assessed: {risk_level} risk ({final_risk:.0f}/100)",
    }


@router.get("/dashboard")
async def get_tprm_dashboard(current_user: Dict = Depends(get_current_user)):
    """Get TPRM dashboard summary."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    vendors = await db.vendors.find({"organization_id": org_id}, {"_id": 0}).to_list(200)

    total = len(vendors)
    by_risk = {"critical": 0, "high": 0, "medium": 0, "low": 0, "not_assessed": 0}
    by_status = {"pending": 0, "approved": 0, "conditional": 0, "rejected": 0, "review_needed": 0}
    by_category = {}

    for v in vendors:
        rl = v.get("risk_level", "not_assessed")
        by_risk[rl] = by_risk.get(rl, 0) + 1
        st = v.get("status", "pending")
        by_status[st] = by_status.get(st, 0) + 1
        cat = v.get("category", "other")
        by_category[cat] = by_category.get(cat, 0) + 1

    avg_risk = sum(v.get("risk_score", 0) for v in vendors if v.get("risk_score") is not None) / max(sum(1 for v in vendors if v.get("risk_score") is not None), 1)

    return {
        "total_vendors": total,
        "by_risk_level": by_risk,
        "by_status": by_status,
        "by_category": by_category,
        "average_risk": round(avg_risk, 1),
    }
