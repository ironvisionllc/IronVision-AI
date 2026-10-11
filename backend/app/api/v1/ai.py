import secrets

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from app.schemas import AIHealthOut
from app.security.deps import CurrentUser, require_permission
from app.services import audit
from app.services.ai.service import AIOutputValidationError, get_ai_service

router = APIRouter(prefix="/ai", tags=["ai"])
PROMPT_ID, PROMPT_VERSION = "ai.health_check", "1.0.0"


@router.post("/health", response_model=AIHealthOut)
async def ai_health(request: Request, current: CurrentUser = Depends(require_permission("admin.ai.test"))) -> AIHealthOut:
    service = get_ai_service()
    if not service.configured:
        raise HTTPException(503, f"AI provider not configured: {service.describe()}")
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
