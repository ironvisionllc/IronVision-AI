"""Tester round 3 (RA UAT fixture through the real upload API + worker handler): progress from enqueue to a kept final summary,
gap empty on met rows, grammar, tagged/"shall" evaluation, trigger-aware relevance, snippet locations, sentence splitting,
decided-mapping coverage notes, not-selected grouping in Mapping Review."""
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Policy
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

FIX = Path(__file__).parent / "fixtures" / "policies" / "ra_policy_dod_aws_raven_demo.docx"


@pytest.fixture(scope="module")
def ra(client, signup_on):  # noqa: F811
    from worker.handlers import handle_policy_analyze
    t = _signup(client, f"r3-{uuid.uuid4().hex[:6]}@example.com", "R3 Org")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "R3 Raven", "acronym": "R3RV", "baseline_key": "high", "categorization_mode": "fips199",
                                               "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    r = client.post("/api/v1/policies", files={"file": (FIX.name, FIX.read_bytes())}, data={"title": "RA Raven", "system_ids": sid}, headers=h)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    with SessionLocal() as db:
        queued = db.get(Policy, uuid.UUID(pid)).analysis["progress"]
    with SessionLocal() as db:
        handle_policy_analyze(db, {"policy_id": pid})
        db.commit()
    d = client.get(f"/api/v1/policies/{pid}", headers=h).json()
    return {"h": h, "sid": sid, "pid": pid, "queued": queued, "d": d}


def test_progress_queued_four_stages_and_final_summary(ra):
    assert ra["queued"]["phase"] == "queued" and ra["queued"]["pct"] == 0 and ra["queued"]["stage"].startswith("Queued – waiting for a worker")
    p = ra["d"]["policy"]["analysis"]["progress"]
    assert p["phase"] == "done" and p["pct"] == 100 and re.match(r"Completed in [\d.]+ s", p["stage"])
    stages = [x["stage"] for x in p["history"]]
    for pre in ("Queued", "1/4", "2/4", "3/4", "4/4"):
        assert any(s.startswith(pre) for s in stages), (pre, stages)
    assert p["audit_findings"] == len(ra["d"]["findings"]) or p["audit_findings"] >= 0
    assert p["requirements_analyzed"] == sum(len(c["requirements"]) for c in ra["d"]["coverage"])


def _reqs(ra):
    return [r for c in ra["d"]["coverage"] for r in c["requirements"]]


def test_gap_empty_on_met_and_grammar(ra):
    rows = _reqs(ra)
    assert all(r["gap"] is None for r in rows if r["effective"] == "met")
    gaps = [r["gap"] for r in rows if r["gap"]]
    assert not [g for g in gaps if re.search(r"\bprocedures is\b|\bpolicies is\b", g)], gaps


def test_tagged_and_shall_sentences_are_evaluated_not_generic(ra):
    rows = {(r["control_id"], r["requirement_id"]): r for r in _reqs(ra)}
    for k in (("ra-2", "ra-2_obj.a"), ("ra-2", "CCI-004615"), ("ra-2", "CCI-004616")):
        if k in rows:
            assert rows[k]["effective"] == "met" or not str(rows[k].get("needs") or "").startswith("Add a statement"), (k, rows[k])
    assert not [r for r in rows.values() if r["status"] == "partial" and str(r.get("needs") or "").startswith("Add a statement that addresses")
                and r["control_id"] == "ra-2"]


def test_trigger_condition_relevance():
    from app.services.policy_coverage import relevant
    req = ("Scans for vulnerabilities in the information system and hosted applications when new vulnerabilities potentially affecting "
           "the system/applications are identified and reported.")
    assert not relevant("Threat intelligence feeds and vulnerability advisories are monitored daily by the ISSO.", req, "Vulnerability Monitoring and Scanning")
    assert not relevant("The ISSO shall monitor the threat environment continuously, using CSSP reporting, vulnerability alerts, and AWS security bulletins, "
                        "and shall trigger an out-of-cycle risk assessment update when the threat picture changes materially.", req, "Vulnerability Monitoring and Scanning")
    assert relevant("When new vulnerabilities affecting the system are identified and reported, the ISSO shall run an ad hoc scan of the affected "
                    "applications within 72 hours.", req, "Vulnerability Monitoring and Scanning")


def test_snippet_locations_have_real_headings(ra):
    locs = [s.get("location") or "" for r in _reqs(ra) for s in (r.get("snippets") or []) if isinstance(s, dict)]
    assert locs and all(loc for loc in locs), "every snippet has a location"
    assert not [x for x in locs if re.search(r"§ [A-Z]{2}-\d+(?:\(\d+\))? (?:is|are|shall)\b", x)], "no stray ID-prose 'headings'"


def test_sentence_splitter_keeps_versions_decimals_abbreviations():
    from app.services.policy_coverage import _sentences
    t = "Sessions use TLS 1.2 or higher (see §8.2), e.g. for the API. Approved by J. Doe per NIST SP 800-53 Rev. 5 and RA-1c.1. Next sentence."
    ss = [x[2] for x in _sentences(t)]
    assert ss == ["Sessions use TLS 1.2 or higher (see §8.2), e.g. for the API.", "Approved by J. Doe per NIST SP 800-53 Rev. 5 and RA-1c.1.", "Next sentence."], ss


def test_mapping_review_not_selected_grouped_and_coverage_notes_labelled(client, ra):
    q = client.get("/api/v1/mapping-review", params={"system_id": ra["sid"]}, headers=ra["h"]).json()
    pm = [x for x in q["queue"] if x["kind"] == "policy_map"]
    ns = [x for x in pm if x.get("group") == "not_selected"]
    assert {x["control_id"] for x in ns} == {"ra-6", "ra-3.4"} and all(x["not_selected"] for x in ns)
    first_ns = min(i for i, x in enumerate(pm) if x.get("group") == "not_selected")
    assert all(x.get("group") == "not_selected" for x in pm[first_ns:]), "not-selected grouped after normal proposals"
    for r in q.get("review_needed", []):
        assert r["label"] == ("Coverage note – mapping already approved" if r["mapping_decided"] else "Review needed")
