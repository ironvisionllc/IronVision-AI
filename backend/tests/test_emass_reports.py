"""Generic eMASS report import: type detection (+ ambiguous/override), context prompts (in-system / no-system, mismatch), register-new
pre-fill without auto-create, no auto-save, per-section permissions, TR stays proposals, POA&M matching, HW/SW macro safety, audit."""
import io
import uuid
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import AuditEvent, EmassImport, Poam, System, TrRow, TrWorkbook
from app.services import emass_reports as er
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

FX = Path(__file__).parent / "fixtures" / "emass"
FILES = {"system_details": "SYNTHETIC_system_details.xlsx", "control_information": "SYNTHETIC_ControlInfoExport.xlsx", "test_results": "SYNTHETIC_TRExport.xlsx",
         "poam": "SYNTHETIC_poam.xlsx", "hwsw": "SYNTHETIC_HWSWList.xlsm"}


def _wb(rows, title="Sheet1") -> bytes:
    wb = Workbook()
    wb.active.title = title
    for r in rows:
        wb.active.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


@pytest.fixture(scope="module")
def ctx(client, signup_on):  # noqa: F811
    t = _signup(client, f"er-{uuid.uuid4().hex[:6]}@example.com", "ER Org")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "Report System", "acronym": "RPT", "emass_id": "SYN-1", "baseline_key": "moderate",
                                                "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])  # noqa: E731
    return {"sid": sid, "isso": role("isso"), "role": role}


def _up(client, ctx, name, data=None, system=True, h=None):
    fname = name if data is not None else FILES[name]
    r = client.post("/api/v1/emass-imports", files={"file": (fname, data if data is not None else (FX / fname).read_bytes())},
                       data={"system_id": ctx["sid"]} if system else {}, headers=h or ctx["isso"])
    if name.endswith((".txt", ".csv")) and data is not None and not data.startswith(b"Control"):
        return r
    assert r.status_code == 201, r.text
    return r


@pytest.mark.parametrize("typ", list(FILES))
def test_detects_every_type_with_high_confidence(typ):
    name = FILES[typ]
    d = er.detect(er.read_sheets((FX / name).read_bytes(), name))
    assert d["type"] == typ and d["confidence"] == "high", d


def test_ambiguous_file_and_override(client, ctx):
    data = _wb([["Control Acronym", "Severity", "Weakness Description", "Status"], ["AC-2", "High", "x", "Ongoing"]])
    d = er.detect(er.read_sheets(data, "a.xlsx"))
    assert d["confidence"] in ("low", "medium") and {"poam", "control_information"} <= set(d["candidates"]) and d["ambiguous"]
    up = client.post("/api/v1/emass-imports", files={"file": ("a.xlsx", data)}, data={"system_id": ctx["sid"]}, headers=ctx["isso"]).json()
    r = client.post(f"/api/v1/emass-imports/{up['id']}/target", json={"action": "update", "system_id": ctx["sid"], "report_type": "poam"}, headers=ctx["isso"])
    assert r.status_code == 200 and r.json()["report_type"] == "poam" and r.json()["items"][0]["section"] == "POA&M"


def test_in_system_prompt_and_mismatch_warning(client, ctx):
    d = _up(client, ctx, "system_details").json()
    det = d["detected"]
    assert det["type"] == "system_details" and det["context_system"] == "RPT" and det["identity"]["acronym"] == "LTP"
    assert "does not match the current system RPT" in det["mismatch"] and d["status"] == "detected" and d["items"] == []
    ok = _up(client, ctx, "x.xlsx", _wb([["System Name", "System Acronym", "System ID"], ["Report System", "RPT", "SYN-1"]])).json()
    assert ok["detected"]["mismatch"] is None


def test_no_system_prompt_register_prefill_without_create(client, ctx):
    d = _up(client, ctx, "system_details", system=False).json()
    assert d["detected"]["context_system_id"] is None and d["system_id"] is None
    with SessionLocal() as db:
        n = db.scalar(select(func.count()).select_from(System))
    r = client.post(f"/api/v1/emass-imports/{d['id']}/target", json={"action": "register"}, headers=ctx["role"]("system_owner")).json()
    assert r["prefill"]["system"] == {"name": "Logistics Tracking Platform", "acronym": "LTP", "emass_id": "SYN-48213",
                                      "description": "SYNTHETIC – tracks shipments and depot inventory (updated description from eMASS)",
                                      "organization_name": "SYNTHETIC Logistics Command"}
    assert r["prefill"]["categorization_hint"] == {"c": "Moderate", "i": "Moderate", "a": "Low"} and "AO approval" in r["prefill"]["note"]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(System)) == n, "register never auto-creates"
    hist = client.get("/api/v1/emass-imports", headers=ctx["isso"]).json()["items"]
    assert any(h["id"] == d["id"] and h["system_id"] is None for h in hist), "unassigned imports appear in history"


