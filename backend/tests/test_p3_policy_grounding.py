"""P3: deterministic policy findings are grounded and readable (requirement text, verbatim sentence or 'Not found', corrective language,
explicit manual review) – never a keyword list; an RA policy is not flagged for a missing AC-17 remote-access section; hyphenated
'remote-access' satisfies the AC-17 section check."""
import re

from app.services.policy_coverage import evaluate
from app.services.rmf import rule_extract

REQ = "Employ vulnerability monitoring tools and techniques that facilitate interoperability among tools and automate parts of the vulnerability management process."


def test_fallback_is_grounded_not_keyword_salad():
    text = "1. Purpose. This SYNTHETIC policy covers scanning.\nThe organization employs vulnerability monitoring tools that facilitate interoperability among tools and automate the vulnerability management process."
    r = evaluate(text, "generic", "policy", None, "Risk Assessment", REQ)
    assert r["status"] == "partial" and r["confidence"] == "Low"
    assert "Manual review needed" in r["reason"] and "Requirement: “Employ vulnerability monitoring" in r["reason"]
    assert r["snippets"] and r["snippets"][0]["text"] in text  # verbatim excerpt
    assert "%" not in r["reason"] and "key words" not in r["reason"]
    assert r["needs"].startswith("Manual review needed: the quoted sentence may address this requirement")  # round 5: requirement quoted verbatim
    assert "Requirement: “Employ vulnerability monitoring tools" in r["needs"] and "Fix: confirm that the quoted sentence meets it" in r["needs"]


def test_fallback_not_found_has_corrective_language():
    r = evaluate("1. Purpose. SYNTHETIC unrelated text about badges.", "generic", "policy", None, "Risk Assessment", REQ)
    assert r["status"] == "missing" and r["reason"].startswith("Not found:") and not r["snippets"]
    assert r["needs"].startswith("The policy does not clearly address this requirement. Requirement: “Employ vulnerability monitoring")  # round 5
    assert "Fix: Add policy language that states how the organization meets this requirement" in r["needs"]
    assert not re.search(r"\b\w+, \w+, \w+, \w+\b", r["reason"].split("“")[0])  # no bare word lists before the quoted requirement


def test_ra_policy_never_flagged_for_remote_access():
    out = rule_extract("SYNTHETIC Risk Assessment Policy. Official: the ISSM is the named official.", families={"ra"}, top_policy_control="ra-1")
    assert not [m for m in out["missing_sections"] if m["control_id"] == "ac-17"]


def test_hyphenated_remote_access_satisfies_ac17():
    out = rule_extract("SYNTHETIC Access Control Policy. Remote-access sessions require MFA. The ISSM is the named official.", families={"ac"})
    assert not [m for m in out["missing_sections"] if m["control_id"] == "ac-17"]
    out = rule_extract("SYNTHETIC Access Control Policy. Accounts are reviewed. The ISSM is the named official.", families={"ac"})
    assert [m for m in out["missing_sections"] if m["control_id"] == "ac-17"]
