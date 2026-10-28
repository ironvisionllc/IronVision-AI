"""Manage imported data for EVERY import type: Test Results, HW/SW inventory, scan uploads (STIG CKL), policy uploads and the eMASS
"Register a new system" path. restore / delete / undo, decisions flagged (never removed), exports exclude deleted items, evidence link
vs file, RBAC 403, cross-tenant 404. Zero AI cost (policy mappings are created directly as SYNTHETIC rows)."""
import io
import uuid
from datetime import datetime, timezone

import openpyxl
import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Asset, AuditEvent, Evidence, EvidenceControl, Finding, Policy, PolicyControlMap, ReviewFlag, SoftwareItem, System, TrRow, User
from tests.conftest import auth
from tests.test_inventory import _jobs, ckl, workbook
from tests.test_processing_pipeline import _process
from tests.test_sandbox import _signup, signup_on  # noqa: F401
from tests.test_tr import BLANK

M = "/api/v1/imported-data"


@pytest.fixture(scope="module")
def w(client, signup_on):  # noqa: F811
    from worker.handlers import handle_tr_detect, handle_tr_generate
    t = _signup(client, f"ida-{uuid.uuid4().hex[:6]}@example.com", f"IDA Org {uuid.uuid4().hex[:4]}")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "IDA System", "acronym": f"ID{uuid.uuid4().hex[:3]}", "baseline_key": "moderate",
                                                "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])  # noqa: E731
    isso = role("isso")
    inv = client.post(f"/api/v1/systems/{sid}/inventory/imports", files={"file": ("HWSW.xlsm", workbook())}, headers=isso).json()["id"]
    with SessionLocal() as db:
        _jobs(db, "inventory.import")
    run = client.post(f"/api/v1/systems/{sid}/uploads", files={"file": ("web01.ckl", ckl("web01", "10.0.0.1"))}, headers=isso).json()["id"]
    _process(run)
    wid = client.post(f"/api/v1/systems/{sid}/tr/workbooks", files={"file": ("BLANK_TRExport.xlsx", BLANK)}, headers=isso).json()["id"]
    with SessionLocal() as db:
        handle_tr_detect(db, {"workbook_id": wid})
        db.commit()
        handle_tr_generate(db, {"workbook_id": wid, "populate": True})
        db.commit()
        rows = sorted(db.scalars(select(TrRow).where(TrRow.workbook_id == uuid.UUID(wid))), key=lambda r: r.row_number)
        tr_ids = [str(r.id) for r in rows[:3]]
    sca = role("sca")
    per = {i: {"tested_by": f"Tester {n}", "date_tested": f"2026-08-0{n + 1}"} for n, i in enumerate(tr_ids)}
    assert client.post(f"/api/v1/tr/workbooks/{wid}/decide", json={"action": "approve", "row_ids": tr_ids, "justification": "SYNTHETIC approval",
                                                                    "status": "Compliant", "per_row": per,
                                                                    "values": {"test_results": "SYNTHETIC result"}}, headers=sca).status_code == 200
    pol = client.post("/api/v1/policies", files={"file": ("SYN_AC_policy.txt", b"SYNTHETIC access control policy. Accounts are reviewed every 90 days.")},
                      data={"title": "SYNTHETIC AC Policy", "system_ids": sid}, headers=isso).json()["id"]
    with SessionLocal() as db:
        org = db.scalar(select(System.org_id).where(System.id == uuid.UUID(sid)))
        uid = db.scalar(select(User.id).where(User.org_id == org))
        db.add_all([PolicyControlMap(policy_id=uuid.UUID(pol), org_id=org, control_id="ac-2", status="mapped", source="manual", confidence="High",
                                     decided_by=uid, decided_at=datetime.now(timezone.utc), basis="SYNTHETIC"),
                    PolicyControlMap(policy_id=uuid.UUID(pol), org_id=org, control_id="ac-3", status="proposed", source="statement_language", confidence="Medium")])
        db.commit()
    return {"h": isso, "sid": sid, "role": role, "inv": inv, "run": run, "wid": wid, "tr_ids": tr_ids, "pol": pol}


def _v(client, w, kind, iid, h=None):
    r = client.get(f"{M}/{kind}/{iid}", headers=h or w["h"])
    assert r.status_code == 200, r.text
    return r.json()


