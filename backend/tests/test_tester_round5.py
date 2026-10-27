"""Tester round 5: gap / fix text QUOTES the authoritative requirement (no clause rewriting); ODP placeholders rendered, never leaked;
AI-suggested language only after the fluency gate. Swept over every CCI and objective of RA, AC, SC, AU, CM and IR."""
import re

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Control
from app.services import policy_coverage as pc
from app.services import policy_profile as pp
from app.services.content.loader import active_catalog_id

FAMILIES = ("ra", "ac", "sc", "au", "cm", "ir")
LEAK = re.compile(r"\[Assignment|\[Selection|_ODP|\{\{")
VERB = re.compile(r"\b(?:is|are|does|do|has|have|add|confirm|meets?|states?|may|needed|defined|suggests)\b", re.I)


def _outside_quotes(s: str) -> str:
    return re.sub(r"“[^”]*”", "“…”", s)


def _problems(s: str) -> list[str]:
    out = []
    if LEAK.search(s):
        out.append("placeholder leaked")
    if re.search(r"\b(?:using|within|per) (?:means|time period)\b|\(\s*\)|\[\s*\]", s):
        out.append("empty value")
    syn = _outside_quotes(s)
    if re.search(r"\b(\w+) \1\b", syn, re.I):
        out.append("doubled word")
    if any(not m.group(1).lower().startswith(pp.VOWEL_OK) for m in re.finditer(r"\ba ([aeiou]\w*)", syn, re.I)):
        out.append("a before vowel")
    if re.search(r"\bwill (?:for|the|a|an|in|on|of|with|by|at|from|to)\b", syn, re.I):
        out.append("will <non-verb>")
    for sent in [x for x in re.split(r"(?<=[.])\s+", syn) if x.strip() and x.strip() not in ("“…”", "“…”.")]:
        if not VERB.search(sent) and not sent.startswith(("Requirement (", "Fix:", "“")):
            out.append(f"no finite verb: {sent[:60]}")
    return out


@pytest.fixture(scope="module")
def catalog():
    with SessionLocal() as db:
        cat = active_catalog_id(db)
        ids = sorted(db.scalars(select(Control.control_id).where(Control.catalog_version_id == cat)))
        ids = [c for c in ids if c.split("-")[0] in FAMILIES]
        return [(cid, r) for cid in ids for r in pc.requirements(db, cid)]


def test_every_requirement_in_six_families_renders_clean(catalog):
    checked = {"cci": 0, "objective": 0}
    bad = []
    for cid, req in catalog:
        for status, where in (("missing", "quoted policy text"), ("partial", "quoted policy text"), ("partial", "tagged section")):
            t = pp.fix_text(req, status, where, cid, [("time_period", "15 minutes")] if cid == "ac-7" else None)
            p = _problems(t)
            if p:
                bad.append((cid, req["id"], p, t[:200]))
        checked[req["type"]] = checked.get(req["type"], 0) + 1
    print(f"\nround-5 sweep: {checked['cci']} CCIs + {checked['objective']} objectives in {', '.join(f.upper() for f in FAMILIES)}; "
          f"{3 * (checked['cci'] + checked['objective'])} gap/fix texts checked")
    assert checked["cci"] > 300 and checked["objective"] > 300
    from collections import Counter
    assert not bad, (Counter(x for b in bad for x in b[2]).most_common(8), bad[:3])


def test_tester_examples_are_quoted_not_rewritten():
    t = pp.fix_text({"type": "objective", "id": "ac-7_obj.b", "label": "AC-07b.", "text": "automatically [Selection (one or more): lock the account or node for "
                     "[Assignment: time period] ; lock the account or node until released by an administrator] when the maximum number of unsuccessful attempts is exceeded."},
                    "missing", control_id="ac-7")
    assert "[organization-defined time period]" in t and "[organization-selected (one or more):" in t and not LEAK.search(t)
    assert t.startswith("The policy does not clearly address this requirement. Requirement (NIST SP 800-53A Rev 5 assessment objective AC-07b): “")
    assert "including the organization-defined value(s): organization-defined time period; the selected option(s)." in t
    t = pp.fix_text({"type": "objective", "id": "ra-3.3_obj", "label": "RA-03(03)", "text": "the current cyber threat environment is determined on an ongoing basis using [Assignment: means]."}, "partial")
    assert "using [organization-defined means]" in t and "using means." not in t
    t = pp.fix_text({"type": "cci", "id": "CCI-001384", "text": "For publicly accessible systems, display system use information with organization-defined conditions before granting further access."}, "missing", control_id="ac-8")
    assert "will for" not in t and "“For publicly accessible systems, display system use information" in t and "organization-defined conditions" in t
    assert "Requirement (DISA CCI-001384, NIST SP 800-53 Rev 5 AC-8)" in t


def test_odp_values_from_the_system_are_labelled():
    t = pp.fix_text({"type": "cci", "id": "CCI-000044", "text": "Enforce the organization-defined limit of consecutive invalid logon attempts."}, "missing",
                    control_id="ac-7", odp=[("unsuccessful_logon_attempts", "3 attempts")])
    assert "unsuccessful logon attempts = 3 attempts (organization-defined: 3 attempts)" in t


def test_ai_suggestion_only_after_fluency_gate():
    req = {"type": "cci", "id": "CCI-002238", "text": "Automatically lock the account or node for an organization-defined time period."}
    good = "The system shall automatically lock the account for [organization-defined time period] after three consecutive invalid logon attempts."
    assert "The AI suggests this language (validated): “" + good in pp.fix_text(req, "missing", suggestion=good)
    for broken in ("the system will use notification states that unauthorized use is prohibited.",  # lowercase start
                   "The organization will for publicly accessible systems, display system use information.",
                   "Accounts shall be locked for [Assignment: time period].", "Threats are determined on an ongoing basis using means.",
                   "The organization shall conduct a impact-level categorization.", "The the system shall lock accounts.",
                   "Lock accounts quickly and also everywhere."):
        assert not pp.fluent(broken), broken
        assert "The AI suggests" not in pp.fix_text(req, "missing", suggestion=broken)


def test_policy_only_evidence_caps_at_partially_implemented():
    import inspect
    src = inspect.getsource(pc.policy_view)
    assert 'target = "implemented" if not policy_gap and has_ev else "partially_implemented"' in src  # Implemented needs technical evidence
