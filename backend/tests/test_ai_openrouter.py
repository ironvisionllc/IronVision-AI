"""OpenRouter / OpenAI-compatible adapter: structured-output negotiation, retries, error messages, model routing, admin endpoint."""
import asyncio
import json
import os

import httpx
import pytest

from app.services.ai import service as ai_service
from app.services.ai.adapters import openai_compatible_adapter as oa
from app.services.ai.base import AIProviderError, AIRequest
from app.services.ai.prompts import HealthCheckOutput
from tests.conftest import auth

SCHEMA = HealthCheckOutput.model_json_schema()
GOOD = {"status": "ok", "nonce": "abc", "summary": "RMF manages risk."}


def _ok(content: str, model: str = "openai/gpt-4o") -> httpx.Response:
    return httpx.Response(200, json={"model": model, "choices": [{"message": {"content": content}}],
                                     "usage": {"prompt_tokens": 11, "completion_tokens": 7}})


@pytest.fixture
def router(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPAT_API_KEY", "sk-or-test-key")
    monkeypatch.delenv("OPENAI_COMPAT_BASE_URL", raising=False)
    monkeypatch.setenv("OPENROUTER_SITE_URL", "https://app.example.gov")
    monkeypatch.setenv("OPENROUTER_APP_NAME", "IronVision AI")
    oa.Provider._modes.clear()
    slept = []

    async def fake_sleep(s):
        slept.append(s)
    monkeypatch.setattr(oa, "_sleep", fake_sleep)

    class S:
        ai_model = "openai/gpt-4o"
        ai_timeout_seconds = 5
    p = oa.OpenRouterProvider(S())
    p.slept = slept
    return p


def _install(p, handler):
    calls = []

    def wrapped(request: httpx.Request):
        calls.append(json.loads(request.content))
        calls[-1]["_headers"] = dict(request.headers)
        calls[-1]["_url"] = str(request.url)
        return handler(request, len(calls))
    p.transport = httpx.MockTransport(wrapped)
    return calls


def _req(**kw):
    return AIRequest(system="sys", user="usr", json_schema=SCHEMA, schema_name="ai_health_check", **kw)


def test_json_schema_success_headers_and_usage(router):
    calls = _install(router, lambda r, n: _ok(json.dumps(GOOD)))
    resp = asyncio.run(router.complete(_req()))
    c = calls[0]
    assert c["_url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert c["response_format"]["type"] == "json_schema" and c["response_format"]["json_schema"]["strict"] is True
    assert c["model"] == "openai/gpt-4o" and c["max_tokens"] == 512 and c["temperature"] == 0.2
    assert c["_headers"]["authorization"] == "Bearer sk-or-test-key"
    assert c["_headers"]["http-referer"] == "https://app.example.gov" and c["_headers"]["x-title"] == "IronVision AI"
    assert resp.provider == "openrouter" and resp.input_tokens == 11 and resp.output_tokens == 7


def test_falls_back_to_json_object_then_plain_and_remembers(router):
    def handler(r, n):
        body = json.loads(r.content)
        rf = body.get("response_format", {}).get("type")
        if rf in ("json_schema", "json_object"):
            return httpx.Response(400, json={"error": {"message": f"{rf} is not supported by this model"}})
        assert "validates against this JSON Schema" in body["messages"][0]["content"]
        return _ok("```json\n" + json.dumps(GOOD) + "\n```")
    calls = _install(router, handler)
    resp = asyncio.run(router.complete(_req()))
    assert [c.get("response_format", {}).get("type") for c in calls] == ["json_schema", "json_object", None]
    assert ai_service._extract_json(resp.text) == GOOD                     # fenced JSON is stripped
    asyncio.run(router.complete(_req()))
    assert len(calls) == 4 and "response_format" not in calls[3]           # downgrade remembered per (endpoint, model)


def test_json_object_fallback_only(router):
    def handler(r, n):
        rf = json.loads(r.content).get("response_format", {}).get("type")
        return httpx.Response(400, json={"error": {"message": "bad schema"}}) if rf == "json_schema" else _ok(json.dumps(GOOD))
    calls = _install(router, handler)
    asyncio.run(router.complete(_req()))
    assert calls[1]["response_format"] == {"type": "json_object"}
    assert "validates against this JSON Schema" in calls[1]["messages"][0]["content"]


def test_429_retries_with_retry_after(router):
    _install(router, lambda r, n: httpx.Response(429, headers={"Retry-After": "2"}, json={"error": {"message": "slow down"}})
             if n < 3 else _ok(json.dumps(GOOD)))
    resp = asyncio.run(router.complete(_req()))
    assert resp.text and router.slept == [2.0, 2.0]


def test_429_gives_up_with_clear_message(router):
    _install(router, lambda r, n: httpx.Response(429, json={"error": {"message": "rate"}}))
    with pytest.raises(AIProviderError, match=r"rate limited \(429\) after 3 retries"):
        asyncio.run(router.complete(_req()))


def test_402_insufficient_credits_message(router):
    _install(router, lambda r, n: httpx.Response(402, json={"error": {"code": 402, "message": "Insufficient credits"}}))
    with pytest.raises(AIProviderError) as ei:
        asyncio.run(router.complete(_req()))
    assert "insufficient credits (402)" in str(ei.value) and "openrouter.ai/settings/credits" in str(ei.value)
    assert "sk-or-test-key" not in str(ei.value)


def test_error_inside_200_body_and_timeout(router):
    _install(router, lambda r, n: httpx.Response(200, json={"error": {"code": 402, "message": "credits"}}))
    with pytest.raises(AIProviderError, match="insufficient credits"):
        asyncio.run(router.complete(_req()))

    def boom(r, n):
        raise httpx.ReadTimeout("slow", request=r)
    _install(router, boom)
    with pytest.raises(AIProviderError, match="timed out after 5s"):
        asyncio.run(router.complete(_req()))


def test_any_model_slug_passed_verbatim(router):
    calls = _install(router, lambda r, n: _ok(json.dumps(GOOD), model="meta-llama/llama-3.1-70b-instruct"))
    resp = asyncio.run(router.complete(_req(model="meta-llama/llama-3.1-70b-instruct")))
    assert calls[0]["model"] == "meta-llama/llama-3.1-70b-instruct" and resp.model == "meta-llama/llama-3.1-70b-instruct"


def test_openrouter_never_reads_anthropic_key(monkeypatch):
    seen = []

    class Recording(dict):
        def get(self, k, d=None):
            seen.append(k)
            return super().get(k, d)

        def __getitem__(self, k):
            seen.append(k)
            return super().__getitem__(k)
    env = Recording({**os.environ, "ANTHROPIC_API_KEY": "sk-ant-should-not-be-read", "OPENAI_COMPAT_API_KEY": "k",
                     "AI_PROVIDER": "openrouter", "AI_MODEL": "openai/gpt-4o"})
    monkeypatch.setattr(oa.os, "environ", env)
    monkeypatch.setattr(ai_service.os, "environ", env)
    monkeypatch.setattr(ai_service, "get_settings", lambda: type("S", (), {"ai_model": "openai/gpt-4o", "ai_timeout_seconds": 5,
                                                                           "environment": "production", "ai_provider": "openrouter"})())
    p = ai_service.build_provider("openrouter")
    assert p.name == "openrouter" and p.is_configured() and p.base_url == "https://openrouter.ai/api/v1"
    p.headers()
    ai_service.env_models()
    assert "ANTHROPIC_API_KEY" not in seen
    import sys


def test_per_use_case_model_override(monkeypatch):
    monkeypatch.setenv("AI_MODEL_DRAFTING", "anthropic/claude-3.5-sonnet")
    monkeypatch.setenv("AI_MODEL_POLICY", "mistralai/mistral-large")
    monkeypatch.delenv("AI_MODEL_MAPPING", raising=False)
    monkeypatch.setenv("AI_MODEL_SUMMARY", "openai/gpt-4.1")
    assert ai_service.model_for("control.implementation_statement", "openai/gpt-4o") == "anthropic/claude-3.5-sonnet"
    assert ai_service.model_for("policy.audit", "openai/gpt-4o") == "mistralai/mistral-large"
    assert ai_service.model_for("mapping.suggest", "openai/gpt-4o") == "openai/gpt-4o"
    assert ai_service.model_for("evidence.summary", "openai/gpt-4o") == "openai/gpt-4.1"
    assert ai_service.model_for("policy.audit", "openai/gpt-4o", "openai/gpt-4.1") == "openai/gpt-4.1"   # admin override wins


def test_service_repair_retry_then_clear_failure(monkeypatch):
    replies = iter(["not json", json.dumps(GOOD)])

    class P:
        name, model = "openrouter", "openai/gpt-4o"

        def is_configured(self):
            return True

        def describe(self):
            return {}

        async def complete(self, req):
            from app.services.ai.base import AIResponse
            return AIResponse(text=next(replies), provider="openrouter", model=req.model, input_tokens=3, output_tokens=2)
    logged = []
    monkeypatch.setattr(ai_service, "_log_interaction", lambda f: logged.append(f) or __import__("uuid").uuid4())
    monkeypatch.setattr(ai_service, "_org_model", lambda uid: None)
    svc = ai_service.AIService(P())
    res = asyncio.run(svc.run("ai.health_check", "1.0.0", {"nonce": "abc"}))
    assert res.output.nonce == "abc" and logged[-1]["validation_status"] == "valid" and logged[-1]["input_tokens"] == 6
    assert "json_schema" not in logged[-1]["request"] and logged[-1]["provider"] == "openrouter"
    replies = iter(["nope", "still nope"])
    with pytest.raises(ai_service.AIOutputValidationError, match="after one repair retry"):
        asyncio.run(svc.run("ai.health_check", "1.0.0", {"nonce": "abc"}))
    assert logged[-1]["validation_status"] == "invalid"


def test_check_env_openrouter_rules():
    from app.check_env import validate
    from tests.test_deploy_hardening import GOOD as PROD
    env = PROD | {"AI_PROVIDER": "openrouter", "AI_MODEL": "openai/gpt-4o"}
    errs, _ = validate(env)
    assert "OPENAI_COMPAT_API_KEY is required for AI_PROVIDER=openrouter" in errs
    errs, warns = validate(env | {"OPENAI_COMPAT_API_KEY": "sk-or-x", "ANTHROPIC_API_KEY": "sk-ant-x"})
    assert errs == [] and any("ANTHROPIC_API_KEY is set but never used" in w for w in warns)
    errs, _ = validate(env | {"OPENAI_COMPAT_API_KEY": "k", "OPENAI_COMPAT_BASE_URL": "http://openrouter.ai/api/v1"})
    assert any("must be https://" in e for e in errs)
    errs, _ = validate(env | {"OPENAI_COMPAT_API_KEY": "k", "AI_MODEL": "openai/gpt 4o"})
    assert any("single model slug" in e for e in errs)


def test_admin_model_override_and_effective_settings(client, token):
    h = auth(token("platform.admin@aegisrmf.demo"))
    r = client.put("/api/v1/admin/ai-settings", json={"model": "openai/gpt 4o"}, headers=h)
    assert r.status_code == 422
    r = client.put("/api/v1/admin/ai-settings", json={"model": "meta-llama/llama-3.1-70b-instruct"}, headers=h)
    assert r.status_code == 200 and r.json()["model"] == "meta-llama/llama-3.1-70b-instruct"
    g = client.get("/api/v1/admin/ai-settings", headers=h).json()
    assert g["model"] == "meta-llama/llama-3.1-70b-instruct" and g["model_source"] == "admin override"
    assert "openai/gpt-4.1" in g["model_examples"] and "effective" in g
    blob = json.dumps(g)
    assert "api_key" not in blob.replace("api_key_configured", "") and "sk-" not in blob
    assert client.put("/api/v1/admin/ai-settings", json={"model": ""}, headers=h).json()["model"] is None


def test_ai_health_endpoint_uses_openrouter(client, token, monkeypatch):
    monkeypatch.setenv("OPENAI_COMPAT_API_KEY", "sk-or-test-key")
    oa.Provider._modes.clear()

    class S:
        ai_model = "openai/gpt-4o"
        ai_timeout_seconds = 5
    p = oa.OpenRouterProvider(S())

    def handler(r):
        body = json.loads(r.content)
        nonce = body["messages"][1]["content"].split('"nonce": "')[1].split('"')[0]
        return _ok(json.dumps({"status": "ok", "nonce": nonce, "summary": "RMF is a risk framework."}))
    p.transport = httpx.MockTransport(handler)
    monkeypatch.setattr(ai_service, "get_ai_service", lambda: ai_service.AIService(p))
    import app.api.v1.ai as ai_api
    monkeypatch.setattr(ai_api, "get_ai_service", lambda: ai_service.AIService(p))
    r = client.post("/api/v1/ai/health", headers=auth(token("platform.admin@aegisrmf.demo")))
    assert r.status_code == 200, r.text
    assert r.json()["provider"] == "openrouter" and r.json()["model"] == "openai/gpt-4o"


@pytest.mark.skipif(not os.environ.get("OPENAI_COMPAT_API_KEY") or os.environ.get("AI_PROVIDER") != "openrouter",
                    reason="live OpenRouter call only when AI_PROVIDER=openrouter and OPENAI_COMPAT_API_KEY are set")
def test_live_openrouter_health():
    p = ai_service.build_provider("openrouter")
    svc = ai_service.AIService(p)
    res = asyncio.run(svc.run("ai.health_check", "1.0.0", {"nonce": "live123"}))
    assert res.output.nonce == "live123"