def test_history_offers_manage_for_every_type(client, w):
    items = client.get("/api/v1/import-center/history", params={"system_id": w["sid"]}, headers=w["h"]).json()["items"]
    kinds = {i["kind"] for i in items}
    assert {"tr", "inventory", "ingest", "policy"} <= kinds
    for kind, iid, dest in (("tr", w["wid"], "Test Results"), ("inventory", w["inv"], "HW/SW Inventory"), ("ingest", w["run"], "Findings"),
                            ("policy", w["pol"], "Policy Auditor")):
        v = _v(client, w, kind, iid)
        assert v["groups"].get(dest) and v["import"]["file_name"] and v["can_change"]


def test_tr_restore_delete_undo_flags_and_export_excludes(client, w):
    a, b = w["tr_ids"][0], w["tr_ids"][1]
    r = client.post(f"{M}/tr/{w['wid']}", json={"action": "delete", "ids": [f"tr_row|{a}"]}, headers=w["h"]).json()
    assert r["failed"] == 1 and r["results"][0]["needs_confirm"], "SCA-approved row needs confirmation"
    r = client.post(f"{M}/tr/{w['wid']}", json={"action": "delete", "ids": [f"tr_row|{a}"], "force": True}, headers=w["h"]).json()
    assert r["ok"] == 1
    flags = client.get(f"/api/v1/systems/{w['sid']}/review-flags", headers=w["h"]).json()["items"]
    assert any(f["entity_type"] == "tr_row" and f["entity_id"] == a for f in flags), "decision flagged needs re-review"
    with SessionLocal() as db:
        assert db.get(TrRow, uuid.UUID(a)) is None
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.entity_id == w["wid"], AuditEvent.action == "import_data.delete"))
    e = client.post(f"/api/v1/tr/workbooks/{w['wid']}/export", headers=w["h"])
    assert e.status_code == 200, e.text
    assert e.json()["counts"]["written_rows"] == 2, "deleted approved row excluded from the export"
    rs = client.post(f"{M}/tr/{w['wid']}", json={"action": "restore", "ids": [f"tr_row|{b}"], "force": True}, headers=w["h"]).json()
    assert rs["ok"] == 1
    with SessionLocal() as db:
        assert db.get(TrRow, uuid.UUID(b)).state == "auto"
    for op in (r["op"]["op_id"], rs["op"]["op_id"]):
        assert client.post(f"{M}/tr/{w['wid']}/undo/{op}", headers=w["h"]).status_code == 200
    with SessionLocal() as db:
        assert db.get(TrRow, uuid.UUID(a)).state == "approved" and db.get(TrRow, uuid.UUID(b)).state == "approved"
        assert db.scalar(select(ReviewFlag.status).where(ReviewFlag.entity_id == a)) == "undone"
    assert client.post(f"{M}/tr/{w['wid']}/undo/{r['op']['op_id']}", headers=w["h"]).status_code == 409


def test_inventory_delete_undo_and_hwsw_export_excludes(client, w):
    v = _v(client, w, "inventory", w["inv"])
    web = next(e for e in v["entries"] if e["record"] == "web01")
    sw = next(e for e in v["entries"] if e["id"].startswith("software|"))
    idx = client.get(f"/api/v1/systems/{w['sid']}/imported-data/index", params={"kind": "asset"}, headers=w["h"]).json()["items"]
    assert idx[web["entity_id"]]["file_name"] == "HWSW.xlsm"
    r = client.post(f"{M}/inventory/{w['inv']}", json={"action": "delete", "ids": [web["id"], sw["id"]]}, headers=w["h"]).json()
    assert r["ok"] == 2
    with SessionLocal() as db:
        assert db.get(Asset, uuid.UUID(web["entity_id"])) is None and db.get(SoftwareItem, uuid.UUID(sw["entity_id"])) is None
        fnd = db.scalar(select(Finding).where(Finding.system_id == uuid.UUID(w["sid"]), Finding.asset_id.is_(None)))
    ex = client.post(f"/api/v1/systems/{w['sid']}/inventory/export", headers=w["h"])
    assert ex.status_code in (200, 201), ex.text
    data = client.get(f"/api/v1/inventory/exports/{ex.json()['id']}/download", headers=w["h"]).content
    wbk = openpyxl.load_workbook(io.BytesIO(data), keep_vba=True)
    assert not any("web01" == c.value for row in wbk["Hardware"].iter_rows() for c in row), "deleted asset excluded from the HW/SW export"
    assert client.post(f"{M}/inventory/{w['inv']}/undo/{r['op']['op_id']}", headers=w["h"]).status_code == 200
    with SessionLocal() as db:
        assert db.get(Asset, uuid.UUID(web["entity_id"])).name == "web01" and db.get(SoftwareItem, uuid.UUID(sw["entity_id"]))
        if fnd:
            assert db.get(Finding, fnd.id).asset_id is not None, "SET NULL references restored on undo"


