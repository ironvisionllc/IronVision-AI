"""
Email Notification Routes via AWS SES.
Sends email alerts for key events (risk alerts, task assignments, audit reminders).
"""
import os
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict
from pydantic import BaseModel

import boto3
from botocore.exceptions import ClientError

from utils import get_current_user, guard_demo

router = APIRouter()

SES_REGION = os.environ.get("AWS_SES_REGION", "us-east-1")
SES_ACCESS_KEY = os.environ.get("AWS_SES_ACCESS_KEY_ID", "")
SES_SECRET_KEY = os.environ.get("AWS_SES_SECRET_ACCESS_KEY", "")
SES_FROM_EMAIL = os.environ.get("AWS_SES_FROM_EMAIL", "noreply@ironvision.ai")


def get_ses_client():
    if not SES_ACCESS_KEY or not SES_SECRET_KEY:
        return None
    return boto3.client(
        "ses",
        region_name=SES_REGION,
        aws_access_key_id=SES_ACCESS_KEY,
        aws_secret_access_key=SES_SECRET_KEY,
    )


async def send_email(to_email: str, subject: str, body_html: str, body_text: str = ""):
    """Send an email via AWS SES. Returns True on success."""
    ses = get_ses_client()
    if not ses:
        print("[EMAIL] SES not configured, skipping email")
        return False

    try:
        ses.send_email(
            Source=SES_FROM_EMAIL,
            Destination={"ToAddresses": [to_email]},
            Message={
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Html": {"Data": body_html, "Charset": "UTF-8"},
                    "Text": {"Data": body_text or subject, "Charset": "UTF-8"},
                },
            },
        )
        return True
    except ClientError as e:
        print(f"[EMAIL] SES send failed: {e}")
        return False


def build_alert_email(title: str, message: str, link_url: str = "", link_text: str = "View in IronVision") -> str:
    """Build a branded HTML email template."""
    link_html = f'<a href="{link_url}" style="display:inline-block;padding:10px 24px;background:#2597B2;color:#fff;border-radius:8px;text-decoration:none;font-weight:600;margin-top:16px">{link_text}</a>' if link_url else ""
    return f"""
    <div style="font-family:Inter,Arial,sans-serif;max-width:560px;margin:0 auto;padding:32px">
      <div style="text-align:center;margin-bottom:24px">
        <h2 style="color:#2597B2;font-size:20px;margin:0">IronVision AI</h2>
        <p style="color:#8EA7AE;font-size:12px;margin:4px 0 0">Governance, Risk & Compliance</p>
      </div>
      <div style="background:#fff;border:1px solid #e5e7eb;border-radius:16px;padding:24px">
        <h3 style="color:#454548;margin:0 0 12px">{title}</h3>
        <p style="color:#6b7280;font-size:14px;line-height:1.6;margin:0">{message}</p>
        {link_html}
      </div>
      <p style="color:#9ca3af;font-size:11px;text-align:center;margin-top:24px">
        This is an automated notification from IronVision AI.
      </p>
    </div>
    """


class EmailTestRequest(BaseModel):
    to_email: str
    subject: str = "IronVision AI - Test Notification"
    message: str = "This is a test email from IronVision AI GRC Platform."


@router.post("/email/test")
async def test_email(data: EmailTestRequest, current_user: Dict = Depends(get_current_user)):
    """Send a test email to verify SES configuration."""
    guard_demo(current_user)
    html = build_alert_email("Test Notification", data.message)
    success = await send_email(data.to_email, data.subject, html)
    if not success:
        raise HTTPException(status_code=503, detail="Email sending failed. Check SES configuration.")
    return {"message": f"Test email sent to {data.to_email}"}


@router.get("/email/status")
async def email_status(current_user: Dict = Depends(get_current_user)):
    """Check if email (SES) is configured."""
    ses = get_ses_client()
    configured = ses is not None
    verified = False
    if configured:
        try:
            resp = ses.get_send_quota()
            verified = resp.get("Max24HourSend", 0) > 0
        except Exception:
            pass
    return {
        "configured": configured,
        "verified": verified,
        "from_email": SES_FROM_EMAIL if configured else None,
    }
