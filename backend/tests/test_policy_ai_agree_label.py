from app.services import policy_profile as pp

TEXT = "The risk assessment policy is reviewed by the ISSM. Reviews follow significant system changes."


def _row():
    return {"status": "partial", "confidence": "Low", "reason": "checklist", "snippets": [{"text": "Reviews follow significant system changes."}]}


def test_ai_partial_agreeing_with_checklist_is_an_ai_verdict():
    r = pp.apply_ai(TEXT, _row(), {"status": "partial", "quote": "The risk assessment policy is reviewed by the ISSM.", "rationale": "no frequency"})
    assert r["basis"] == "ai" and r["status"] == "partial" and "agree" in r["reason"]
    assert r["snippets"][0]["text"].startswith("The risk assessment policy")


def test_ai_partial_with_bad_quote_keeps_checklist_passage():
    r = pp.apply_ai(TEXT, _row(), {"status": "partial", "quote": "invented words", "rationale": "x"})
    assert r["basis"] == "ai" and r["snippets"][0]["text"].startswith("Reviews follow") and "not matched" in r["reason"]
