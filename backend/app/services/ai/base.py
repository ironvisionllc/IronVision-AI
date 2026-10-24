from abc import ABC, abstractmethod

from pydantic import BaseModel


class AIRequest(BaseModel):
    system: str
    user: str
    max_tokens: int = 512
    model: str | None = None              # per-request model (use-case override / admin override); adapters fall back to AI_MODEL
    json_schema: dict | None = None       # expected output schema (structured output where the provider supports it)
    schema_name: str | None = None
    temperature: float | None = None


class AIResponse(BaseModel):
    text: str
    provider: str
    model: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None
    finish_reason: str | None = None      # normalised: "length" = reply cut off at max_tokens


class AIProvider(ABC):
    name: str
    model: str | None

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    async def complete(self, request: AIRequest) -> AIResponse: ...

    def describe(self) -> dict:
        return {}


class AIProviderError(RuntimeError):
    pass
