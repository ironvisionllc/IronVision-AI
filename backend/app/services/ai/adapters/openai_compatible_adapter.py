import os

from app.config import Settings
from app.services.ai.base import AIProvider, AIRequest, AIResponse


class Provider(AIProvider):
    """OpenAI-compatible Chat Completions adapter (vLLM, Ollama, LM Studio, Azure-style gateways)."""

    name = "openai_compatible"

    def __init__(self, settings: Settings):
        self.base_url = os.environ.get("OPENAI_COMPAT_BASE_URL")
        self.api_key = os.environ.get("OPENAI_COMPAT_API_KEY") or "not-required"
        self.model = settings.ai_model
        self.timeout = settings.ai_timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.base_url and self.model)

    async def complete(self, request: AIRequest) -> AIResponse:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key, timeout=self.timeout)
        resp = await client.chat.completions.create(
            model=self.model,
            max_tokens=request.max_tokens,
            messages=[{"role": "system", "content": request.system}, {"role": "user", "content": request.user}],
        )
        usage = resp.usage
        return AIResponse(
            text=resp.choices[0].message.content or "",
            provider=self.name,
            model=resp.model,
            input_tokens=usage.prompt_tokens if usage else None,
            output_tokens=usage.completion_tokens if usage else None,
        )
