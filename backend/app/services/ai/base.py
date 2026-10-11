from abc import ABC, abstractmethod

from pydantic import BaseModel


class AIRequest(BaseModel):
    system: str
    user: str
    max_tokens: int = 512


class AIResponse(BaseModel):
    text: str
    provider: str
    model: str | None
    input_tokens: int | None = None
    output_tokens: int | None = None


class AIProvider(ABC):
    name: str
    model: str | None

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    async def complete(self, request: AIRequest) -> AIResponse: ...


class AIProviderError(RuntimeError):
    pass
