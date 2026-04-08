"""
Compliance Copilot - LLM-powered Q&A for GRC questions.
Uses Emergent LLM Key with GPT-5.2 via emergentintegrations.
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Optional, List
from datetime import datetime, timezone
import uuid
import logging
import os

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/copilot", tags=["copilot"])

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

SYSTEM_PROMPT = """You are IronVision Compliance Copilot, an expert AI assistant for Governance, Risk & Compliance (GRC).

Your expertise covers:
- Regulatory frameworks (NIST 800-53, ISO 27001, SOC 2, HIPAA, PCI-DSS, FedRAMP, CMMC, GDPR, etc.)
- Risk assessment and management methodologies
- Policy writing and compliance mapping
- Control implementation and testing strategies
- Audit preparation and evidence collection
- Vendor risk management
- Incident response planning

Guidelines:
- Be precise, actionable, and cite specific framework controls when relevant.
- If asked about something outside GRC, politely redirect to compliance topics.
- When recommending controls, reference the specific control ID (e.g., AC-1, A.5.1).
- Provide practical, real-world advice for implementing compliance programs.
- Keep responses concise but thorough. Use bullet points and structured formatting.
"""


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    message_id: str
    response: str
    created_at: str


async def _build_context_snippet(user: Dict) -> str:
    """Build a brief context from the user's org data."""
    org_id = user["roles"][0]["organization_id"] if user.get("roles") else None
    if not org_id:
        return ""

    parts = []
    # Count key items
    policy_count = await db.policies.count_documents({"organization_id": org_id})
    risk_count = await db.risks.count_documents({"organization_id": org_id})
    framework_count = await db.frameworks.count_documents({})

    if policy_count or risk_count or framework_count:
        parts.append(f"\n[User's Organization Context: {policy_count} policies, {risk_count} risks, {framework_count} frameworks loaded]")

    return "\n".join(parts)


@router.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, current_user: Dict = Depends(get_current_user)):
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if not EMERGENT_LLM_KEY:
        raise HTTPException(status_code=503, detail="LLM service not configured")

    session_id = req.session_id or str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    user_id = current_user["id"]
    now = datetime.now(timezone.utc).isoformat()

    # Ensure session exists
    existing = await db.copilot_sessions.find_one({"session_id": session_id, "user_id": user_id})
    if not existing:
        title = req.message[:60] + ("..." if len(req.message) > 60 else "")
        await db.copilot_sessions.insert_one({
            "session_id": session_id,
            "user_id": user_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
        })

    # Store user message
    await db.copilot_messages.insert_one({
        "message_id": str(uuid.uuid4()),
        "session_id": session_id,
        "user_id": user_id,
        "role": "user",
        "content": req.message,
        "created_at": now,
    })

    # Build chat history for context
    history = await db.copilot_messages.find(
        {"session_id": session_id, "user_id": user_id},
        {"_id": 0, "role": 1, "content": 1}
    ).sort("created_at", 1).to_list(20)

    # Call LLM
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        org_context = await _build_context_snippet(current_user)
        system_msg = SYSTEM_PROMPT + org_context

        chat_instance = LlmChat(
            api_key=EMERGENT_LLM_KEY,
            session_id=f"copilot-{session_id}",
            system_message=system_msg,
        )
        chat_instance.with_model("openai", "gpt-5.2")

        # Re-send history to maintain conversation context
        for msg in history[:-1]:  # exclude the last user message we just added
            if msg["role"] == "user":
                um = UserMessage(text=msg["content"])
                await chat_instance.send_message(um)

        # Send the current message
        user_msg = UserMessage(text=req.message)
        ai_response = await chat_instance.send_message(user_msg)

    except Exception as e:
        logger.error(f"Copilot LLM error: {e}")
        ai_response = "I'm sorry, I encountered an error processing your request. Please try again in a moment."

    # Store AI response
    await db.copilot_messages.insert_one({
        "message_id": message_id,
        "session_id": session_id,
        "user_id": user_id,
        "role": "assistant",
        "content": ai_response,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })

    # Update session timestamp
    await db.copilot_sessions.update_one(
        {"session_id": session_id},
        {"$set": {"updated_at": datetime.now(timezone.utc).isoformat()}}
    )

    return ChatResponse(
        session_id=session_id,
        message_id=message_id,
        response=ai_response,
        created_at=now,
    )


@router.get("/sessions")
async def list_sessions(current_user: Dict = Depends(get_current_user)):
    sessions = await db.copilot_sessions.find(
        {"user_id": current_user["id"]},
        {"_id": 0}
    ).sort("updated_at", -1).to_list(50)
    return sessions


@router.get("/sessions/{session_id}/messages")
async def get_session_messages(session_id: str, current_user: Dict = Depends(get_current_user)):
    messages = await db.copilot_messages.find(
        {"session_id": session_id, "user_id": current_user["id"]},
        {"_id": 0}
    ).sort("created_at", 1).to_list(200)
    return messages


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, current_user: Dict = Depends(get_current_user)):
    await db.copilot_sessions.delete_one({"session_id": session_id, "user_id": current_user["id"]})
    await db.copilot_messages.delete_many({"session_id": session_id, "user_id": current_user["id"]})
    return {"status": "deleted"}
