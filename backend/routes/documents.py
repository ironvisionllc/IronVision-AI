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
    framework: str = Form("nist-800-53"),
    control_family: str = Form(""),
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
    ]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only PDF and DOCX files are supported")

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
    doc_record = {
        "id": job_id,
        "organization_id": org_id,
        "user_id": user_id,
        "original_name": file.filename,
        "s3_key": s3_key,
        "file_type": file_ext,
        "framework": framework,
        "control_family": control_family,
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
    return docs


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
