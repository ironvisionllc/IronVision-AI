"""Shared separation of duties for Test Results (edit/prepare → SCA approve) and Inventory (accept → approve).
Real orgs: different REAL person required (persona switching ≠ different person). Sandbox orgs: a different persona is allowed and
labelled "Sandbox: same person"; the same persona is always refused. The sandbox flag is server-side only."""
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent, Organization, RoleAssignment, System, TrRow, TrWorkbook, User
from tests.conftest import auth
from tests.test_inventory import _discs, inv  # noqa: F401
from tests.test_sandbox import _signup, signup_on  # noqa: F401
from tests.test_tr import _ap, _import, _rows, populated, ws  # noqa: F401

T = {"tested_by": "Lee, Sam", "date_tested": "2026-09-01"}
SPOOF = {"X-Sandbox": "true", "X-Org-Is-Sandbox": "1"}


def _set_sandbox(org_id, value: bool):
    with SessionLocal() as db:
        db.get(Organization, org_id).is_sandbox = value
        db.commit()


def _real_user(org_id, role: str) -> dict:
    """A different REAL person in the same org."""
    from app.security import sessions
    from app.security.tokens import create_access_token

    with SessionLocal() as db:
        u = User(org_id=org_id, email=f"real-{role}-{uuid.uuid4().hex[:6]}@example.com", display_name=f"Real {role}", is_active=True)
        db.add(u)
        db.flush()
        db.add(RoleAssignment(user_id=u.id, role=role, scope_type="org", scope_id=org_id))
        sess, _ = sessions.create(db, u.id, "dev_password", None, None)
        db.commit()
        return auth(create_access_token(u.id, "dev_password", sess.id)[0])


@pytest.fixture(scope="module")
def tw(client, ws):  # noqa: F811
    c = ws["stig_ctl"]
    rows = [(_ap(c).split("(")[0], f"{_ap(c)}.{i}", ws["stig_cci"].replace("CCI-", "")) for i in range(1, 10)]
    wid = _import(client, ws, populated(rows), name="TR-sod.xlsx")
    with SessionLocal() as db:
        org = db.get(TrWorkbook, uuid.UUID(wid)).org_id
    return {"wid": wid, "org": org}


def _edit(client, wid, rid, h, text):
    r = client.post(f"/api/v1/tr/workbooks/{wid}/decide", json={"action": "edit", "row_ids": [rid], "justification": "prepare text",
                                                                "values": {"test_results": text}}, headers=h)
    assert r.status_code == 200, r.text


def _approve(client, wid, rids, h, extra=None, headers=None):
    return client.post(f"/api/v1/tr/workbooks/{wid}/decide", json={"action": "approve", "row_ids": rids, "status": "Compliant",
                                                                   "justification": "SCA review", **T, **(extra or {})}, headers={**h, **(headers or {})})


def test_tr_sandbox_different_persona_allowed_and_labelled(client, ws, tw):  # noqa: F811
    _set_sandbox(tw["org"], True)
    rows, isso, sca = _rows(client, ws, tw["wid"]), ws["role"]("isso"), ws["role"]("sca")
    _edit(client, tw["wid"], rows[7]["id"], isso, "Prepared by the ISSO")
    r = _approve(client, tw["wid"], [rows[7]["id"]], sca)
    assert r.status_code == 200 and r.json()["approved"] == [7], r.text
    with SessionLocal() as db:
        row = db.get(TrRow, uuid.UUID(rows[7]["id"]))
        assert row.final["sod_label"] == "Sandbox: same person" and row.final["test_results"] == "Prepared by the ISSO"
        ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "tr.row_approved", AuditEvent.entity_id == rows[7]["id"]))
        d = ev.details
        assert d["label"] == "Sandbox: same person" and d["prepared_by"]["persona_role"] == "isso" and d["approved_by"]["persona_role"] == "sca"
        assert d["prepared_by"]["real_user_id"] == d["approved_by"]["real_user_id"]


