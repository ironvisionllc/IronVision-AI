"""RMF Accuracy release – Phase 2: categorization (2), PTA (4), overlays (6), privacy overlay vs 800-53B privacy baseline (7), SRG IL (9)."""
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent, CategorizationRecord, System
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

SYS = {"baseline_key": "moderate", "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}


@pytest.fixture(scope="module")
def org(client, signup_on):  # noqa: F811
    t = _signup(client, f"p2-{uuid.uuid4().hex[:6]}@example.com", "P2 Org")
    h = auth(t["access_token"])
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])  # noqa: E731
    mk = lambda name: client.post("/api/v1/systems", json={"name": name, "acronym": f"P2{uuid.uuid4().hex[:3]}", **SYS}, headers=h).json()["id"]  # noqa: E731
    return {"h": h, "role": role, "mk": mk}


def _cat(client, sid, h, **kw):
    body = {"mode": "fips199", "information_types": [{"id": "D.16.3"}], **kw}
    return client.put(f"/api/v1/systems/{sid}/categorization", json=body, headers=h)


def test_fips_high_water_mark_and_cnssi_kept_separate(client, org):
    fips = client.post("/api/v1/reference/categorize", json={"mode": "fips199", "information_types": [{"id": "D.16.3", "c": "Low", "i": "High", "a": "Low", "rationale": "integrity is critical here"}]}, headers=org["h"]).json()
    assert fips["overall"] == "High" and fips["baseline"] == "high"
    cn = client.post("/api/v1/reference/categorize", json={"mode": "cnssi1253", "information_types": [{"id": "D.16.3"}], "cia": {"c": "Moderate", "i": "High", "a": "Low"}}, headers=org["h"]).json()
    assert cn["overall"] is None and (cn["c"], cn["i"], cn["a"]) == ("Moderate", "High", "Low")
    assert "CNSSI 1253 Appendix D" in cn["baseline_selection"] and "SME review required" not in cn["baseline_selection"] and any("M-H-L" in s for s in cn["steps"])
    ref = client.get("/api/v1/reference/frameworks", headers=org["h"]).json()
    assert "3552" in ref["nss_help"] and "800-59" in ref["nss_help"] and ref["nss_answers"] == ["yes", "no", "unsure"]


def test_categorization_approval_and_reapproval(client, org):
    sid = org["mk"]("Cat System")
    isso, ao = org["role"]("isso"), org["role"]("ao")
    assert _cat(client, sid, isso, nss_determination="no", rationale="Initial categorization from the 800-60 types").status_code == 200
    recs = client.get(f"/api/v1/systems/{sid}/categorization/records", headers=isso).json()
    cur = recs["current"]
    assert cur["status"] == "draft" and cur["framework"] == "fips199" and cur["nss_determination"] == "no"
    url = f"/api/v1/systems/{sid}/categorization/records/{cur['id']}/approve"
    assert client.post(url, json={"rationale": "Approved by the ISSO?"}, headers=isso).status_code == 403
    ok = client.post(url, json={"rationale": "Categorization reviewed and approved"}, headers=ao)
    assert ok.status_code == 200 and ok.json()["status"] == "approved" and ok.json()["approved_by"]
    approved_c = client.get(f"/api/v1/systems/{sid}/categorization", headers=isso).json()["confidentiality_impact"]
    ch = _cat(client, sid, isso, information_types=[{"id": "D.16.3", "c": "High", "i": "High", "a": "High", "rationale": "mission change raises impact"}])
    assert ch.status_code == 200 and ch.json()["calculation"]["record_status"] == "pending_reapproval"
    assert client.get(f"/api/v1/systems/{sid}/categorization", headers=isso).json()["confidentiality_impact"] == approved_c, "approved values not overwritten"
    recs = client.get(f"/api/v1/systems/{sid}/categorization/records", headers=isso).json()
    assert recs["approved"]["revision"] == cur["revision"] and recs["current"]["status"] == "pending_reapproval" and len(recs["history"]) >= 2
    client.post(f"/api/v1/systems/{sid}/categorization/records/{recs['current']['id']}/approve", json={"rationale": "Re-approved after the change"}, headers=ao)
    assert client.get(f"/api/v1/systems/{sid}/categorization", headers=isso).json()["confidentiality_impact"] == "High"
    with SessionLocal() as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "categorization.approved", AuditEvent.entity_id == sid))


def test_legacy_categorizations_migrated_and_new_systems_get_revision_1(client, org):
    # legacy copy by migration 0024 is verified by the up/down run on a 0023 database copy (scripts/verify_migration_0024.sh)
    sid = org["mk"]("New Rev System")
    cur = client.get(f"/api/v1/systems/{sid}/categorization/records", headers=org["h"]).json()["current"]
    assert cur["revision"] == 1 and cur["status"] == "draft"