def _target(client, ctx, d, h=None):
    r = client.post(f"/api/v1/emass-imports/{d['id']}/target", json={"action": "update", "system_id": ctx["sid"]}, headers=h or ctx["isso"])
    assert r.status_code == 200, r.text
    return r.json()


def test_system_details_review_no_autosave_and_blocked_sections(client, ctx):
    v = _target(client, ctx, _up(client, ctx, "system_details").json())
    secs = {i["section"]: i for i in v["items"]}
    assert set(secs) == {"System details", "Categorization", "Roles"}
    assert secs["Categorization"]["fields"]["confidentiality_impact"]["blocked"].startswith("Categorization changes go through")
    assert secs["System details"]["fields"]["authorization_status"]["blocked"] and secs["Roles"]["fields"]["role_isso"]["blocked"]
    u = f"/api/v1/emass-imports/{v['id']}"
    assert client.put(f"{u}/decisions", json={"decisions": [{"key": "categorization", "field": "confidentiality_impact", "decision": "accept"}]},
                      headers=ctx["isso"]).status_code == 422
    client.put(f"{u}/decisions", json={"decisions": [{"key": "system_details", "field": "description", "decision": "accept"},
                                                     {"key": "system_details", "field": "name", "decision": "reject"}]}, headers=ctx["isso"])
    det = client.get(f"/api/v1/systems/{ctx['sid']}", headers=ctx["isso"]).json()
    assert det["name"] == "Report System" and "SYNTHETIC" not in (det.get("description") or ""), "decisions never save"
    assert client.post(f"{u}/apply", headers=ctx["isso"]).status_code == 200
    det = client.get(f"/api/v1/systems/{ctx['sid']}", headers=ctx["isso"]).json()
    assert det["description"].startswith("SYNTHETIC – tracks") and det["name"] == "Report System"
    with SessionLocal() as db:
        ev = db.scalar(select(AuditEvent).where(AuditEvent.entity_id == ctx["sid"], AuditEvent.action == "system.updated").order_by(AuditEvent.occurred_at.desc()))
        assert ev.details["source"].startswith("eMASS import System Details SYNTHETIC_system_details.xlsx (sha256 ") and ev.after == {"description": det["description"]}


def test_poam_matching_new_items_and_closure_rule(client, ctx):
    with SessionLocal() as db:
        from app.services import workflow as wf
        s = db.get(System, uuid.UUID(ctx["sid"]))
        p = wf.create_poam(db, system=s, actor=None, data={"weakness": "old text", "control_ids": ["si-2"], "status": "new", "emass_remote_id": "SYN-9002"}, findings=[])
        db.commit()
        pid = str(p.id)
    v = _target(client, ctx, _up(client, ctx, "poam").json())
    it = {i["key"]: i for i in v["items"]}
    matched = next(i for i in v["items"] if i["poam_id"] == pid)
    assert matched["create"] is False and matched["fields"]["weakness"]["change"]
    assert matched["fields"]["status"]["blocked"].startswith("Closing or risk-accepting")
    new = [i for i in v["items"] if i["create"]]
    assert len(new) == 2 and all(i["label"].startswith("New POA&M") for i in new)
    bad = next(i for i in new if "ZZ-9" in str(i["fields"]["control"]["imported"]) or i["fields"]["control"]["error"])
    assert bad["fields"]["control"]["error"] and bad["required_issue"] and bad["fields"]["due_date"]["error"] and bad["fields"]["severity"]["error"]
    good = next(i for i in new if i is not bad)
    u = f"/api/v1/emass-imports/{v['id']}"
    assert client.put(f"{u}/decisions", json={"decisions": [{"key": good["key"], "field": "*", "decision": "accept"},
                                                            {"key": matched["key"], "field": "weakness", "decision": "accept"}]}, headers=ctx["isso"]).status_code == 200
    assert client.post(f"{u}/apply", headers=ctx["isso"]).status_code == 200
    with SessionLocal() as db:
        assert db.get(Poam, uuid.UUID(pid)).weakness.startswith("SYNTHETIC: Patch cadence") and db.get(Poam, uuid.UUID(pid)).status == "new"
        created = db.scalar(select(Poam).where(Poam.system_id == uuid.UUID(ctx["sid"]), Poam.emass_remote_id == "SYN-9001"))
        assert created and created.control_ids == ["ac-2"] and created.status == "new" and str(created.due_date) == "2027-06-30"
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.entity_id == str(created.id), AuditEvent.action == "poam.created"))
    assert it


