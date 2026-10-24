"""RMF Accuracy release – Phase 4: side-by-side mapping review (11) and confidence/citation transparency (12)."""
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent, Policy
from app.services import mapping_sbs
from app.services import policy_mapping as pm
from tests.conftest import auth
from tests.test_policy_auditor_v2 import _upload
from tests.test_sandbox import _signup, signup_on  # noqa: F401

LINES = ["1 Purpose", "This policy establishes the access control policy for the organization.",
         "2 Requirements", "AC-2 Account Management: the ISSO shall review accounts every 30 days and must disable inactive accounts.",
         "AC-7 is referenced for information only.", "3 Audit", "Audit Events are reviewed by the security team."]


@pytest.fixture(scope="module")
def pol(client, signup_on):  # noqa: F811
    t = _signup(client, f"p4-{uuid.uuid4().hex[:6]}@example.com", "P4 Org")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "P4 System", "acronym": f"P4{uuid.uuid4().hex[:3]}", "baseline_key": "moderate",
                                                "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    pid = _upload(client, h, sid, LINES, "P4 Access Policy")
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])  # noqa: E731
    return {"h": h, "sid": sid, "pid": pid, "role": role}


def _detail(client, pol):
    return {m["control_id"]: m for m in client.get(f"/api/v1/policies/{pol['pid']}", headers=pol["h"]).json()["control_mappings"]}


def test_every_mapping_has_excerpt_or_explicit_no_text_and_evidence_confidence(client, pol):
    maps = _detail(client, pol)
    assert {"ac-2", "ac-7"} <= set(maps)
    for m in maps.values():
        assert m["excerpts"] or m["no_supporting_text"], m["control_id"]
        for e in m["excerpts"]:
            assert e["exact"] and e["text"] in "\n".join(LINES) or e["exact"]
    assert maps["ac-2"]["evidence_confidence"] == "High" and maps["ac-2"]["evidence_kind"] == "direct"
    assert maps["ac-7"]["evidence_confidence"] == "Medium", "explicit ID without requirement language"
    low = [m for m in maps.values() if "title_language" in m["source"] and "explicit_id" not in m["source"]]
    assert all(m["evidence_confidence"] == "Low" and m["evidence_kind"] == "inferred" for m in low)
    with SessionLocal() as db:  # manual mapping with no supporting text is no longer "High"
        p = db.get(Policy, uuid.UUID(pol["pid"]))
        m = pm.decide(db, p, "sc-8", "mapped", type("A", (), {"id": None, "email": "t@example.com"})(), "manual")
        db.commit()
        assert m.confidence == "Low" and not m.snippets
    sc8 = _detail(client, pol)["sc-8"]
    assert sc8["no_supporting_text"] and sc8["evidence_confidence"] == "Requires manual review"


def test_side_by_side_payload_and_server_side_excerpt_verification(client, pol):
    r = client.get(f"/api/v1/policies/{pol['pid']}/mappings/ac-2/review", headers=pol["h"]).json()
    c = r["control"]
    assert c["title"] == "Account Management" and c["statement"] and c["odps"] and any(q["type"] == "cci" for q in c["requirements"]) and c["enhancements"]
    assert "guidance" in c and r["policy"]["title"] == "P4 Access Policy"
    ex = r["mapping"]["excerpts"][0]
    assert ex["exact"] and ex["section"] and ex["context_before"] is not None and set(r["legend"]) >= {"High", "Medium", "Low"}
    assert r["coverage"]["outcome"] in ("Fully Addressed", "Partially Addressed", "Not Addressed", "Requires Manual Review")
    assert any(g["type"] == "Organizational decision required" for g in r["gaps"]) and any(g["text"].startswith("Recommendation") for g in r["gaps"])
    with SessionLocal() as db:  # a fabricated excerpt is not shown as evidence
        m = next(x for x in pm.current(db, uuid.UUID(pol["pid"])) if x.control_id == "ac-7")
        m.snippets = (m.snippets or []) + ["This sentence is not in the policy."]
        db.commit()
    r7 = client.get(f"/api/v1/policies/{pol['pid']}/mappings/ac-7/review", headers=pol["h"]).json()
    assert "This sentence is not in the policy." in r7["mapping"]["unverified_excerpts"] and any(g["type"] == "Unsupported claim" for g in r7["gaps"])


def test_decisions_persist_audited_and_approved_mappings_protected(client, pol):
    isso, lead = pol["role"]("isso"), pol["role"]("leadership_viewer")
    url = lambda c: f"/api/v1/policies/{pol['pid']}/mappings/{c}/decision"  # noqa: E731
    assert client.post(url("ac-2"), json={"action": "accept"}, headers=lead).status_code == 403
    assert client.post(url("ac-7"), json={"action": "reject", "comment": "short"}, headers=isso).status_code == 422
    ok = client.post(url("ac-2"), json={"action": "accept", "comment": "Policy clearly addresses AC-2"}, headers=isso).json()
    assert ok["mapping"]["status"] == "mapped" and ok["mapping"]["comments"][-1]["action"] == "accept"
    assert client.post(url("ac-2"), json={"action": "override_coverage", "coverage_outcome": "Fully Addressed", "comment": "x"}, headers=isso).status_code == 422
    ov = client.post(url("ac-2"), json={"action": "override_coverage", "coverage_outcome": "Partially Addressed", "comment": "Frequency only, no procedure"}, headers=isso).json()
    assert ov["coverage"]["overridden"] and ov["coverage"]["outcome"] == "Partially Addressed"
    fl = client.post(url("ac-7"), json={"action": "flag", "comment": "Check context"}, headers=isso).json()
    assert fl["mapping"]["review_flag"]
    with SessionLocal() as db:  # reanalysis with different evidence must not overwrite the approved mapping
        m = next(x for x in pm.current(db, uuid.UUID(pol["pid"])) if x.control_id == "ac-2")
        m.snippets = ["AC-2 Account Management: the ISSO shall review accounts every 30 days and must disable inactive accounts."][:1] + ["old"]
        db.commit()
    ra = client.post(url("ac-2"), json={"action": "reanalyze", "comment": ""}, headers=isso).json()
    assert ra["mapping"]["status"] == "mapped" and ra["mapping"]["reanalysis"]["label"] == "differs from approved"
    ed = client.post(url("ac-7"), json={"action": "edit", "edit_control_id": "AC-7(1)", "comment": "The enhancement is meant"}, headers=isso).json()
    assert ed["mapping"]["status"] == "mapped" and ed["control"]["control_id"] == "ac-7.1"
    assert _detail(client, pol)["ac-7"]["status"] == "rejected"
    with SessionLocal() as db:
        acts = {e.action for e in db.scalars(select(AuditEvent).where(AuditEvent.entity_id == pol["pid"], AuditEvent.action.like("policy_mapping.%")))}
        assert {"policy_mapping.accept", "policy_mapping.override_coverage", "policy_mapping.flag", "policy_mapping.reanalyze", "policy_mapping.edit"} <= acts
    assert mapping_sbs.LEGEND["High"].startswith("Explicit control ID")
