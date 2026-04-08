"""
Slack Integration - Webhook-based notifications for GRC events.
Users configure a Slack Incoming Webhook URL, and the app sends notifications
for key events (risks, tasks, policies, audits).
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Optional, List
from datetime import datetime, timezone
import uuid
import logging
import httpx

from database import db
from utils import get_current_user, guard_demo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/slack", tags=["slack"])


class SlackConfigRequest(BaseModel):
    webhook_url: str
    channel_name: Optional[str] = "#general"
    notify_risks: bool = True
    notify_tasks: bool = True
    notify_policies: bool = True
    notify_audits: bool = True


class SlackTestRequest(BaseModel):
    webhook_url: str


class SlackNotification(BaseModel):
    event_type: str
    title: str
    message: str
    severity: Optional[str] = "info"
    link: Optional[str] = None


@router.get("/config")
async def get_slack_config(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    config = await db.slack_config.find_one(
        {"organization_id": org_id},
        {"_id": 0}
    )
    if not config:
        return {"configured": False}
    # Mask webhook URL for security
    wh = config.get("webhook_url", "")
    masked = wh[:30] + "..." + wh[-8:] if len(wh) > 40 else wh
    return {
        "configured": True,
        "channel_name": config.get("channel_name", "#general"),
        "webhook_url_masked": masked,
        "notify_risks": config.get("notify_risks", True),
        "notify_tasks": config.get("notify_tasks", True),
        "notify_policies": config.get("notify_policies", True),
        "notify_audits": config.get("notify_audits", True),
        "created_at": config.get("created_at"),
        "updated_at": config.get("updated_at"),
    }


@router.post("/config")
async def save_slack_config(req: SlackConfigRequest, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()

    if not req.webhook_url.startswith("https://hooks.slack.com/"):
        raise HTTPException(status_code=400, detail="Invalid Slack webhook URL. Must start with https://hooks.slack.com/")

    await db.slack_config.update_one(
        {"organization_id": org_id},
        {"$set": {
            "organization_id": org_id,
            "webhook_url": req.webhook_url,
            "channel_name": req.channel_name,
            "notify_risks": req.notify_risks,
            "notify_tasks": req.notify_tasks,
            "notify_policies": req.notify_policies,
            "notify_audits": req.notify_audits,
            "updated_at": now,
        }, "$setOnInsert": {"created_at": now}},
        upsert=True
    )
    return {"status": "saved", "message": "Slack integration configured successfully"}


@router.post("/test")
async def test_slack_webhook(req: SlackTestRequest, current_user: Dict = Depends(get_current_user)):
    """Send a test message to verify the webhook works."""
    try:
        payload = {
            "blocks": [
                {
                    "type": "header",
                    "text": {"type": "plain_text", "text": "IronVision GRC - Test Notification"}
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"This is a test notification from *IronVision GRC Platform*.\nTriggered by: {current_user.get('name', 'Unknown')}\n\nYour Slack integration is working correctly."
                    }
                },
                {
                    "type": "context",
                    "elements": [
                        {"type": "mrkdwn", "text": f"Sent at {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"}
                    ]
                }
            ]
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(req.webhook_url, json=payload)
            if resp.status_code == 200:
                return {"status": "success", "message": "Test message sent successfully!"}
            else:
                raise HTTPException(status_code=400, detail=f"Slack returned status {resp.status_code}: {resp.text}")
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Slack webhook timed out")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send test message: {str(e)}")


@router.delete("/config")
async def delete_slack_config(current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    await db.slack_config.delete_one({"organization_id": org_id})
    return {"status": "deleted"}


@router.get("/history")
async def get_notification_history(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    history = await db.slack_notifications.find(
        {"organization_id": org_id},
        {"_id": 0}
    ).sort("sent_at", -1).to_list(50)
    return history


# ---- Helper function called by other routes to send Slack notifications ----

async def send_slack_notification(org_id: str, event_type: str, title: str, message: str, severity: str = "info", link: str = None):
    """Send a notification to Slack if configured for this org and event type."""
    config = await db.slack_config.find_one({"organization_id": org_id})
    if not config:
        return

    # Check if this event type is enabled
    type_map = {
        "risk": "notify_risks",
        "task": "notify_tasks",
        "policy": "notify_policies",
        "audit": "notify_audits",
    }
    config_key = type_map.get(event_type)
    if config_key and not config.get(config_key, True):
        return

    severity_emoji = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢", "info": "🔵"}.get(severity, "🔵")

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{severity_emoji} {title}"}
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": message}
        },
    ]

    if link:
        blocks.append({
            "type": "actions",
            "elements": [
                {"type": "button", "text": {"type": "plain_text", "text": "View in IronVision"}, "url": link}
            ]
        })

    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"IronVision GRC | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}"}
        ]
    })

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(config["webhook_url"], json={"blocks": blocks})
            success = resp.status_code == 200
    except Exception as e:
        logger.error(f"Slack notification failed: {e}")
        success = False

    # Log the notification
    await db.slack_notifications.insert_one({
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "event_type": event_type,
        "title": title,
        "message": message,
        "severity": severity,
        "success": success,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    })
