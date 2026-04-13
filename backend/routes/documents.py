"""
S3 Document Upload and Lambda Pipeline Routes.
Handles file upload to S3, invokes preprocessing and analysis Lambdas.
"""
import os
import uuid
import json
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from typing import Dict, Optional

import boto3
from botocore.exceptions import ClientError

from database import db
from utils import get_current_user, guard_demo, log_activity
from routes.notifications import create_notification

router = APIRouter()

AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
PREPROCESS_LAMBDA = os.environ.get("PREPROCESS_LAMBDA_FUNCTION_NAME", "")
ANALYSIS_LAMBDA = os.environ.get("ANALYSIS_LAMBDA_FUNCTION_NAME", "")


def get_s3_client():
    return boto3.client(
        "s3",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


def get_lambda_client():
    return boto3.client(
        "lambda",
        region_name=AWS_REGION,
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    )


@router.post("/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    framework: str = Form(""),
    control_family: str = Form(""),
    category: str = Form("other"),
    custom_tags: str = Form(""),
    current_user: Dict = Depends(get_current_user),
):
    """Upload a document to S3 and trigger preprocessing Lambda."""
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    user_id = current_user["id"]

    if not BUCKET_NAME:
        raise HTTPException(status_code=503, detail="S3 bucket not configured")

    allowed_types = [
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "text/plain",
        "text/csv",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "image/png",
        "image/jpeg",
    ]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Unsupported file type. Allowed: PDF, DOCX, DOC, TXT, CSV, XLSX, PNG, JPG")

    job_id = str(uuid.uuid4())
    file_ext = file.filename.rsplit(".", 1)[-1] if "." in file.filename else "pdf"
    s3_key = f"uploads/{user_id}/{job_id}.{file_ext}"

    # Read file content
    content = await file.read()

    # Upload to S3
    try:
        s3 = get_s3_client()
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=s3_key,
            Body=content,
            ContentType=file.content_type,
            Metadata={"job_id": job_id, "user_id": user_id},
        )
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"S3 upload failed: {str(e)}")

    # Create file record in local DB
    now = datetime.now(timezone.utc).isoformat()
    parsed_tags = [t.strip() for t in custom_tags.split(",") if t.strip()] if custom_tags else []
    doc_record = {
        "id": job_id,
        "organization_id": org_id,
        "user_id": user_id,
        "original_name": file.filename,
        "s3_key": s3_key,
        "file_type": file_ext,
        "framework": framework,
        "control_family": control_family,
        "category": category,
        "custom_tags": parsed_tags,
        "status": "uploaded",
        "progress": 0,
        "created_at": now,
        "updated_at": now,
    }
    await db.document_uploads.insert_one(doc_record)

    # Try to invoke preprocessing Lambda
    lambda_invoked = False
    if PREPROCESS_LAMBDA:
        try:
            lc = get_lambda_client()
            payload = {
                "Records": [{
                    "s3": {
                        "bucket": {"name": BUCKET_NAME},
                        "object": {"key": s3_key},
                    }
                }]
            }
            lc.invoke(
                FunctionName=PREPROCESS_LAMBDA,
                InvocationType="Event",
                Payload=json.dumps(payload).encode(),
            )
            await db.document_uploads.update_one(
                {"id": job_id},
                {"$set": {"status": "preprocessing", "updated_at": datetime.now(timezone.utc).isoformat()}}
            )
            lambda_invoked = True
        except Exception as e:
            print(f"Lambda invoke error: {e}")

    if not lambda_invoked:
        await db.document_uploads.update_one(
            {"id": job_id},
            {"$set": {"status": "uploaded_pending_processing", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )

    await log_activity(org_id, user_id, current_user.get("name", ""), "document_uploaded", f"Uploaded document: {file.filename}")

    doc_record.pop("_id", None)
    return {
        "message": "Document uploaded successfully",
        "job_id": job_id,
        "s3_key": s3_key,
        "status": "preprocessing" if lambda_invoked else "uploaded_pending_processing",
        "lambda_invoked": lambda_invoked,
    }


@router.post("/documents/{job_id}/analyze")
async def trigger_analysis(
    job_id: str,
    current_user: Dict = Depends(get_current_user),
):
    """Trigger compliance analysis Lambda on an uploaded document."""
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    user_id = current_user["id"]

    doc = await db.document_uploads.find_one({"id": job_id, "organization_id": org_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if not ANALYSIS_LAMBDA:
        raise HTTPException(status_code=503, detail="Analysis Lambda not configured")

    try:
        lc = get_lambda_client()
        payload = {
            "framework": doc.get("framework", "nist-800-53"),
            "controlFamily": doc.get("control_family", ""),
            "fileId": job_id,
            "jobId": job_id,
            "userId": user_id,
            "topK": 6,
        }
        lc.invoke(
            FunctionName=ANALYSIS_LAMBDA,
            InvocationType="Event",
            Payload=json.dumps(payload).encode(),
        )
        await db.document_uploads.update_one(
            {"id": job_id},
            {"$set": {"status": "analyzing", "updated_at": datetime.now(timezone.utc).isoformat()}}
        )
        await log_activity(org_id, user_id, current_user.get("name", ""), "analysis_started", f"Started analysis: {doc.get('original_name', job_id)}")
        return {"message": "Analysis started", "status": "analyzing", "job_id": job_id}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Lambda invocation failed: {str(e)}")


@router.get("/documents")
async def list_documents(current_user: Dict = Depends(get_current_user)):
    """List all uploaded documents for the user's organization."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    docs = await db.document_uploads.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    # Ensure filename field exists for frontend compatibility
    for d in docs:
        if "filename" not in d and "original_name" in d:
            d["filename"] = d["original_name"]
        if "job_id" not in d and "id" in d:
            d["job_id"] = d["id"]
    return docs


@router.get("/documents/custom-tags")
async def get_custom_tags(current_user: Dict = Depends(get_current_user)):
    """Get all unique custom tags used in the organization for auto-suggest."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    pipeline = [
        {"$match": {"organization_id": org_id, "custom_tags": {"$exists": True, "$ne": []}}},
        {"$unwind": "$custom_tags"},
        {"$group": {"_id": "$custom_tags"}},
        {"$sort": {"_id": 1}},
    ]
    tags = []
    async for doc in db.document_uploads.aggregate(pipeline):
        tags.append(doc["_id"])
    return tags


@router.get("/documents/{job_id}")
async def get_document(job_id: str, current_user: Dict = Depends(get_current_user)):
    """Get a single document record."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    doc = await db.document_uploads.find_one({"id": job_id, "organization_id": org_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return doc


@router.get("/documents/{job_id}/download-url")
async def get_download_url(job_id: str, current_user: Dict = Depends(get_current_user)):
    """Generate a presigned S3 download URL."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    doc = await db.document_uploads.find_one({"id": job_id, "organization_id": org_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    try:
        s3 = get_s3_client()
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": BUCKET_NAME, "Key": doc["s3_key"]},
            ExpiresIn=3600,
        )
        return {"url": url, "expires_in": 3600}
    except ClientError as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate URL: {str(e)}")


@router.put("/documents/{job_id}/metadata")
async def update_document_metadata(job_id: str, data: dict, current_user: Dict = Depends(get_current_user)):
    """Update document metadata: category, custom_tags, framework."""
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    doc = await db.document_uploads.find_one({"id": job_id, "organization_id": org_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    now = datetime.now(timezone.utc).isoformat()
    update = {"updated_at": now}
    if "category" in data:
        update["category"] = data["category"]
    if "custom_tags" in data:
        update["custom_tags"] = data["custom_tags"] if isinstance(data["custom_tags"], list) else []
    if "framework" in data:
        update["framework"] = data["framework"]
    if "description" in data:
        update["description"] = data["description"]

    await db.document_uploads.update_one({"id": job_id}, {"$set": update})
    updated = await db.document_uploads.find_one({"id": job_id}, {"_id": 0})
    return updated


@router.post("/documents/create")
async def create_document(data: dict, current_user: Dict = Depends(get_current_user)):
    """Create a document from scratch using the built-in text editor."""
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    user_id = current_user["id"]

    title = data.get("title", "Untitled Document")
    content = data.get("content", "")
    category = data.get("category", "policy")
    custom_tags = data.get("custom_tags", [])
    framework = data.get("framework", "")

    now = datetime.now(timezone.utc).isoformat()
    doc_id = str(uuid.uuid4())
    doc_record = {
        "id": doc_id,
        "organization_id": org_id,
        "user_id": user_id,
        "original_name": title,
        "filename": title,
        "file_type": "created",
        "s3_key": "",
        "framework": framework,
        "control_family": "",
        "category": category,
        "custom_tags": custom_tags if isinstance(custom_tags, list) else [],
        "content": content,
        "status": "draft",
        "progress": 100,
        "created_at": now,
        "updated_at": now,
    }
    await db.document_uploads.insert_one(doc_record)
    doc_record.pop("_id", None)
    doc_record["job_id"] = doc_id
    return doc_record


@router.put("/documents/{job_id}/content")
async def update_document_content(job_id: str, data: dict, current_user: Dict = Depends(get_current_user)):
    """Update the text content of a created document."""
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    doc = await db.document_uploads.find_one({"id": job_id, "organization_id": org_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    now = datetime.now(timezone.utc).isoformat()
    update = {"updated_at": now}
    if "content" in data:
        update["content"] = data["content"]
    if "title" in data:
        update["original_name"] = data["title"]
        update["filename"] = data["title"]
    await db.document_uploads.update_one({"id": job_id}, {"$set": update})
    updated = await db.document_uploads.find_one({"id": job_id}, {"_id": 0})
    if updated:
        updated["job_id"] = updated.get("id", job_id)
    return updated


@router.put("/documents/{job_id}/status")
async def update_document_status(job_id: str, data: dict, current_user: Dict = Depends(get_current_user)):
    """Update document approval status: draft -> under_review -> approved."""
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    doc = await db.document_uploads.find_one({"id": job_id, "organization_id": org_id})
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    new_status = data.get("status", "")
    valid_statuses = ["draft", "under_review", "approved"]
    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

    current_status = doc.get("status", "draft")
    # Normalize legacy statuses
    if current_status in ("uploaded", "uploaded_pending_processing", "preprocessing", "analysis_completed", "completed"):
        current_status = "draft"

    valid_transitions = {
        "draft": ["under_review"],
        "under_review": ["approved", "draft"],
        "approved": ["draft"],
    }
    if new_status != current_status and new_status not in valid_transitions.get(current_status, []):
        raise HTTPException(status_code=400, detail=f"Cannot transition from '{current_status}' to '{new_status}'")

    now = datetime.now(timezone.utc).isoformat()
    update_fields = {"status": new_status, "updated_at": now}
    if new_status == "approved":
        update_fields["approved_by"] = current_user["id"]
        update_fields["approved_by_name"] = current_user.get("name", current_user.get("email", "Unknown"))
        update_fields["approved_at"] = now

    await db.document_uploads.update_one({"id": job_id}, {"$set": update_fields})
    return {"message": f"Status updated to {new_status}", "status": new_status}
