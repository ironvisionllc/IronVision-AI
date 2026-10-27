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


def test_sca_reject_records_assessment_with_reason_and_evidence(client, ws):
    from app.models import Assessment
    st = [i for i in _q(client, ws) if i["kind"] == "status" and not i["awaiting_sca"]][:1]
    if not st:
        pytest.skip("no evidence-based status suggestion left in the demo system")
    cid, cited = st[0]["control_id"], sorted(e["id"] for e in st[0]["evidence"])
    assert _dec(client, ws, "isso", st).status_code == 200
    w = next(i for i in _q(client, ws, "sca") if i["control_id"] == cid and i["awaiting_sca"])
    r = _dec(client, ws, "sca", [w], action="reject", just="SYNTHETIC: screenshot does not show the lock timeout")
    assert r.status_code == 200 and r.json()["rejected"] == 1
    lst = client.get(f"/api/v1/systems/{ws['sid']}/controls/{cid}/assessments", headers=ws["sca"]).json()
    assert lst and lst[0]["result"] == "other_than_satisfied" and "lock timeout" in lst[0]["findings_text"]
    assert sorted(lst[0]["evidence_ids"]) == cited  # the evidence the queue item cited
    with SessionLocal() as db:
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(ws["sid"]), ControlAssignment.control_id == cid))
        assert a.assessment_status == "other_than_satisfied"
        assert db.scalar(select(func.count()).select_from(Assessment).where(Assessment.assignment_id == a.id)) == 1


def test_sca_approve_carries_cited_evidence(client, ws):
    from app.models import Assessment
    with SessionLocal() as db:
        rows = db.scalars(select(Assessment).where(Assessment.system_id == uuid.UUID(ws["sid"]), Assessment.result == "satisfied")).all()
    assert rows and all(r.evidence_ids for r in rows) and "(0 evidence" not in rows[0].findings_text


def test_bulk_isso_then_bulk_sca_approve_and_reject(client, ws):
    """Item 7: bulk path – ISSO bulk-approves status suggestions → Awaiting assessor; SCA bulk-approves some, bulk-rejects others."""
    from app.models import Assessment, Job
    from app.services import review_bulk as rb

    def run(jid, who=None):  # same handler the worker's interactive lane runs (tests use their own DB, no worker)
        with SessionLocal() as db:
            job = db.get(Job, uuid.UUID(jid))
            res = rb.run(db, job.payload)
            job.status, job.result = "succeeded", res
            db.commit()
        return res
    st = [i for i in _q(client, ws) if i["kind"] == "status" and not i["awaiting_sca"]]
    if len(st) < 2:
        pytest.skip("need ≥2 status suggestions")
    j = client.post("/api/v1/mapping-review/bulk-jobs", json={"system_id": ws["sid"], "action": "approve", "kind": "status",
                                                              "justification": "SYNTHETIC bulk", "idempotency_key": uuid.uuid4().hex}, headers=ws["isso"])
    assert j.status_code in (200, 201, 202), j.text
    res = run(j.json()["id"])
    assert res["succeeded"] == j.json()["total"] and not res["failed"]
    aw = [i for i in _q(client, ws, "sca") if i["kind"] == "status" and i["awaiting_sca"]]
    assert {i["control_id"] for i in st} <= {i["control_id"] for i in aw}, "every ISSO-approved suggestion now awaits the SCA"
    half = len(aw) // 2
    ok, bad = aw[:half] or aw[:1], aw[half:] if half else []
    for action, items in (("approve", ok), ("reject", bad)):
        if not items:
            continue
        r = client.post("/api/v1/mapping-review/bulk-jobs", json={"system_id": ws["sid"], "action": action, "item_keys": [i["key"] for i in items],
                                                                  "justification": f"SYNTHETIC SCA bulk {action}", "idempotency_key": uuid.uuid4().hex}, headers=ws["sca"])
        assert r.status_code in (200, 201, 202), r.text
        out = run(r.json()["id"], "sca")
        assert out["succeeded"] == len(items) and not out["failed"], out
    left = {i["control_id"] for i in _q(client, ws, "sca") if i["kind"] == "status" and i["awaiting_sca"]}
    assert not left & {i["control_id"] for i in aw}, "decided items leave the queue after reload"
    with SessionLocal() as db:
        for items, result in ((ok, "satisfied"), (bad, "other_than_satisfied")):
            for i in items:
                a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(ws["sid"]), ControlAssignment.control_id == i["control_id"]))
                asm = db.scalars(select(Assessment).where(Assessment.assignment_id == a.id).order_by(Assessment.created_at.desc())).first()
                assert a.assessment_status == result and asm is not None and asm.result == result and asm.evidence_ids, (i["control_id"], result)
    print(f"bulk SCA: isso={res['succeeded']} sca_approved={len(ok)} sca_rejected={len(bad)}")
