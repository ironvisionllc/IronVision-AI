"""Truncated replies (finish_reason=length): detected by adapter + service, coverage refine retries the batch smaller and merges."""
import asyncio
import json

import httpx
import pytest

from app.services import policy_coverage as pc
from app.services.ai import service as ai_service
from app.services.ai.base import AIResponse
from app.services.ai.adapters import openai_compatible_adapter as oa
from tests.test_ai_openrouter import _install, _req


def test_adapter_normalises_finish_reason_length(monkeypatch):
    monkeypatch.setenv("OPENAI_COMPAT_API_KEY", "sk-or-test-key")
    router = oa.OpenRouterProvider(type("S", (), {"ai_model": "openai/gpt-4o", "ai_timeout_seconds": 5})())
    _install(router, lambda r, n: httpx.Response(200, json={"choices": [{"message": {"content": "{\"st"}, "finish_reason": "length"}]}))
    assert asyncio.run(router.complete(_req())).finish_reason == "length"


class FakeProvider:
    """Answers coverage batches; any batch larger than `limit` requirements comes back cut off (finish_reason=length)."""
    name, model = "openrouter", "anthropic/claude-sonnet-5.5"

    def __init__(self, limit: int, fail_ids: frozenset = frozenset()):
        self.limit, self.fail_ids, self.sizes, self.max_tokens = limit, fail_ids, [], []

    def is_configured(self):
        return True

    def describe(self):
        return {}

    async def complete(self, req):
        reqs = json.loads(req.user.split("deterministic result):\n", 1)[1].split("\n\nPolicy text", 1)[0])
        self.sizes.append(len(reqs))
        self.max_tokens.append(req.max_tokens)
        if len(reqs) > self.limit:
            return AIResponse(text='{"items": [{"requirement_id": "x", "sta', provider=self.name, model=self.model,
                              input_tokens=100, output_tokens=req.max_tokens, finish_reason="length")
        if any(r["requirement_id"] in self.fail_ids for r in reqs):
            return AIResponse(text="not json", provider=self.name, model=self.model, finish_reason="stop")
        items = [{"requirement_id": r["requirement_id"], "status": "met", "quote": "Accounts are reviewed.", "rationale": "stated"} for r in reqs]
        return AIResponse(text=json.dumps({"items": items}), provider=self.name, model=self.model, input_tokens=100,
                          output_tokens=50, finish_reason="stop")


@pytest.fixture
def logged(monkeypatch):
    rows = []
    monkeypatch.setattr(ai_service, "_log_interaction", lambda f: rows.append(dict(f)) or __import__("uuid").uuid4())
    monkeypatch.setattr(ai_service, "_org_model", lambda uid: None)
    return rows


def _reqs(n):
    return [{"id": f"r{i}", "text": f"Requirement {i}"} for i in range(n)], [("kw", {"status": "missing"})] * n


def _run(monkeypatch, provider, n):
    monkeypatch.setattr(ai_service, "get_ai_service", lambda: ai_service.AIService(provider))
    stats: dict = {}
    reqs, results = _reqs(n)
    return pc.ai_refine("Accounts are reviewed.", "ac-2", reqs, results, None, stats), stats


def test_service_raises_truncated_without_repair_retry(monkeypatch, logged):
    p = FakeProvider(limit=0)
    with pytest.raises(ai_service.AIOutputTruncatedError, match="finish_reason=length"):
        asyncio.run(ai_service.AIService(p).run("policy.coverage_refine", "1.0.0",
                                                {"control_id": "AC-2", "requirements": json.dumps([{"requirement_id": "a"}]), "policy": "x"}))
    assert len(p.sizes) == 1 and logged[-1]["status"] == "truncated" and logged[-1]["validation_status"] == "not_run"


def test_large_control_is_batched_and_merged(monkeypatch, logged):
    monkeypatch.setenv("AI_MAX_OUTPUT_TOKENS", "5000")
    p = FakeProvider(limit=10)
    out, stats = _run(monkeypatch, p, 20)
    assert p.sizes == [8, 8, 4] and set(p.max_tokens) == {5000}
    assert set(out) == {f"r{i}" for i in range(20)} and stats == {"batches": 3, "succeeded": 3, "failed": 0, "truncated": 0}


def test_truncated_batch_is_retried_smaller(monkeypatch, logged):
    p = FakeProvider(limit=3)
    out, stats = _run(monkeypatch, p, 10)
    assert len(out) == 10 and stats["failed"] == 0 and stats["truncated"] >= 2
    assert all(s <= 8 for s in p.sizes) and max(s for s in p.sizes if s <= 3) <= 3


def test_one_failed_batch_does_not_drop_the_others(monkeypatch, logged):
    p = FakeProvider(limit=10, fail_ids=frozenset({"r9"}))
    out, stats = _run(monkeypatch, p, 20)
    assert set(out) == {f"r{i}" for i in range(20)} - {f"r{i}" for i in range(8, 16)}
    assert stats["failed"] == 1 and stats["succeeded"] == 2


def test_default_max_output_tokens(monkeypatch):
    monkeypatch.delenv("AI_MAX_OUTPUT_TOKENS", raising=False)
    assert ai_service.ai_max_output_tokens() == 8000
