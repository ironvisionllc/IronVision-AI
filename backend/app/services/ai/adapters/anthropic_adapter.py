import os

from app.config import Settings
from app.services.ai.base import AIProvider, AIRequest, AIResponse


class Provider(AIProvider):
    """Direct Anthropic API adapter (ANTHROPIC_API_KEY, AI_MODEL)."""

    name = "anthropic"

    def __init__(self, settings: Settings):
        self.api_key = os.environ.get("ANTHROPIC_API_KEY")
        self.model = settings.ai_model
        self.timeout = settings.ai_timeout_seconds

    def is_configured(self) -> bool:
        return bool(self.api_key and self.model)

    async def complete(self, request: AIRequest) -> AIResponse:
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=self.api_key, timeout=self.timeout)
        msg = await client.messages.create(
            model=self.model,
            max_tokens=request.max_tokens,
            system=request.system,
            messages=[{"role": "user", "content": ([{"type": "text", "text": request.cache_prefix, "cache_control": {"type": "ephemeral"}},
                                                    {"type": "text", "text": request.user[len(request.cache_prefix):] or " "}]
                                                   if request.cache_prefix and request.user.startswith(request.cache_prefix) else request.user)}],
        )
        text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
        return AIResponse(text=text, provider=self.name, model=msg.model,
                          input_tokens=msg.usage.input_tokens, output_tokens=msg.usage.output_tokens,
                          cached_tokens=getattr(msg.usage, "cache_read_input_tokens", None), cache_write_tokens=getattr(msg.usage, "cache_creation_input_tokens", None),
                          finish_reason="length" if msg.stop_reason == "max_tokens" else msg.stop_reason)