def test_findings_delete_undo_poam_flag_and_evidence_link_vs_file(client, w):
    v = _v(client, w, "ingest", w["run"])
    f = next(e for e in v["entries"] if e["id"].startswith("finding|") and e["actions"])
    pid = client.post("/api/v1/poams", json={"system_id": w["sid"], "weakness": "SYNTHETIC weakness", "control_ids": ["cm-6"]}, headers=w["h"]).json()["id"]
    assert client.post(f"/api/v1/poams/{pid}/findings", json={"finding_id": f["entity_id"]}, headers=w["h"]).status_code == 200
    r = client.post(f"{M}/ingest/{w['run']}", json={"action": "delete", "ids": [f["id"]]}, headers=w["h"]).json()
    assert r["ok"] == 1
    flags = client.get(f"/api/v1/systems/{w['sid']}/review-flags", headers=w["h"]).json()["items"]
    assert any(x["entity_type"] == "poam" and x["entity_id"] == pid for x in flags), "POA&M kept and flagged"
    assert client.get(f"/api/v1/poams/{pid}", headers=w["h"]).status_code == 200
    link = next(e for e in v["entries"] if e["id"].startswith("evidence_link|"))
    filee = next(e for e in v["entries"] if e["id"].startswith("evidence_file|"))
    lr = client.post(f"{M}/ingest/{w['run']}", json={"action": "delete", "ids": [link["id"]]}, headers=w["h"]).json()
    assert lr["ok"] == 1
    with SessionLocal() as db:
        assert db.get(EvidenceControl, uuid.UUID(link["entity_id"])).removed_at and db.get(Evidence, uuid.UUID(filee["entity_id"])).status == "active"
    fr = client.post(f"{M}/ingest/{w['run']}", json={"action": "delete", "ids": [filee["id"]]}, headers=w["h"]).json()
    assert fr["failed"] == 1 and fr["results"][0]["needs_file_confirm"]
    fr = client.post(f"{M}/ingest/{w['run']}", json={"action": "delete", "ids": [filee["id"]], "confirm_file": True}, headers=w["h"]).json()
    assert fr["ok"] == 1
    for op in (r["op"]["op_id"], lr["op"]["op_id"], fr["op"]["op_id"]):
        assert client.post(f"{M}/ingest/{w['run']}/undo/{op}", headers=w["h"]).status_code == 200
    with SessionLocal() as db:
        assert db.get(Finding, uuid.UUID(f["entity_id"])) and db.get(Evidence, uuid.UUID(filee["entity_id"])).status == "active"
        assert db.get(EvidenceControl, uuid.UUID(link["entity_id"])).removed_at is None


def test_policy_delete_human_mapping_confirm_flag_undo(client, w):
    v = _v(client, w, "policy", w["pol"])
    hm = next(e for e in v["entries"] if e["id"].startswith("policy_map|") and e.get("decision"))
    r = client.post(f"{M}/policy/{w['pol']}", json={"action": "delete", "ids": [hm["id"]]}, headers=w["h"]).json()
    assert r["results"][0]["needs_confirm"]
    r = client.post(f"{M}/policy/{w['pol']}", json={"action": "delete", "all": True, "force": True}, headers=w["h"]).json()
    assert r["ok"] == 1
    with SessionLocal() as db:
        assert db.get(Policy, uuid.UUID(w["pol"])).status == "removed"
        assert not db.scalar(select(PolicyControlMap.id).where(PolicyControlMap.policy_id == uuid.UUID(w["pol"])))
        assert db.scalar(select(ReviewFlag.id).where(ReviewFlag.entity_type == "policy_mapping", ReviewFlag.status == "open"))
    assert client.post(f"{M}/policy/{w['pol']}/undo/{r['op']['op_id']}", headers=w["h"]).status_code == 200
    with SessionLocal() as db:
        assert db.get(Policy, uuid.UUID(w["pol"])).status == "current"
        assert db.scalar(select(func.count()).select_from(PolicyControlMap).where(PolicyControlMap.policy_id == uuid.UUID(w["pol"]))) == 2
    r = client.post(f"{M}/policy/{w['pol']}", json={"action": "delete", "ids": [hm["id"]], "force": True}, headers=w["h"]).json()
    assert r["ok"] == 1, "a single human-approved mapping can be deleted after confirmation (flagged)"


