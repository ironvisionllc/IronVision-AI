"""No silent misses: whole-document mode (screening orders, never excludes; full document as a cached prompt prefix), coverage guard,
second look (index first, focused whole-document AI only when the index finds nothing), and forgiving quote matching. AI is faked."""
import json
import uuid
from types import SimpleNamespace

import pytest

from app.db import SessionLocal
from app.models import Organization
from app.services import policy_analyzer_v2 as v2
from app.services import policy_profile as pp
from app.services.ai.adapters.openai_compatible_adapter import _user_content
from app.services.ai.base import AIRequest
from tests.test_policy_v2 import DOC, TODO

TITLES = {"ac-2": "Account Management", "ac-17": "Remote Access", "ia-5": "Authenticator Management"}


class WholeDocSvc:
    """First pass: everything 'missing' except ac-2_obj.d; second look: finds ac-2_obj.j, confirms ia-5 absent."""

    def __init__(self):
        self.calls, self.provider = [], SimpleNamespace(model="fake/model")

    async def run(self, pid, ver, vars, max_tokens=None, cache_prefix_var=None):
        reqs = json.loads(vars["requirements"])
        self.calls.append({"prompt": (pid, ver), "doc": "document" in vars, "cache": cache_prefix_var, "ids": [r["requirement_id"] for r in reqs]})
        items = []
        for r in reqs:
            q = {"ac-2_obj.d": "account managers are assigned for every information system account"}.get(r["requirement_id"], "")
            if (pid, ver) == v2.PROMPT_SECOND and r["requirement_id"] == "ac-2_obj.j":
                q = "Accounts are reviewed every 90 days."
            items.append(SimpleNamespace(control_id=r["control_id"], requirement_id=r["requirement_id"], status="met" if q else "missing",
                                         quote=q, section="S1", rationale="Stated." if q else "Not stated."))
        return SimpleNamespace(output=SimpleNamespace(items=items), model="fake/model", usage={"input": 1000, "output": 50, "cached": 800, "cache_write": 0})


@pytest.fixture
def svc(monkeypatch):
    f = WholeDocSvc()
    monkeypatch.setattr("app.services.ai.service.get_ai_service", lambda: f)
    monkeypatch.setenv("POLICY_AI_CACHE", "0")
    monkeypatch.setenv("POLICY_AI_WHOLE_DOC", "1")
    monkeypatch.setattr("app.services.policy_second_look.THRESHOLD", 0.95)  # make the index miss → exercise the AI escalation
    return f


def _org():
    with SessionLocal() as db:
        o = Organization(name=f"NSM {uuid.uuid4().hex[:8]}", slug=f"nsm-{uuid.uuid4().hex[:8]}", is_synthetic=True, is_sandbox=True)
        db.add(o)
        db.commit()
        return o.id


def test_whole_document_no_exclusion_cached_prefix_and_coverage_guard(svc):
    out, st = v2.analyze_ai(DOC, uuid.uuid4(), _org(), TODO, TITLES, "cat")
    first = [c for c in svc.calls if c["prompt"] == v2.PROMPT_WD]
    assert first and all(c["doc"] and c["cache"] == "document" for c in first)
    assert st["whole_document"] and st["not_examined"] == 0 and st["examined"] == 4  # ia-5 (no relevant section) still examined
    assert st["chunks_covered"] == st["chunks_total"] and not st["uncovered_sections"]
    assert st["tokens_cached"] > 0 and st["prompt_cache_hits"] == st["calls"]


def test_large_document_retrieval_mode_never_excludes_and_second_look_uses_whole_doc(monkeypatch, svc):
    monkeypatch.setenv("POLICY_AI_WHOLE_DOC", "auto")
    monkeypatch.setenv("POLICY_AI_WHOLE_DOC_MAX_CHARS", "10")  # force "large": batches carry retrieved sections only
    out, st = v2.analyze_ai(DOC, uuid.uuid4(), _org(), TODO, TITLES, "cat")
    first = [c for c in svc.calls if c["prompt"] == v2.PROMPT]
    second = [c for c in svc.calls if c["prompt"] == v2.PROMPT_SECOND]
    assert first and not any(c["doc"] for c in first) and not st["whole_document"]
    assert st["not_examined"] == 0 and st["index_filled"] >= 1  # the index fills what keyword screening missed
    assert second and all(c["doc"] and c["cache"] == "document" for c in second)  # absence is only confirmed against the whole document
    assert out["ia-5"]["ia-5_obj.zz"]["second_look"] == "none"


