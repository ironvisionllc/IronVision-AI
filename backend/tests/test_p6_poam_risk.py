"""P6: POA&M eMASS risk fields are separate from technical severity/CAT (no automatic conversion), validated on the eMASS scale, audited,
defaultable from the control's Risk Assessment without overwriting manual values; eMASS POA&M import keeps Raw Severity on the eMASS scale."""
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent, ControlAssignment, EmassControlFields, Poam
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401


@pytest.fixture(scope="module")
def ctx(client, signup_on):  # noqa: F811
    t = _signup(client, f"p6-{uuid.uuid4().hex[:6]}@example.com", "P6 Org")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "Risk System", "acronym": f"RK{uuid.uuid4().hex[:3]}", "baseline_key": "low",
                                                "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    isso = auth(client.post("/api/v1/sandbox/act-as", json={"role": "isso"}, headers=h).json()["access_token"])
    sca = auth(client.post("/api/v1/sandbox/act-as", json={"role": "sca"}, headers=h).json()["access_token"])
    pid = client.post("/api/v1/poams", json={"system_id": sid, "weakness": "SYNTHETIC weak password policy", "control_ids": ["ac-2"], "severity": "high",
                                            "cat": "CAT I"}, headers=isso).json()["id"]
    with SessionLocal() as db:
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(sid), ControlAssignment.control_id == "ac-2"))
        db.add(EmassControlFields(system_id=a.system_id, assignment_id=a.id, control_id="ac-2", severity="Moderate", relevance_of_threat="High",
                                  likelihood="Moderate", impact="High", residual_risk_level="Moderate", mitigations="SYNTHETIC MFA enforced"))
        db.commit()
    return {"sid": sid, "isso": isso, "sca": sca, "pid": pid}


def test_technical_and_emass_scales_are_separate(client, ctx):
    r = client.get(f"/api/v1/poams/{ctx['pid']}/risk", headers=ctx["isso"]).json()
    assert r["technical"]["severity"] == "high" and r["technical"]["cat"] == "CAT I"
    assert all(v is None for v in r["emass"].values())  # no automatic conversion from technical severity


def test_patch_validates_scale_and_marks_manual(client, ctx):
    assert client.patch(f"/api/v1/poams/{ctx['pid']}", json={"likelihood": "critical"}, headers=ctx["isso"]).status_code == 422
    r = client.patch(f"/api/v1/poams/{ctx['pid']}", json={"likelihood": "Low", "comments": "SYNTHETIC note"}, headers=ctx["isso"])
    assert r.status_code == 200
    v = client.get(f"/api/v1/poams/{ctx['pid']}/risk", headers=ctx["isso"]).json()
    assert v["emass"]["likelihood"] == "Low" and v["source"]["likelihood"] == "manual" and v["technical"]["severity"] == "high"


def test_default_from_control_keeps_manual_and_audits(client, ctx):
    r = client.post(f"/api/v1/poams/{ctx['pid']}/risk/from-control", json={"control_id": "ac-2"}, headers=ctx["isso"]).json()
    assert "likelihood" not in r["applied"] and r["applied"]["raw_severity"] == "Moderate" and r["applied"]["residual_risk_level"] == "Moderate"
    v = client.get(f"/api/v1/poams/{ctx['pid']}/risk", headers=ctx["isso"]).json()
    assert v["emass"]["likelihood"] == "Low" and v["source"]["raw_severity"] == "control:ac-2"
    with SessionLocal() as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "poam.risk_from_control", AuditEvent.entity_id == ctx["pid"])) is not None
        assert db.get(Poam, uuid.UUID(ctx["pid"])).severity == "high"


def test_rbac_sca_cannot_edit_risk(client, ctx):
    assert client.patch(f"/api/v1/poams/{ctx['pid']}", json={"impact": "Low"}, headers=ctx["sca"]).status_code == 403
    assert client.post(f"/api/v1/poams/{ctx['pid']}/risk/from-control", json={"control_id": "ac-2"}, headers=ctx["sca"]).status_code == 403


def test_import_raw_severity_not_converted():
    from app.services.emass_reports import CATS, RAW
    assert RAW["veryhigh"] == "Very High" and CATS["cati"] == "CAT I" and "critical" not in RAW.values()


def test_poam_updated_audit_has_changed_fields_before_after(client, ctx):
    assert client.patch(f"/api/v1/poams/{ctx['pid']}", json={"impact": "Moderate", "mitigations": "SYNTHETIC v2"}, headers=ctx["isso"]).status_code == 200
    ev = [e for e in client.get("/api/v1/audit-events?action=poam.updated&limit=20", headers=ctx["isso"]).json() if e["entity_id"] == ctx["pid"]][0]
    assert ev["details"]["changed_fields"] == ["impact", "mitigations"]
    assert ev["after"] == {"impact": "Moderate", "mitigations": "SYNTHETIC v2"} and "impact" in ev["before"] and ev["before"]["impact"] != "Moderate"
