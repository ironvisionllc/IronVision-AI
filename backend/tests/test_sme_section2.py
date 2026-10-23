"""SME section 2: STIG run detail, unified Mapping Review queue (STIG / policy / status suggestions), bulk + justification, SoD."""
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import ControlAssignment, FindingControlMap, IngestRun, System, User
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401
from tests.test_sme_section1 import RA_POLICY, _docx


@pytest.fixture(scope="module")
def ws(client, signup_on):  # noqa: F811
    t = _signup(client, f"s2-{uuid.uuid4().hex[:6]}@example.com", "S2 Org")
    h = auth(t["access_token"])
    assert client.post("/api/v1/sandbox/demo-data", headers=h).status_code == 200
    with SessionLocal() as db:
        from sqlalchemy import func
        from app.models import Finding
        org = db.scalar(select(User.org_id).where(User.email == t["user"]["email"]))
        sid = str(db.scalar(select(System.id).join(Finding, Finding.system_id == System.id).join(FindingControlMap, FindingControlMap.finding_id == Finding.id)
                            .where(System.org_id == org).group_by(System.id).order_by(func.count().desc()).limit(1)))
    return {"h": h, "sid": sid, "org": org}


def _queue(client, ws):
    return client.get("/api/v1/mapping-review", params={"system_id": ws["sid"]}, headers=ws["h"]).json()


def test_stig_run_detail_all_rules_totals_and_source_check(client, ws):
    with SessionLocal() as db:
        run = db.scalar(select(IngestRun).join(System, System.id == IngestRun.system_id)
                        .where(System.org_id == ws["org"], IngestRun.file_format == "ckl", IngestRun.status != "duplicate").limit(1))
    d = client.get(f"/api/v1/ingest-runs/{run.id}/stig", headers=ws["h"]).json()
    assert d["header"]["title"] and d["rules"]
    assert {r["status"] for r in d["rules"]} <= {"Open", "Not a Finding", "Not Applicable", "Not Reviewed"}
    assert {r["severity"] for r in d["rules"]} <= {"CAT I", "CAT II", "CAT III"}
    assert sum(d["totals"]["by_status"].values()) == len(d["rules"]) == sum(d["totals"]["by_severity"].values())
    assert d["parse_check"]["match"] is True and d["parse_check"]["source_rules"] == len(d["rules"])
    assert all(r["vuln_id"] and r["rule_id"] and r["title"] for r in d["rules"])


def test_queue_is_not_empty_and_lists_every_automated_kind(client, ws):
    r = client.post("/api/v1/policies", files={"file": ("ra.docx", _docx(RA_POLICY))}, data={"title": "RA S2", "system_ids": ws["sid"]}, headers=ws["h"])
    from worker.handlers import handle_policy_analyze
    with SessionLocal() as db:
        handle_policy_analyze(db, {"policy_id": r.json()["id"]})
        db.commit()
    q = _queue(client, ws)
    assert q["queue_counts"]["finding_map"] > 0 and q["queue_counts"]["policy_map"] > 0, q["queue_counts"]
    assert any(i["kind"] == "policy_map" and i["control_id"] == "ra-1" for i in q["queue"])


def test_listing_never_changes_status(client, ws):
    with SessionLocal() as db:
        before = {a.control_id: (a.implementation_status, a.assessment_status) for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(ws["sid"])))}
    _queue(client, ws)
    _queue(client, ws)
    with SessionLocal() as db:
        after = {a.control_id: (a.implementation_status, a.assessment_status) for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(ws["sid"])))}
    assert before == after


def _post(client, ws, items, action, just="", edit=None):
    return client.post("/api/v1/mapping-review/decide", json={"system_id": ws["sid"], "items": items, "action": action, "justification": just,
                                                              "edit_control_ids": edit or []}, headers=ws["h"])


def _items(q, kind, n):
    return [{"kind": i["kind"], "ids": i["ids"], "control_id": i["control_id"], "evidence_fp": i.get("evidence_fp")} for i in q["queue"] if i["kind"] == kind][:n]


def test_bulk_approve_reject_edit_with_justification(client, ws):
    q = _queue(client, ws)
    fm = _items(q, "finding_map", 4)
    assert _post(client, ws, fm[:1], "reject").status_code == 422                 # justification required
    assert _post(client, ws, fm[:2], "approve").json()["approved"] == 2           # bulk, justification optional for approve
    assert _post(client, ws, fm[2:3], "edit", "Rule actually supports remote access", ["ac-17(2)"]).json()["edited"] == 1
    with SessionLocal() as db:
        st = {str(m.id): m.review_status for m in db.scalars(select(FindingControlMap).where(FindingControlMap.id.in_([uuid.UUID(i) for x in fm[:3] for i in x["ids"]])))}
        edited = db.scalar(select(FindingControlMap).where(FindingControlMap.mapping_source == "human_edit", FindingControlMap.control_id == "ac-17.2",
                                                           FindingControlMap.valid_to.is_(None)))
    assert {st[i] for x in fm[:2] for i in x["ids"]} == {"human_approved"}
    assert {st[i] for i in fm[2]["ids"]} == {"rejected"} and edited is not None and edited.review_status == "human_approved"
    pm = _items(_queue(client, ws), "policy_map", 1)
    assert _post(client, ws, pm, "approve").status_code == 200
    assert not [i for i in _queue(client, ws)["queue"] if i["ids"] == pm[0]["ids"]]


def test_status_suggestion_requires_approval_and_respects_sod(client, ws):
    q = _queue(client, ws)
    st = _items(q, "status", 2)
    if not st:
        pytest.skip("no control has current passing evidence without open findings in this sample system")
    cid = st[0]["control_id"]
    r = _post(client, ws, st[:1], "approve", "Evidence reviewed")
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(ws["sid"]), ControlAssignment.control_id == cid))
    assert a.implementation_status == "implemented"
    assert (a.assessment_status == "satisfied") != (cid in r.json()["partial"])  # ISSO persona: assessment left to the SCA
    if len(st) > 1:
        assert _post(client, ws, st[1:2], "reject", "Evidence is for a different boundary").status_code == 200
        assert not [i for i in _queue(client, ws)["queue"] if i["kind"] == "status" and i["control_id"] == st[1]["control_id"]]