def test_test_results_import_stays_proposals_pending_sca(client, ctx):
    v = _target(client, ctx, _up(client, ctx, "test_results").json())
    item = v["items"][0]
    assert item["section"] == "Test Results" and item["create"] and "PROPOSALS" in item["note"]
    u = f"/api/v1/emass-imports/{v['id']}"
    client.put(f"{u}/decisions", json={"bulk": "accept_safe"}, headers=ctx["isso"])
    res = client.post(f"{u}/apply", headers=ctx["isso"]).json()
    wid = res["results"][0]["created_id"]
    from worker.handlers import handle_tr_detect
    with SessionLocal() as db:
        handle_tr_detect(db, {"workbook_id": wid})
        db.commit()
        assert db.get(TrWorkbook, uuid.UUID(wid)).sha256 == v["sha256"]
        assert db.scalar(select(func.count()).select_from(TrRow).where(TrRow.workbook_id == uuid.UUID(wid), TrRow.state == "approved")) == 0


def test_hwsw_macro_file_never_runs_macros_and_needs_approval(client, ctx):
    v = _target(client, ctx, _up(client, ctx, "hwsw").json())
    item = v["items"][0]
    assert item["section"] == "Inventory" and "macros are never run" in item["note"] and "approves" in item["note"]


def test_permissions_per_section(client, ctx):
    sca = ctx["role"]("sca")
    v = _target(client, ctx, _up(client, ctx, "poam").json(), h=sca)
    assert v["can_apply"] is False and "POA&M" in v["read_only_sections"]
    u = f"/api/v1/emass-imports/{v['id']}"
    assert client.put(f"{u}/decisions", json={"bulk": "accept_safe"}, headers=sca).status_code == 403
    assert client.post(f"{u}/apply", headers=sca).status_code == 403
    ci = _target(client, ctx, _up(client, ctx, "control_information").json(), h=ctx["role"]("system_owner"))
    assert ci["can_apply"] and "Controls" in ci["allowed_sections"]


def test_rejects_unknown_files(client, ctx):
    assert _up(client, ctx, "x.txt", b"hello").status_code == 422
    assert _up(client, ctx, "x.csv", b"\xff\xfe\x00bad").status_code == 422
    d = _up(client, ctx, "x.csv", b"Control Acronym,SLCM Frequency\nAC-2,Weekly\n").json()
    assert d["detected"]["type"] == "control_information"
    with SessionLocal() as db:
        assert db.get(EmassImport, uuid.UUID(d["id"])).storage_key.endswith("x.csv")


def test_emass_id_mismatch_warns_even_when_acronym_matches(client, ctx):
    d = _up(client, ctx, "y.xlsx", _wb([["System Name", "System Acronym", "System ID"], ["Report System", "RPT", "SYN-999"]])).json()
    assert "eMASS ID 'SYN-999'" in d["detected"]["mismatch"]


def test_read_only_role_cannot_upload(client, ctx):
    r = client.post("/api/v1/emass-imports", files={"file": ("a.xlsx", (FX / FILES["poam"]).read_bytes())}, data={"system_id": ctx["sid"]},
                    headers=ctx["role"]("leadership_viewer"))
    assert r.status_code == 403


def test_cancel_and_register_close_the_session_with_audit(client, ctx):
    d = _up(client, ctx, "system_details", system=False).json()
    assert client.post(f"/api/v1/emass-imports/{d['id']}/target", json={"action": "cancel"}, headers=ctx["isso"]).json()["status"] == "discarded"
    d2 = _up(client, ctx, "system_details", system=False).json()
    assert client.post(f"/api/v1/emass-imports/{d2['id']}/target", json={"action": "register"}, headers=ctx["role"]("system_owner")).json()["status"] == "to_registration"
    with SessionLocal() as db:
        acts = set(db.scalars(select(AuditEvent.action).where(AuditEvent.entity_id.in_([d["id"], d2["id"]]))))
        assert {"emass.import_discarded", "emass.import_to_registration"} <= acts
        assert db.get(EmassImport, uuid.UUID(d["id"])).finished_at is not None
