from fastapi import APIRouter, HTTPException, Depends
from typing import Dict

from database import db
from models import Vendor, VendorCreate
from utils import get_current_user, guard_demo, log_activity

router = APIRouter()


@router.get("/vendors")
async def get_vendors(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    vendors = await db.vendors.find({"organization_id": org_id}, {"_id": 0}).to_list(1000)
    return vendors


@router.post("/vendors")
async def create_vendor(data: VendorCreate, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    vendor = Vendor(
        organization_id=org_id,
        name=data.name,
        contact_email=data.contact_email,
        risk_level=data.risk_level,
        assessment_status=data.assessment_status
    )

    doc = vendor.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    if doc.get("last_assessment_date"):
        doc["last_assessment_date"] = doc["last_assessment_date"].isoformat()
    if doc.get("next_assessment_date"):
        doc["next_assessment_date"] = doc["next_assessment_date"].isoformat()

    await db.vendors.insert_one(doc)
    await log_activity(org_id, current_user["id"], current_user.get("name", ""), "vendor_created", f"Added vendor: {data.name}")
    return vendor


@router.put("/vendors/{vendor_id}")
async def update_vendor(vendor_id: str, data: VendorCreate, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    existing = await db.vendors.find_one({"id": vendor_id, "organization_id": org_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Vendor not found")

    update = {
        "name": data.name,
        "contact_email": data.contact_email,
        "risk_level": data.risk_level,
        "assessment_status": data.assessment_status,
    }
    await db.vendors.update_one({"id": vendor_id}, {"$set": update})
    await log_activity(org_id, current_user["id"], current_user.get("name", ""), "vendor_updated", f"Updated vendor: {data.name}")
    updated = await db.vendors.find_one({"id": vendor_id}, {"_id": 0})
    return updated


@router.delete("/vendors/{vendor_id}")
async def delete_vendor(vendor_id: str, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    existing = await db.vendors.find_one({"id": vendor_id, "organization_id": org_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Vendor not found")
    await db.vendors.delete_one({"id": vendor_id})
    await log_activity(org_id, current_user["id"], current_user.get("name", ""), "vendor_deleted", f"Deleted vendor: {existing.get('name', '')}")
    return {"message": "Vendor deleted"}