def test_tr_sandbox_same_persona_refused_single_and_bulk(client, ws, tw):  # noqa: F811
    _set_sandbox(tw["org"], True)
    rows, isso, sca = _rows(client, ws, tw["wid"]), ws["role"]("isso"), ws["role"]("sca")
    _edit(client, tw["wid"], rows[8]["id"], sca, "SCA wrote this")
    r = _approve(client, tw["wid"], [rows[8]["id"]], sca)
    assert r.status_code == 403 and "same role" in r.json()["detail"]
    lock = next(x for x in client.get(f"/api/v1/tr/workbooks/{tw['wid']}/rows", headers=sca).json()["items"] if x["row"] == 8)["sod_lock"]
    assert lock and "Separation of duties" in lock
    _edit(client, tw["wid"], rows[9]["id"], isso, "ISSO wrote this")
    b = _approve(client, tw["wid"], [rows[8]["id"], rows[9]["id"], rows[10]["id"]], sca)
    assert b.status_code == 200 and b.json()["approved"] == [9, 10], b.text
    assert b.json()["skipped"][0]["row"] == 8 and "Separation of duties" in b.json()["skipped"][0]["reason"]
    e = client.post(f"/api/v1/tr/workbooks/{tw['wid']}/export", headers=ws["h"]).json()
    assert e["verification"]["sandbox_same_person_rows"] == 2
    hist = client.get(f"/api/v1/tr/workbooks/{tw['wid']}", headers=ws["h"]).json()["exports"][0]
    assert hist["sandbox_same_person_rows"] == 2


def test_tr_real_org_requires_a_different_real_person(client, ws, tw):  # noqa: F811
    rows, isso, sca = _rows(client, ws, tw["wid"]), ws["role"]("isso"), ws["role"]("sca")  # persona sessions opened while still a sandbox
    _set_sandbox(tw["org"], False)
    try:
        _edit(client, tw["wid"], rows[11]["id"], isso, "ISSO prepared (real org)")
        r = _approve(client, tw["wid"], [rows[11]["id"]], sca)
        assert r.status_code == 403 and "persona does not count" in r.json()["detail"]
        spoof = _approve(client, tw["wid"], [rows[11]["id"]], sca, {"is_sandbox": True, "sandbox": True}, SPOOF)
        assert spoof.status_code == 403, "client input cannot turn on sandbox rules"
        other = _real_user(tw["org"], "sca")
        ok = _approve(client, tw["wid"], [rows[11]["id"]], other)
        assert ok.status_code == 200 and ok.json()["approved"] == [11]
        with SessionLocal() as db:
            ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "tr.row_approved", AuditEvent.entity_id == rows[11]["id"]))
            assert ev.details["sod"] == "different person" and "label" not in ev.details
        _edit(client, tw["wid"], rows[12]["id"], other, "SCA edited own row")
        assert _approve(client, tw["wid"], [rows[12]["id"]], other).status_code == 403
        _edit(client, tw["wid"], rows[13]["id"], isso, "ISSO prepared")
        b = _approve(client, tw["wid"], [rows[12]["id"], rows[13]["id"]], other)
        assert b.json()["approved"] == [13] and b.json()["skipped"][0]["row"] == 12
        assert _approve(client, tw["wid"], [rows[14]["id"]], sca).status_code == 200, "an unedited (auto-suggested) row can be approved directly"
    finally:
        _set_sandbox(tw["org"], True)


def test_approve_saves_test_results_and_documents_field(client, ws, tw):  # noqa: F811
    rows, sca = _rows(client, ws, tw["wid"]), ws["role"]("sca")
    r = _approve(client, tw["wid"], [rows[15]["id"]], sca, {"values": {"test_results": "Final SCA wording"}})
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.get(TrRow, uuid.UUID(rows[15]["id"])).final["test_results"] == "Final SCA wording"
    bad = _approve(client, tw["wid"], [rows[15]["id"]], sca, {"values": {"compliance_status": "Compliant"}})
    assert bad.status_code == 422 and "values.test_results" in bad.json()["detail"]
    spec = client.get("/api/openapi.json").json()["components"]["schemas"]["DecideIn"]["properties"]["values"]
    assert "test_results" in spec["description"] and "approve" in spec["description"]


