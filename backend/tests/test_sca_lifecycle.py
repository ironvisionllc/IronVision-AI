"""P1.3 SCA lifecycle with real personas: ISSO approves implementation → item "Awaiting assessor (SCA)"; ISSO/System Owner cannot confirm
Satisfied; the SCA (no finding.map) can see and decide only awaiting items; assessment ≠ implementation approval; audit; who acts next."""
import uuid

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import AuditEvent, ControlAssignment, Finding, FindingControlMap, System, User
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401


@pytest.fixture(scope="module")
def ws(client, signup_on):  # noqa: F811
    t = _signup(client, f"sca-{uuid.uuid4().hex[:6]}@example.com", "SCA Org")
    h = auth(t["access_token"])
    assert client.post("/api/v1/sandbox/demo-data", headers=h).status_code == 200
    with SessionLocal() as db:
        org = db.scalar(select(User.org_id).where(User.email == t["user"]["email"]))
        sid = str(db.scalar(select(System.id).join(Finding, Finding.system_id == System.id).join(FindingControlMap, FindingControlMap.finding_id == Finding.id)
                            .where(System.org_id == org).group_by(System.id).order_by(func.count().desc()).limit(1)))
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])  # noqa: E731
    return {"sid": sid, "isso": role("isso"), "so": role("system_owner"), "sca": role("sca"), "issm": role("issm")}


def _q(client, ws, who="isso"):
    return client.get("/api/v1/mapping-review", params={"system_id": ws["sid"]}, headers=ws[who]).json()["queue"]


def _dec(client, ws, who, items, action="approve", just="SYNTHETIC evidence reviewed"):
    return client.post("/api/v1/mapping-review/decide", json={"system_id": ws["sid"], "action": action, "justification": just, "items": [
        {"kind": i["kind"], "key": i["key"], "ids": i["ids"], "control_id": i["control_id"], "evidence_fp": i.get("evidence_fp")} for i in items]}, headers=ws[who])


def test_full_sca_lifecycle_with_personas(client, ws):
    st = [i for i in _q(client, ws) if i["kind"] == "status" and not i["awaiting_sca"]][:1]
    if not st:
        pytest.skip("no evidence-based status suggestion in the demo system")
    cid = st[0]["control_id"]
    assert st[0]["next_actor"].startswith("ISSO")
    # SCA cannot approve the implementation (not awaiting yet) – separation of duties, with the reason
    r = _dec(client, ws, "sca", st)
    assert r.status_code == 403 and "Awaiting assessor (SCA)" in r.json()["detail"]["message"]
    # ISSO approves the implementation → awaiting SCA
    assert _dec(client, ws, "isso", st).json()["partial"] == [cid]
    w = next(i for i in _q(client, ws) if i["control_id"] == cid and i["kind"] == "status")
    assert w["awaiting_sca"] and w["next_actor"].startswith("SCA")
    # ISSO and System Owner cannot confirm Satisfied
    r = _dec(client, ws, "isso", [w])
    assert r.status_code == 403 and "waiting for the SCA" in r.json()["detail"]["message"]
    assert _dec(client, ws, "so", [w]).status_code == 403
    # the SCA sees it and confirms → assessment Satisfied, implementation unchanged; item leaves the queue
    assert any(i["control_id"] == cid and i["awaiting_sca"] for i in _q(client, ws, "sca"))
    r = _dec(client, ws, "sca", [w], just="SYNTHETIC: assessed – examined evidence, satisfied")
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(ws["sid"]), ControlAssignment.control_id == cid))
        assert (a.implementation_status, a.assessment_status) == ("implemented", "satisfied")
        ev = db.scalars(select(AuditEvent.action).where(AuditEvent.entity_id == str(a.id), AuditEvent.action == "control.status_suggestion_approved")).all()
        assert len(ev) == 2, "implementation approval and assessment confirmation are two audited decisions"
        from app.models import Assessment
        asm = db.scalar(select(Assessment).where(Assessment.assignment_id == a.id))
        assert asm is not None and asm.result == "satisfied"  # the SCA confirmation feeds the SAR
    assert not [i for i in _q(client, ws) if i["control_id"] == cid and i["kind"] == "status"]


def test_sca_cannot_decide_mappings(client, ws):
    m = [i for i in _q(client, ws) if i["kind"] in ("finding_map", "policy_map")][:1]
    if not m:
        pytest.skip("no mapping item")
    r = _dec(client, ws, "sca", m)
    assert r.status_code == 403 and r.json()["detail"]["code"] == "separation_of_duties"
