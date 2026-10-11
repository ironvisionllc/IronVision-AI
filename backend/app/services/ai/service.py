import hashlib
import importlib
import json
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
    "emergent": "app.services.ai.adapters.emergent_adapter",
}


class AIOutputValidationError(RuntimeError):
    pass


@dataclass
class AIResult:
    output: BaseModel
    provider: str
    model: str | None
    latency_ms: int
    interaction_id: uuid.UUID


def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in model output")
    return json.loads(match.group(0))


class AIService:
    def __init__(self, provider: AIProvider | None):
        self.provider = provider

    @property
    def configured(self) -> bool:
        return self.provider is not None and self.provider.is_configured()

    def describe(self) -> dict:
        if self.provider is None:
            return {"provider": "none", "model": None, "configured": False}
        return {"provider": self.provider.name, "model": self.provider.model, "configured": self.provider.is_configured()}

    async def run(self, prompt_id: str, version: str, variables: dict, actor_user_id: uuid.UUID | None = None) -> AIResult:
        if not self.configured:
            raise RuntimeError("AI provider is not configured")
        prompt = get_prompt(prompt_id, version)
        req = AIRequest(system=prompt.system, user=prompt.render(**variables), max_tokens=prompt.max_tokens)
        input_sha = hashlib.sha256((req.system + "\n" + req.user).encode()).hexdigest()
        started = time.perf_counter()
        log = dict(
            provider=self.provider.name, model=self.provider.model, prompt_id=prompt_id, prompt_version=version,
            input_sha256=input_sha, request=req.model_dump(), actor_user_id=actor_user_id,
            correlation_id=correlation_id_var.get(),
        )
        try:
            resp = await self.provider.complete(req)
        except Exception as exc:
            log.update(status="error", validation_status="not_run", error=str(exc)[:2000],
                       latency_ms=int((time.perf_counter() - started) * 1000))
            await run_in_threadpool(_log_interaction, log)
            raise
        latency = int((time.perf_counter() - started) * 1000)
        log.update(response_text=resp.text, latency_ms=latency, input_tokens=resp.input_tokens,
                   output_tokens=resp.output_tokens, model=resp.model or self.provider.model)
        try:
            output = prompt.output_model.model_validate(_extract_json(resp.text))
        except (ValueError, ValidationError) as exc:
            log.update(status="completed", validation_status="invalid", error=str(exc)[:2000])
            await run_in_threadpool(_log_interaction, log)
            raise AIOutputValidationError(f"Model output failed schema validation: {exc}") from exc
        log.update(status="completed", validation_status="valid", parsed_output=output.model_dump())
        interaction_id = await run_in_threadpool(_log_interaction, log)
        return AIResult(output=output, provider=resp.provider, model=log["model"], latency_ms=latency,
                        interaction_id=interaction_id)


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
    module = importlib.import_module(ADAPTERS[name])
    return module.Provider(get_settings())


@lru_cache
def get_ai_service() -> AIService:
    return AIService(build_provider(get_settings().ai_provider))