def _open_change(client, inv, skip=()):  # noqa: F811
    return next(x for x in _discs(client, inv) if x["status"] == "open" and x["proposed_change"] and x["id"] not in skip)


def _org(inv):  # noqa: F811
    with SessionLocal() as db:
        return db.get(System, uuid.UUID(inv["sid"])).org_id


def test_inventory_sandbox_rules(client, inv):  # noqa: F811
    _set_sandbox(_org(inv), True)
    d = _open_change(client, inv)
    url = f"/api/v1/inventory/discrepancies/{d['id']}"
    assert client.post(url, json={"action": "accept"}, headers=inv["role"]("isso")).status_code == 200
    r = client.post(url, json={"action": "approve"}, headers=inv["role"]("issm"))
    assert r.status_code == 200 and r.json()["status"] == "applied" and r.json()["sod"]["label"] == "Sandbox: same person", r.text
    with SessionLocal() as db:
        ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "inventory.change_applied", AuditEvent.entity_id == d["id"]))
        assert ev.details["label"] == "Sandbox: same person" and ev.details["prepared_by"]["persona_role"] == "isso" and ev.details["approved_by"]["persona_role"] == "issm"
    d2 = _open_change(client, inv, {d["id"]})
    u2 = f"/api/v1/inventory/discrepancies/{d2['id']}"
    client.post(u2, json={"action": "accept"}, headers=inv["role"]("isso"))
    same = client.post(u2, json={"action": "approve"}, headers=inv["role"]("isso"))
    assert same.status_code == 403 and "same role" in same.json()["detail"]


def test_inventory_real_org_rules(client, inv):  # noqa: F811
    org = _org(inv)
    isso, issm = inv["role"]("isso"), inv["role"]("issm")  # persona sessions opened while still a sandbox
    _set_sandbox(org, False)
    try:
        d = _open_change(client, inv)
        url = f"/api/v1/inventory/discrepancies/{d['id']}"
        client.post(url, json={"action": "accept"}, headers=isso)
        r = client.post(url, json={"action": "approve"}, headers=issm)
        assert r.status_code == 403 and "persona does not count" in r.json()["detail"]
        assert client.post(url, json={"action": "approve", "is_sandbox": True}, headers={**issm, **SPOOF}).status_code in (403, 422)
        lock = next(x for x in client.get(f"/api/v1/systems/{inv['sid']}/inventory/discrepancies", headers=issm).json() if x["id"] == d["id"])
        assert lock["approve_locked"] and "different person" in lock["approve_locked"]
        ok = client.post(url, json={"action": "approve"}, headers=_real_user(org, "issm"))
        assert ok.status_code == 200 and ok.json()["sod"]["sod"] == "different person"
    finally:
        _set_sandbox(org, True)


def test_mocked_badge_names_the_collector(client, inv):  # noqa: F811
    from app.models import EvidenceSource
    from app.services.connectors import MockAdapter
    from app.services.inventory import consistency as cs

    with SessionLocal() as db:
        src = EvidenceSource(system_id=uuid.UUID(inv["sid"]), name="On-prem collector (MOCK)", source_type="on_prem", adapter="mock", config={})
        db.add(src)
        db.flush()
        MockAdapter().collect(db, src)
        db.commit()
        cs.run(db, uuid.UUID(inv["sid"]))
        db.commit()
    d = next(x for x in _discs(client, inv) if x["kind"] == "missing_from_inventory" and "mock-onprem-01" in x["title"])
    assert {(r["source_label"], r["collector"]) for r in d["records"]} == {("MOCKED source", "On-prem collector (MOCK)")}
    o = client.get(f"/api/v1/systems/{inv['sid']}/inventory", headers=inv["h"]).json()
    assert next(a for a in o["scan_observed"] if a["name"] == "mock-onprem-01")["collector"] == "On-prem collector (MOCK)"
