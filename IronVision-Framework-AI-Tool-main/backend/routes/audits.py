from fastapi import APIRouter, Depends
from typing import Dict, Any, List
from datetime import datetime

from database import db
from models import Audit, AuditCreate, AuditEvidence
from utils import get_current_user, guard_demo

router = APIRouter()


@router.get("/audits")
async def get_audits(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    audits = await db.audits.find({"organization_id": org_id}, {"_id": 0}).to_list(1000)
    return audits


@router.post("/audits")
async def create_audit(data: AuditCreate, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    audit = Audit(
        organization_id=org_id,
        title=data.title,
        framework_ids=data.framework_ids,
        audit_type=data.audit_type,
        status=data.status,
        scheduled_date=datetime.fromisoformat(data.scheduled_date.replace('Z', '+00:00')),
        auditor=data.auditor
    )

    doc = audit.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    doc["scheduled_date"] = doc["scheduled_date"].isoformat()
    if doc.get("completion_date"):
        doc["completion_date"] = doc["completion_date"].isoformat()

    await db.audits.insert_one(doc)
    return audit


@router.post("/audits/{audit_id}/evidence")
async def upload_audit_evidence(audit_id: str, data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    evidence = AuditEvidence(
        audit_id=audit_id,
        control_id=data.get("control_id", ""),
        evidence_type=data.get("evidence_type", "document"),
        file_url=data.get("file_url"),
        description=data.get("description", ""),
        uploaded_by=current_user["id"]
    )

    doc = evidence.model_dump()
    doc["uploaded_at"] = doc["uploaded_at"].isoformat()
    await db.audit_evidence.insert_one(doc)
    return evidence


@router.get("/audits/{audit_id}/evidence")
async def get_audit_evidence(audit_id: str, current_user: Dict = Depends(get_current_user)):
    evidence = await db.audit_evidence.find({"audit_id": audit_id}, {"_id": 0}).to_list(1000)
    return evidence
