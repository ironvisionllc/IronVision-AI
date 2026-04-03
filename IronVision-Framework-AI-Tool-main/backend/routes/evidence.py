from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.responses import FileResponse
from typing import Dict, Optional
from datetime import datetime, timezone
from pathlib import Path
import uuid

from database import db
from utils import get_current_user, guard_demo, log_activity

router = APIRouter()

ROOT_DIR = Path(__file__).parent.parent
UPLOAD_DIR = ROOT_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.get("/evidence")
async def get_evidence(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    items = await db.evidence_library.find({"organization_id": org_id}, {"_id": 0}).sort("created_at", -1).to_list(1000)
    return items


@router.post("/evidence")
async def create_evidence(
    description: str = Form(...),
    evidence_type: str = Form("document"),
    control_id: str = Form(""),
    framework_name: str = Form(""),
    tags: str = Form(""),
    file: Optional[UploadFile] = File(None),
    current_user: Dict = Depends(get_current_user)
):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    file_info = None
    if file and file.filename:
        content = await file.read()
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large. Maximum size is 50MB.")

        ext = Path(file.filename).suffix
        safe_name = f"{uuid.uuid4().hex}{ext}"
        file_path = UPLOAD_DIR / safe_name

        with open(file_path, "wb") as f:
            f.write(content)

        file_info = {
            "original_name": file.filename,
            "stored_name": safe_name,
            "size": len(content),
            "content_type": file.content_type or "application/octet-stream"
        }

    parsed_tags = [t.strip() for t in tags.split(",") if t.strip()] if tags else []

    doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "description": description,
        "evidence_type": evidence_type,
        "control_id": control_id,
        "framework_name": framework_name,
        "tags": parsed_tags,
        "file": file_info,
        "uploaded_by": current_user["id"],
        "uploaded_by_name": current_user.get("name", ""),
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    await db.evidence_library.insert_one(doc)
    await log_activity(org_id, current_user["id"], current_user.get("name", ""), "evidence_added", f"Added evidence: {description[:50]}")
    doc.pop("_id", None)
    return doc


@router.get("/evidence/{evidence_id}/download")
async def download_evidence_file(evidence_id: str, current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    item = await db.evidence_library.find_one({"id": evidence_id, "organization_id": org_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Evidence not found")
    if not item.get("file"):
        raise HTTPException(status_code=404, detail="No file attached to this evidence")

    file_path = UPLOAD_DIR / item["file"]["stored_name"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    return FileResponse(
        path=str(file_path),
        filename=item["file"]["original_name"],
        media_type=item["file"].get("content_type", "application/octet-stream")
    )


@router.delete("/evidence/{evidence_id}")
async def delete_evidence(evidence_id: str, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    item = await db.evidence_library.find_one({"id": evidence_id, "organization_id": org_id}, {"_id": 0})
    if not item:
        raise HTTPException(status_code=404, detail="Evidence not found")

    if item.get("file"):
        file_path = UPLOAD_DIR / item["file"]["stored_name"]
        if file_path.exists():
            file_path.unlink()

    await db.evidence_library.delete_one({"id": evidence_id, "organization_id": org_id})
    return {"message": "Evidence deleted successfully"}
