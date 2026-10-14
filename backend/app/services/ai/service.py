import hashlib
import importlib
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache

from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from app.config import get_settings
from app.db import SessionLocal
from app.logging_setup import correlation_id_var
from app.models import AIInteraction
from app.services.ai.base import AIProvider, AIRequest
from app.services.ai.prompts import get_prompt

ADAPTERS = {
    "anthropic": "app.services.ai.adapters.anthropic_adapter",
    "openai_compatible": "app.services.ai.adapters.openai_compatible_adapter",
    "openrouter": "app.services.ai.adapters.openai_compatible_adapter",
    "emergent": "app.services.ai.adapters.emergent_adapter",
}


# prompt_id -> per-use-case model variable (falls back to AI_MODEL); prompts whose id contains "summary" use AI_MODEL_SUMMARY
USE_CASE_MODEL_ENV = {"control.implementation_statement": "AI_MODEL_DRAFTING", "policy.audit": "AI_MODEL_POLICY",
                      "mapping.suggest": "AI_MODEL_MAPPING"}
MODEL_SLUG = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,199}$")


class AIOutputValidationError(RuntimeError):
    pass


def model_for(prompt_id: str, default: str | None, admin_model: str | None = None) -> str | None:
    """Admin override (AI administration page) > AI_MODEL_<USE CASE> > AI_MODEL. Any slug is passed through verbatim."""
    if admin_model:
        return admin_model
    var = USE_CASE_MODEL_ENV.get(prompt_id) or ("AI_MODEL_SUMMARY" if "summary" in prompt_id else None)
    return (os.environ.get(var) if var else None) or default


def env_models() -> dict:
    return {"default": os.environ.get("AI_MODEL") or None,
            **{k.removeprefix("AI_MODEL_").lower(): os.environ.get(k) or None
               for k in ("AI_MODEL_DRAFTING", "AI_MODEL_POLICY", "AI_MODEL_MAPPING", "AI_MODEL_SUMMARY")}}


def _org_model(actor_user_id: uuid.UUID | None) -> str | None:
    if actor_user_id is None:
        return None
    from sqlalchemy import select

    from app.models import AppSetting, User
    with SessionLocal() as db:
        org_id = db.scalar(select(User.org_id).where(User.id == actor_user_id))
        row = db.scalar(select(AppSetting).where(AppSetting.org_id == org_id, AppSetting.key == "ai")) if org_id else None
        return ((row.value or {}).get("model") or None) if row else None


@dataclass
class AIResult:
    output: BaseModel
    provider: str
    model: str | None
    latency_ms: int
    interaction_id: uuid.UUID


def _extract_json(text: str) -> dict:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    cleaned = fenced.group(1) if fenced else text.strip()
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model output")
    return json.loads(match.group(0))


class AIService:
    def __init__(self, provider: AIProvider | None, error: str | None = None):
        self.provider = provider
        self.error = error

    @property
    def configured(self) -> bool:
        return self.provider is not None and self.provider.is_configured()

    def describe(self) -> dict:
        s = get_settings()
        if self.provider is None:
            reason = self.error or ("AI_PROVIDER is empty/none – AI disabled; template drafting is used" if s.ai_provider in ("", "none") else "provider not built")
            return {"provider": s.ai_provider or "none", "model": None, "configured": False, "reason": reason, "app_env": s.environment}
        ok = self.provider.is_configured()
        return {"provider": self.provider.name, "model": self.provider.model, "configured": ok, "app_env": s.environment,
                "models": env_models(), **self.provider.describe(),
                "reason": None if ok else "provider selected but its API key or model is missing"}

    async def run(self, prompt_id: str, version: str, variables: dict, actor_user_id: uuid.UUID | None = None) -> AIResult:
        if not self.configured:
            raise RuntimeError("AI provider is not configured")
        prompt = get_prompt(prompt_id, version)
        model = model_for(prompt_id, self.provider.model, await run_in_threadpool(_org_model, actor_user_id))
        req = AIRequest(system=prompt.system, user=prompt.render(**variables), max_tokens=prompt.max_tokens, model=model,
                        json_schema=prompt.output_model.model_json_schema(), schema_name=prompt_id.replace(".", "_"))
        input_sha = hashlib.sha256((req.system + "\n" + req.user).encode()).hexdigest()
        started = time.perf_counter()
        log = dict(
            provider=self.provider.name, model=model, prompt_id=prompt_id, prompt_version=version,
            input_sha256=input_sha, request=req.model_dump(exclude={"json_schema"}), actor_user_id=actor_user_id,
            correlation_id=correlation_id_var.get(),
        )
        try:
            resp = await self.provider.complete(req)
        except Exception as exc:
            log.update(status="error", validation_status="not_run", error=str(exc)[:2000],
                       latency_ms=int((time.perf_counter() - started) * 1000))
            await run_in_threadpool(_log_interaction, log)
            raise
        log.update(response_text=resp.text, input_tokens=resp.input_tokens, output_tokens=resp.output_tokens,
                   model=resp.model or model)
        try:
            output = prompt.output_model.model_validate(_extract_json(resp.text))
        except (ValueError, ValidationError) as first:
            repair = req.model_copy(update={"user": req.user + "\n\nYour previous reply did not match the required JSON schema: "
                                            + str(first)[:600] + "\nPrevious reply:\n" + resp.text[:4000]
                                            + "\nReturn ONLY the corrected JSON object."})
            try:
                resp2 = await self.provider.complete(repair)
                log.update(response_text=resp2.text, input_tokens=_sum(resp.input_tokens, resp2.input_tokens),
                           output_tokens=_sum(resp.output_tokens, resp2.output_tokens))
                output = prompt.output_model.model_validate(_extract_json(resp2.text))
            except Exception as exc:
                log.update(status="completed", validation_status="invalid", error=f"after one repair retry: {exc}"[:2000],
                           latency_ms=int((time.perf_counter() - started) * 1000))
                await run_in_threadpool(_log_interaction, log)
                raise AIOutputValidationError(f"Model output failed schema validation after one repair retry: {exc}") from exc
        latency = int((time.perf_counter() - started) * 1000)
        log["latency_ms"] = latency
        log.update(status="completed", validation_status="valid", parsed_output=output.model_dump())
        interaction_id = await run_in_threadpool(_log_interaction, log)
        return AIResult(output=output, provider=resp.provider, model=log["model"], latency_ms=latency,
                        interaction_id=interaction_id)


def _sum(a: int | None, b: int | None) -> int | None:
    return None if a is None and b is None else (a or 0) + (b or 0)


def _log_interaction(fields: dict) -> uuid.UUID:
    with SessionLocal() as db:
        row = AIInteraction(**fields)
        db.add(row)
        db.commit()
        return row.id


def build_provider(name: str) -> AIProvider | None:
    if name in ("", "none"):
        return None
    if name not in ADAPTERS:
        raise ValueError(f"Unknown AI_PROVIDER '{name}'. Options: {', '.join(ADAPTERS)} or none")
    if name == "emergent" and get_settings().environment in ("staging", "production"):
        raise ValueError("AI_PROVIDER=emergent is preview-only and is refused in staging/production")
    module = importlib.import_module(ADAPTERS[name])
    return getattr(module, "OpenRouterProvider" if name == "openrouter" else "Provider")(get_settings())


@lru_cache
def get_ai_service() -> AIService:
    try:
        return AIService(build_provider(get_settings().ai_provider))
    except (ValueError, ImportError) as exc:
        return AIService(None, str(exc))
