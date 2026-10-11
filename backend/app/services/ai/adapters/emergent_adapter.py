"""DEV ONLY: Emergent universal-key adapter. Delete this file (and the 'emergent' entry in
app/services/ai/service.py ADAPTERS) when migrating off Emergent. See docs/PORTABILITY.md."""
import os
import uuid

from app.config import Settings
from app.services.ai.base import AIProvider, AIRequest, AIResponse


class Provider(AIProvider):
    name = "emergent"

    def __init__(self, settings: Settings):
        self.api_key = os.environ.get("EMERGENT_LLM_KEY")
        self.vendor = os.environ.get("EMERGENT_AI_VENDOR", "anthropic")
        self.model = settings.ai_model

    def is_configured(self) -> bool:
        return bool(self.api_key and self.model)

    async def complete(self, request: AIRequest) -> AIResponse:
        from emergentintegrations.llm.chat import LlmChat, UserMessage

        chat = (
            LlmChat(api_key=self.api_key, session_id=f"aegis-{uuid.uuid4()}", system_message=request.system)
            .with_model(self.vendor, self.model)
            .with_params(max_tokens=request.max_tokens)
        )
        text = await chat.send_message(UserMessage(text=request.user))
        return AIResponse(text=str(text), provider=self.name, model=self.model)