def test_pta_questionnaire_retired_history_read_only(client, org):
    sid = org["mk"]("PTA System")
    isso, priv = org["role"]("isso"), org["role"]("privacy_official")
    g = client.get(f"/api/v1/systems/{sid}/pta", headers=isso)
    assert g.status_code == 200, "existing PTA records stay readable"
    r = client.post(f"/api/v1/systems/{sid}/pta", json={"answers": {"pii": {"answer": "no", "explanation": "no personal data"}}}, headers=isso)
    assert r.status_code == 410 and "Yes/No" in r.json()["detail"]
    rv = client.post(f"/api/v1/systems/{sid}/pta/{uuid.uuid4()}/review", json={"decision": "approve", "rationale": "PII confirmed; PIA later"}, headers=priv)
    assert rv.status_code == 410


def test_overlays_framework_rules_and_classified_needs_explicit_answer(client, org):
    sid = org["mk"]("Overlay Rules")
    isso = org["role"]("isso")
    g = {x["group"]: x for x in client.get(f"/api/v1/systems/{sid}/select", headers=isso).json()["overlay_groups"]}
    assert not g["privacy"]["available"] and "SP 800-53B privacy baseline" in g["privacy"]["unavailable_reason"]
    assert not g["classified"]["available"] and g["privacy"]["meta"]["source_document"].startswith("CNSSI 1253F Attachment 6")
    ov = lambda k: client.post(f"/api/v1/systems/{sid}/select/overlay", json={"overlay_key": k, "apply": True}, headers=isso)  # noqa: E731
    assert ov("cnssi-privacy-low").status_code == 422 and ov("cnssi-classified").status_code == 422
    _cat(client, sid, isso, mode="cnssi1253", nss_determination="yes", classified_information="unknown")
    assert ov("cnssi-classified").status_code == 422, "classification level alone never applies it"
    _cat(client, sid, isso, mode="cnssi1253", classified_information="yes")
    assert ov("cnssi-classified").status_code == 200
    _cat(client, sid, isso, mode="fips199", classified_information="no")
    flags = client.get(f"/api/v1/systems/{sid}/select", headers=isso).json()["review_flags"]
    assert any(f["value"] == "cnssi-classified" and "Applicability review needed" in f["message"] for f in flags), "existing selection kept + flagged"
    a = client.post("/api/v1/agency-overlays", json={"name": "Agency X overlay", "issuing_authority": "Agency X CIO", "source_document": "AX-OVL-1",
                                                     "framework": "fips199", "version": "1.0", "applicability": "All Agency X cloud systems"}, headers=org["role"]("platform_admin"))
    assert a.status_code == 201 and client.get("/api/v1/agency-overlays", headers=isso).json()[0]["agency_defined"]
    assert client.post("/api/v1/agency-overlays", json={"name": "x", "issuing_authority": "y", "source_document": "z", "framework": "fips199", "version": "1",
                                                        "applicability": "everything"}, headers=isso).status_code == 403


def test_srg_impact_levels(client, org):
    sid = org["mk"]("IL System")
    isso = org["role"]("isso")
    r = _cat(client, sid, isso, operating_environment="on_prem_gov", environment_detail={"impact_level": "IL4"})
    assert r.status_code == 422 and "cloud service offerings" in r.json()["detail"]
    assert client.get(f"/api/v1/systems/{sid}/categorization/records", headers=isso).json()["il_options"] == []
    r = _cat(client, sid, isso, operating_environment="cloud_iaas", environment_detail={"impact_level": "IL6"})
    assert r.status_code == 422 and "SECRET" in r.json()["detail"]
    assert _cat(client, sid, isso, operating_environment="cloud_iaas", environment_detail={"impact_level": "IL5"}).status_code == 200
    il = {o["value"]: o for o in client.get(f"/api/v1/systems/{sid}/categorization/records", headers=isso).json()["il_options"]}
    assert il["IL5"]["available"] and not il["IL6"]["available"] and il["IL6"]["reason"]
    ok = _cat(client, sid, isso, mode="cnssi1253", classified_information="yes", operating_environment="cloud_iaas", environment_detail={"impact_level": "IL6"})
    assert ok.status_code == 200, ok.text
    with SessionLocal() as db:  # legacy inconsistent value kept and flagged
        s = db.get(System, uuid.UUID(sid))
        s.operating_environment = "on_prem_gov"
        db.commit()
    flags = client.get(f"/api/v1/systems/{sid}/categorization/records", headers=isso).json()["review_flags"]
    assert any(f["field"] == "impact_level" and "Review applicability" in f["message"] for f in flags)