def test_rbac_403_cross_tenant_404_and_flag_resolve_permission(client, w, signup_on):  # noqa: F811
    ao = w["role"]("ao")
    for kind, iid in (("tr", w["wid"]), ("inventory", w["inv"]), ("ingest", w["run"]), ("policy", w["pol"])):
        v = client.get(f"{M}/{kind}/{iid}", headers=ao).json()
        assert not v["can_change"] and all(not e["actions"] for e in v["entries"])
        assert client.post(f"{M}/{kind}/{iid}", json={"action": "delete", "all": True}, headers=ao).status_code == 403
    other = auth(_signup(client, f"ida-x-{uuid.uuid4().hex[:6]}@example.com", f"IDA X {uuid.uuid4().hex[:4]}")["access_token"])
    for kind, iid in (("tr", w["wid"]), ("inventory", w["inv"]), ("ingest", w["run"]), ("policy", w["pol"])):
        assert client.get(f"{M}/{kind}/{iid}", headers=other).status_code == 404
        assert client.post(f"{M}/{kind}/{iid}", json={"action": "delete", "all": True}, headers=other).status_code == 404
        assert client.post(f"{M}/{kind}/{iid}/undo/abc", headers=other).status_code == 404
    assert client.get(f"/api/v1/systems/{w['sid']}/imported-data/index", params={"kind": "finding"}, headers=other).status_code == 404
    assert client.get(f"/api/v1/systems/{w['sid']}/review-flags", headers=other).status_code == 404
    flags = client.get(f"/api/v1/systems/{w['sid']}/review-flags", headers=w["h"]).json()["items"]
    fl = next(f for f in flags if f["entity_type"] == "policy_mapping")
    assert client.post(f"/api/v1/review-flags/{fl['id']}/resolve", json={"note": "checked"}, headers=other).status_code == 404
    assert client.post(f"/api/v1/review-flags/{fl['id']}/resolve", json={"note": "checked"}, headers=ao).status_code == 403
    assert client.post(f"/api/v1/review-flags/{fl['id']}/resolve", json={"note": "Re-reviewed the mapping"}, headers=w["h"]).status_code == 200


def test_register_new_system_path_fields_shown_as_imported_clear_restore_undo(client, w):
    from app.services import emass_reports as er
    h = w["role"]("issm")
    up = client.post("/api/v1/emass-imports", files={"file": ("SYN_SystemDetails.xlsx", er.sample_xlsx("system_details", None))}, headers=h)
    assert up.status_code == 201, up.text
    iid = up.json()["id"]
    t = client.post(f"/api/v1/emass-imports/{iid}/target", json={"action": "register", "report_type": "system_details"}, headers=h)
    assert t.status_code == 200, t.text
    pre = t.json()["prefill"]["system"]
    assert pre.get("name") and pre.get("description")
    body = {**pre, "acronym": f"RG{uuid.uuid4().hex[:3]}", "baseline_key": "moderate", "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}
    sid = client.post("/api/v1/systems", json=body, headers=h).json()["id"]
    reg = client.post(f"/api/v1/emass-imports/{iid}/registered", json={"system_id": sid, "fields": {**pre, "acronym": body["acronym"]}}, headers=h)
    assert reg.status_code == 200 and "description" in reg.json()["fields"]
    v = _v(client, w, "emass", iid, h)
    reg_e = [e for e in v["entries"] if e["destination"] == "Registration (System Details)"]
    assert {e["field"] for e in reg_e} >= {"name", "description"} and all(e["state"] == "applied" for e in reg_e)
    assert "clear" not in next(e for e in reg_e if e["field"] == "name")["actions"], "the required name can be restored, not cleared"
    r = client.post(f"{M}/emass/{iid}", json={"action": "clear", "ids": ["reg|description"]}, headers=h).json()
    assert r["ok"] == 1
    with SessionLocal() as db:
        assert db.get(System, uuid.UUID(sid)).description is None
    allr = client.post(f"{M}/emass/{iid}", json={"action": "clear", "all": True}, headers=h).json()  # "delete everything this import created" – system shell kept
    with SessionLocal() as db:
        s = db.get(System, uuid.UUID(sid))
        assert s is not None and s.name == pre["name"]
    if allr.get("op"):  # undo newest first
        assert client.post(f"{M}/emass/{iid}/undo/{allr['op']['op_id']}", headers=h).status_code == 200
    assert client.post(f"{M}/emass/{iid}/undo/{r['op']['op_id']}", headers=h).status_code == 200
    with SessionLocal() as db:
        assert db.get(System, uuid.UUID(sid)).description == pre["description"]
    items = client.get("/api/v1/import-center/history", params={"system_id": sid}, headers=h).json()["items"]
    assert any(i["id"] == iid and i["status"] == "applied" for i in items)