def test_second_look_escalates_only_unexplained_missing(svc):
    out, st = v2.analyze_ai(DOC, uuid.uuid4(), _org(), TODO, TITLES, "cat")
    second = [c for c in svc.calls if c["prompt"] == v2.PROMPT_SECOND]
    assert second and "ac-2_obj.d" not in second[0]["ids"]  # met items never get a second look
    assert out["ac-2"]["ac-2_obj.j"]["second_look"] == "found" and out["ac-2"]["ac-2_obj.j"]["status"] == "partial"
    assert out["ia-5"]["ia-5_obj.zz"]["second_look"] == "none"


def test_index_candidates_mean_needs_review_not_absent(monkeypatch, svc):
    monkeypatch.setattr("app.services.policy_second_look.THRESHOLD", 0.05)
    out, st = v2.analyze_ai(DOC, uuid.uuid4(), _org(), TODO, TITLES, "cat")
    v = out["ac-2"]["ac-2_obj.j"]
    assert v.get("candidates") and st["second_look_candidates"] >= 1
    row = pp.apply_ai(DOC, {"status": "missing", "confidence": "Low", "reason": "", "snippets": []}, v)
    assert row["status"] == "partial" and row["reason"].startswith("Needs manual review") and row["snippets"][0]["candidate"]
    assert 0 <= row["snippets"][0]["score"] <= 1.5 and row["snippets"][0]["location"]


def test_absent_only_after_whole_document_second_look():
    base = {"status": "missing", "confidence": "Low", "reason": "", "snippets": []}
    assert pp.apply_ai(DOC, dict(base), {"status": "missing", "second_look": "none", "rationale": "x"})["status"] == "missing"
    unconfirmed = pp.apply_ai(DOC, dict(base), {"status": "missing", "rationale": "x"})
    assert unconfirmed["status"] == "partial" and unconfirmed["reason"].startswith("Needs manual review")


@pytest.mark.parametrize("text,quote", [
    ("The ISSO shall review \u201caudit logs\u201d weekly.", 'The ISSO shall review "audit logs" weekly.'),          # smart quotes
    ("Access is reviewed \u2013 at least annually \u2014 by the ISSM.", "Access is reviewed - at least annually - by the ISSM."),  # dashes
    ("The ISSO shall\n   review the\tlogs every week.", "The ISSO shall review the logs every week."),               # whitespace / line breaks
    ("1.2 The ISSO shall review the logs every week.", "The ISSO shall review the logs every week."),               # list numbering
    ("\u2022 The ISSO shall review the logs every week.", "The ISSO shall review the logs every week."),             # bullets
    ("The ISSO shall review the authen-\nticator logs weekly.", "The ISSO shall review the authenticator logs weekly."),  # hyphenation
    ("THE ISSO SHALL REVIEW THE LOGS EVERY WEEK.", "The ISSO shall review the logs every week."),                   # case
    ("The ISSO shall re\u00adview the logs\u00a0every week.", "The ISSO shall review the logs every week."),         # soft hyphen + NBSP
])
def test_forgiving_quote_matching(text, quote):
    hit = pp.find_quote(text, quote)
    assert hit is not None and pp.verify_quote(text, quote)
    assert "ISSO" in text[hit[0]:hit[1]] or "ISSM" in text[hit[0]:hit[1]] or "Access" in text[hit[0]:hit[1]]


def test_quote_matching_still_rejects_paraphrase():
    assert not pp.verify_quote("The ISSO shall review the logs every week.", "The ISSM reviews logs monthly.")


def test_openrouter_cache_control_block():
    r = AIRequest(system="s", user="DOC-PREFIX rest", cache_prefix="DOC-PREFIX")
    c = _user_content(r)
    assert c[0]["cache_control"] == {"type": "ephemeral"} and c[0]["text"] == "DOC-PREFIX" and c[1]["text"] == " rest"
    assert _user_content(AIRequest(system="s", user="plain")) == "plain"
