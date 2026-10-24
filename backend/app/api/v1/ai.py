import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.db import get_db
from app.models import AIInteraction
from app.schemas import AIHealthOut
from app.security.rbac import has_permission
from app.security.deps import CurrentUser, get_current_user, require_permission
from app.services import audit, rmf
from app.services.ai.service import AIOutputValidationError, get_ai_service

router = APIRouter(prefix="/ai", tags=["ai"])
PROMPT_ID, PROMPT_VERSION = "ai.health_check", "1.0.0"


DETERMINISTIC = "Deterministic analysis (no AI)"


def _can(current: CurrentUser, perm: str) -> bool:
    return has_permission(current.assignments, perm, current.user.org_id)


def _usage(db: Session) -> dict:
    ok = (AIInteraction.status == "completed") & (AIInteraction.validation_status == "valid")
    last_ok = db.execute(select(AIInteraction.created_at, AIInteraction.provider, AIInteraction.model, AIInteraction.latency_ms)
                         .where(ok).order_by(AIInteraction.created_at.desc()).limit(1)).first()
    last_err = db.execute(select(AIInteraction.created_at, AIInteraction.error).where(~ok)
                          .order_by(AIInteraction.created_at.desc()).limit(1)).first()
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    calls, tokens = db.execute(select(func.count(), func.coalesce(func.sum(func.coalesce(AIInteraction.input_tokens, 0)
                               + func.coalesce(AIInteraction.output_tokens, 0)), 0)).where(AIInteraction.created_at >= since)).one()
    return {"last_success_at": last_ok.created_at.isoformat() if last_ok else None,
            "last_success": {"provider": last_ok.provider, "model": last_ok.model, "latency_ms": last_ok.latency_ms} if last_ok else None,
            "last_error_at": last_err.created_at.isoformat() if last_err else None,
            "last_error": (last_err.error or "")[:300] if last_err else None, "calls_24h": calls, "tokens_24h": int(tokens)}


@router.get("/status")
def ai_status(db: Session = Depends(get_db), current: CurrentUser = Depends(get_current_user)) -> dict:
    """Non-secret AI status for every signed-in role: provider, model, configured, last successful call, fallback mode."""
    svc = get_ai_service()
    d = svc.describe()
    override = rmf.get_setting(db, current.user.org_id, "ai", rmf.AI_DEFAULTS).get("model")
    usage = _usage(db)
    if not _can(current, "admin.health.read"):
        usage.pop("last_error")
    model = (override or d.get("model")) if d["configured"] else d.get("model")
    return {"provider": d["provider"], "model": model, "model_source": "admin override" if override and d["configured"] else "AI_MODEL",
            "configured": d["configured"], "mode": "ai" if d["configured"] else "deterministic",
            "mode_label": f"AI-assisted ({d['provider']} / {model})" if d["configured"] else DETERMINISTIC,
            "base_url": d.get("base_url"), "api_key_configured": bool(d.get("api_key_configured")),
            "reason": d.get("reason"), "app_env": d.get("app_env"), "can_test": _can(current, "admin.ai.test"), **usage}


@router.post("/health", response_model=AIHealthOut)
async def ai_health(request: Request, current: CurrentUser = Depends(require_permission("admin.ai.test"))) -> AIHealthOut:
    service = get_ai_service()
    if not service.configured:
        await run_in_threadpool(audit.record_now, action="ai.health", outcome="failure", actor_user_id=current.user.id,
                                actor_email=current.user.email, details={"error": "not configured", **service.describe()},
                                **audit.request_meta(request))
        raise HTTPException(503, f"AI provider not configured – {service.describe().get('reason')}. Analyses use {DETERMINISTIC}.")
    nonce = secrets.token_hex(6)
    meta = audit.request_meta(request)
    try:
        result = await service.run(PROMPT_ID, PROMPT_VERSION, {"nonce": nonce}, actor_user_id=current.user.id)
        if result.output.nonce != nonce:
            raise AIOutputValidationError("Nonce mismatch in model output")
    except Exception as exc:
        await run_in_threadpool(audit.record_now, action="ai.health", outcome="failure", actor_user_id=current.user.id,
                                actor_email=current.user.email, details={"error": str(exc)[:300]}, **meta)
        raise HTTPException(502, f"AI call failed: {str(exc)[:300]}")
    await run_in_threadpool(audit.record_now, action="ai.health", outcome="success", actor_user_id=current.user.id,
                            actor_email=current.user.email, entity_type="ai_interaction",
                            entity_id=str(result.interaction_id),
                            details={"provider": result.provider, "model": result.model, "latency_ms": result.latency_ms},
                            **meta)
    return AIHealthOut(ok=True, provider=result.provider, model=result.model, latency_ms=result.latency_ms,
                       prompt_id=PROMPT_ID, prompt_version=PROMPT_VERSION, interaction_id=result.interaction_id,
                       output=result.output.model_dump())
