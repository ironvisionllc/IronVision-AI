"""OpenAI Chat Completions adapters over plain httpx: `openai_compatible` (vLLM, Ollama, LM Studio, gateways) and `openrouter`.

POST {base_url}/chat/completions with messages / temperature / max_tokens. Structured output is negotiated per (endpoint, model):
response_format json_schema (strict) → json_object → plain prompt ("return only JSON matching this schema"); the first mode
the endpoint rejects (400/404/422) is skipped for later calls. 429/502/503 are retried honouring Retry-After. The API key is
only ever sent as a bearer header – never logged or returned."""
import asyncio
import json
import os

import httpx

from app.config import Settings
from app.services.ai.base import AIProvider, AIProviderError, AIRequest, AIResponse

MODES = ("json_schema", "json_object", "plain")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MAX_RETRIES = 3
_sleep = asyncio.sleep


def _retry_after(r: httpx.Response, attempt: int) -> float:
    try:
        return min(float(r.headers.get("retry-after", "")), 30.0)
    except ValueError:
        return min(2.0 ** attempt, 30.0)


def _message(data: dict) -> str:
    err = data.get("error") if isinstance(data, dict) else None
    if isinstance(err, dict):
        return str(err.get("message") or err.get("code") or err)[:300]
    return str(err or data)[:300]


class Provider(AIProvider):
    name = "openai_compatible"
    default_base_url: str | None = None
    key_required = False
    _modes: dict[tuple[str | None, str | None], str] = {}

    def __init__(self, settings: Settings):
        self.base_url = (os.environ.get("OPENAI_COMPAT_BASE_URL") or self.default_base_url or "").rstrip("/") or None
        self.api_key = os.environ.get("OPENAI_COMPAT_API_KEY") or None
        self.model = settings.ai_model
        self.timeout = settings.ai_timeout_seconds
        self.temperature = float(os.environ.get("AI_TEMPERATURE") or 0.2)
        self.transport: httpx.AsyncBaseTransport | None = None   # tests inject httpx.MockTransport

    def is_configured(self) -> bool:
        return bool(self.base_url and self.model and (self.api_key or not self.key_required))

    def describe(self) -> dict:
        return {"base_url": self.base_url, "api_key_configured": bool(self.api_key),
                "structured_output": "json_schema → json_object → prompt (validated with Pydantic, one repair retry)"}

    def headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    def _body(self, request: AIRequest, model: str, mode: str) -> dict:
        system = request.system
        if request.json_schema and mode != "json_schema":
            system += ("\n\nReturn ONLY one JSON object (no markdown, no code fences) that validates against this JSON Schema:\n"
                       + json.dumps(request.json_schema, separators=(",", ":")))
        body = {"model": model, "max_tokens": request.max_tokens,
                "temperature": self.temperature if request.temperature is None else request.temperature,
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": request.user}]}
        if mode == "json_schema":
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": request.schema_name or "output", "strict": True, "schema": request.json_schema}}
        elif mode == "json_object":
            body["response_format"] = {"type": "json_object"}
        return body

    async def _post(self, client: httpx.AsyncClient, body: dict) -> tuple[int, dict]:
        for attempt in range(MAX_RETRIES + 1):
            try:
                r = await client.post(f"{self.base_url}/chat/completions", json=body, headers=self.headers())
            except httpx.TimeoutException as exc:
                raise AIProviderError(f"{self.name}: request timed out after {self.timeout}s (AI_TIMEOUT_SECONDS)") from exc
            except httpx.HTTPError as exc:
                raise AIProviderError(f"{self.name}: cannot reach {self.base_url} ({type(exc).__name__})") from exc
            if r.status_code in (429, 502, 503) and attempt < MAX_RETRIES:
                await _sleep(_retry_after(r, attempt))
                continue
            try:
                data = r.json()
            except ValueError:
                data = {"error": {"message": r.text[:300]}}
            return r.status_code, data
        raise AssertionError("unreachable")

    def _error(self, status: int, data: dict, model: str) -> AIProviderError:
        msg = _message(data)
        if status == 401:
            return AIProviderError(f"{self.name}: API key rejected (401) – check OPENAI_COMPAT_API_KEY")
        if status == 402:
            return AIProviderError(f"{self.name}: insufficient credits (402) – add credits to the account "
                                   f"(OpenRouter: https://openrouter.ai/settings/credits) or choose a cheaper model. Provider: {msg}")
        if status == 429:
            return AIProviderError(f"{self.name}: rate limited (429) after {MAX_RETRIES} retries – try again later. Provider: {msg}")
        if status == 404:
            return AIProviderError(f"{self.name}: model {model!r} not found or no provider available (404). Provider: {msg}")
        return AIProviderError(f"{self.name}: HTTP {status} from {self.base_url}. Provider: {msg}")

    async def complete(self, request: AIRequest) -> AIResponse:
        model = request.model or self.model
        key = (self.base_url, model)
        modes = MODES if request.json_schema else ("plain",)
        if request.json_schema and key in self._modes:
            modes = MODES[MODES.index(self._modes[key]):]
        async with httpx.AsyncClient(timeout=self.timeout, transport=self.transport) as client:
            for i, mode in enumerate(modes):
                status, data = await self._post(client, self._body(request, model, mode))
                if status in (400, 404, 422) and mode != "plain":
                    self._modes[key] = modes[i + 1]
                    continue
                if status >= 400:
                    raise self._error(status, data, model)
                if not data.get("choices"):
                    code = (data.get("error") or {}).get("code") if isinstance(data.get("error"), dict) else None
                    raise self._error(int(code) if str(code).isdigit() else 502, data, model)
                self._modes.setdefault(key, mode)
                content = data["choices"][0].get("message", {}).get("content") or ""
                if isinstance(content, list):
                    content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
                usage = data.get("usage") or {}
                finish = data["choices"][0].get("finish_reason")
                return AIResponse(text=content, provider=self.name, model=data.get("model") or model,
                                  input_tokens=usage.get("prompt_tokens"), output_tokens=usage.get("completion_tokens"),
                                  finish_reason="length" if finish in ("length", "max_tokens") else finish)
        raise AssertionError("unreachable")


class OpenRouterProvider(Provider):
    """OpenRouter: one key (OPENAI_COMPAT_API_KEY), any model slug in AI_MODEL, passed through verbatim."""

    name = "openrouter"
    default_base_url = OPENROUTER_BASE_URL
    key_required = True

    def headers(self) -> dict:
        h = super().headers()
        if os.environ.get("OPENROUTER_SITE_URL"):
            h["HTTP-Referer"] = os.environ["OPENROUTER_SITE_URL"]
        if os.environ.get("OPENROUTER_APP_NAME"):
            h["X-Title"] = os.environ["OPENROUTER_APP_NAME"]
        return h
