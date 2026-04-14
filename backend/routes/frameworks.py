from fastapi import APIRouter, Depends
from typing import Dict

from database import db
from models import Framework, FrameworkCreate, Control
from utils import get_current_user, guard_demo

router = APIRouter()


@router.get("/frameworks")
async def get_frameworks(current_user: Dict = Depends(get_current_user)):
    frameworks = await db.frameworks.find({"type": "standard"}, {"_id": 0}).to_list(100)
    return frameworks


@router.post("/frameworks")
async def create_framework(data: FrameworkCreate, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    framework = Framework(
        name=data.name,
        description=data.description,
        version=data.version,
        organization_id=org_id,
        type="custom"
    )

    doc = framework.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.frameworks.insert_one(doc)
    return framework


@router.get("/controls/{framework_id}")
async def get_controls(framework_id: str, current_user: Dict = Depends(get_current_user)):
    controls = await db.controls.find({"framework_id": framework_id}, {"_id": 0}).to_list(1000)
    return controls


@router.post("/controls")
async def create_control(control: Control, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    doc = control.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.controls.insert_one(doc)
    return control


@router.post("/init/seed-frameworks")
async def seed_frameworks():
    from framework_controls_data import get_framework_controls

    frameworks_data = [
        {"name": "NIST Cybersecurity Framework", "type": "standard", "description": "Framework for improving critical infrastructure cybersecurity", "version": "1.1"},
        {"name": "NIST SP 800-53", "type": "standard", "description": "Security and Privacy Controls for Information Systems", "version": "Rev 5"},
        {"name": "NIST SP 800-171", "type": "standard", "description": "Protecting Controlled Unclassified Information", "version": "Rev 2"},
        {"name": "ISO 27001", "type": "standard", "description": "Information Security Management Systems", "version": "2022"},
        {"name": "GDPR", "type": "standard", "description": "General Data Protection Regulation", "version": "2018"},
        {"name": "HIPAA", "type": "standard", "description": "Health Insurance Portability and Accountability Act", "version": "2013"},
        {"name": "SOC 2", "type": "standard", "description": "Service Organization Control 2", "version": "2017"},
        {"name": "CMMC", "type": "standard", "description": "Cybersecurity Maturity Model Certification", "version": "2.0"},
        {"name": "NIS2", "type": "standard", "description": "Network and Information Security Directive", "version": "2023"},
        {"name": "NIST AI Risk Management Framework", "type": "standard", "description": "AI Risk Management Framework for AI systems", "version": "1.0"},
        {"name": "Financial Services AI Risk Management Framework", "type": "standard", "description": "AI RMF tailored for financial services", "version": "1.0"},
        {"name": "StateRAMP", "type": "standard", "description": "State Risk and Authorization Management Program for cloud security", "version": "4.0"},
        {"name": "NERC CIP", "type": "standard", "description": "Critical Infrastructure Protection standards for Bulk Electric System cybersecurity", "version": "v7"},
        {"name": "NERC Reliability Standards (Order 693)", "type": "standard", "description": "Mandatory reliability standards for Bulk Power System operations, balancing, and planning", "version": "2024"},
    ]

    frameworks_created = 0
    controls_created = 0

    for fw_data in frameworks_data:
        existing = await db.frameworks.find_one({"name": fw_data["name"]})
        if not existing:
            framework = Framework(**fw_data)
            doc = framework.model_dump()
            doc["created_at"] = doc["created_at"].isoformat()
            await db.frameworks.insert_one(doc)
            frameworks_created += 1
            fw_id = framework.id
        else:
            fw_id = existing["id"]

        # Always sync controls from source data
        controls = get_framework_controls(fw_data["name"])
        if controls:
            existing_ctrl_ids = set()
            existing_ctrls = await db.controls.find({"framework_id": fw_id}, {"_id": 0, "control_id": 1}).to_list(10000)
            existing_ctrl_ids = {c["control_id"] for c in existing_ctrls}

            for ctrl_data in controls:
                if ctrl_data["control_id"] not in existing_ctrl_ids:
                    control = Control(
                        framework_id=fw_id,
                        control_id=ctrl_data["control_id"],
                        title=ctrl_data["title"],
                        category=ctrl_data["category"],
                        description=ctrl_data["description"]
                    )
                    ctrl_doc = control.model_dump()
                    ctrl_doc["created_at"] = ctrl_doc["created_at"].isoformat()
                    await db.controls.insert_one(ctrl_doc)
                    controls_created += 1

    return {
        "message": "Frameworks and controls seeded successfully",
        "frameworks_created": frameworks_created,
        "controls_created": controls_created,
        "total_frameworks": len(frameworks_data)
    }
