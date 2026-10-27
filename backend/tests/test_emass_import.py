"""eMASS Control Information import: header detection, matching, validation, no-autosave review, accept/reject, RBAC, audit,
Inherited rule, status sync, round trip from our own export, malicious/oversized file rejection."""
import io
import uuid
import zipfile
from pathlib import Path

import pytest
from openpyxl import Workbook
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent, ControlAssignment, EmassImport
from app.services import emass_import as ei
from tests.conftest import auth
from tests.test_emass_fields import FULL
from tests.test_sandbox import _signup, signup_on  # noqa: F401

FIXTURE = (Path(__file__).parent / "fixtures" / "emass" / "SYNTHETIC_ControlInfoExport.xlsx").read_bytes()


def _xlsx(rows: list[list], pre: int = 0, sheet: str = "Sheet1") -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = sheet
    for _ in range(pre):
        ws.append(["banner / notes row"])
    for r in rows:
        ws.append(r)
    b = io.BytesIO()
    wb.save(b)
    return b.getvalue()


@pytest.fixture(scope="module")
def ctx(client, signup_on):  # noqa: F811
    t = _signup(client, f"ei-{uuid.uuid4().hex[:6]}@example.com", "EI Org")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "EI System", "acronym": f"EI{uuid.uuid4().hex[:3]}", "baseline_key": "moderate",
                                                "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])  # noqa: E731
    isso = role("isso")
    base = f"/api/v1/systems/{sid}/workbench/controls"
    assert client.put(f"{base}/ac-2/emass/plan", json={"implementation_status": "Planned", **FULL}, headers=isso).status_code == 200
    assert client.put(f"{base}/ac-2/emass/risk", json={"severity": "Low"}, headers=isso).status_code == 200
    with SessionLocal() as db:
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(sid), ControlAssignment.control_id == "ia-2.1"))
        a.responsibility, a.implementation_status = "inherited", "inherited"
        db.commit()
    return {"h": isso, "sid": sid, "role": role, "base": base, "url": f"/api/v1/systems/{sid}/emass-imports"}


def _up(client, ctx, data, name="export.xlsx", h=None):
    return client.post(ctx["url"], files={"file": (name, data)}, headers=h or ctx["h"])


def test_header_detection_aliases_reordered_and_acronym_normalization():
    data = _xlsx([["Notes", None], [" slcm  FREQUENCY ", "implementationStatus", "Security Control\nAcronym".replace("Security Control\n", ""), "Criticality", "Residual Risk", "Mystery"],
                  ["Weekly", "implemented", "AC-2 (1)", "High", "low", "?"], ["monthly", "N/A", "ac-02(03)", "Low", "Very high", "?"]], pre=2)
    p = ei.parse(data)
    assert p["header_row"] == 4
    assert {f: c["col"] for f, c in p["columns"].items()} == {"slcm_frequency": "A", "implementation_status": "B", "acronym": "C", "slcm_criticality": "D",
                                                            "residual_risk_level": "E"}
    assert p["unknown_headers"] == ["Mystery"]
    assert [ei.norm_acronym(r["acronym"]) for r in p["rows"]] == ["ac-2.1", "ac-2.3"]
    assert ei.norm_acronym("AC-2(1)") == ei.norm_acronym("ac-2.1") == ei.norm_acronym("AC-02 (01)") == "ac-2.1" and ei.norm_acronym("bogus") is None
    assert ei.normalize("implementation_status", "N/A") == ("Not Applicable", None) and ei.normalize("residual_risk_level", "very HIGH")[0] == "Very High"
    assert ei.normalize("estimated_completion_date", "06/30/2027")[0].isoformat() == "2027-06-30" and ei.normalize("estimated_completion_date", "31/31/2027")[1]


def test_fixture_report_matching_and_validation(client, ctx):
    r = _up(client, ctx, FIXTURE, "SYNTHETIC_ControlInfoExport.xlsx")
    assert r.status_code == 201, r.text
    d = r.json()
    rep = d["report"]
    assert d["detection"]["header_row"] == 3 and "Compliance Status" in d["detection"]["ignored_headers"]
    assert rep["not_in_system"] == [{"row": 14, "control": "ZZ-99"}]
    assert rep["duplicates"] == [{"row": 15, "control": "AC-2", "first_row": 4}]
    inv = {(x["control"], x["field"]) for x in rep["invalid"]}
    assert inv == {("CM-6", "SLCM Frequency"), ("RA-5", "Estimated Completion Date"), ("RA-5", "Residual Risk Level"), ("SI-2", "SLCM Comments")}
    assert any(x["control"] == "IA-2(1)" and x["field"] == "Severity" for x in rep["blocked"])
    assert any(x["control"] == "AU-2" and "N/A Justification" in x["missing"] for x in rep["status_not_applied"])
    assert "AC-3" in rep["missing_from_file"] and d["status"] == "review" and len(d["sha256"]) == 64
    with SessionLocal() as db:
        imp = db.get(EmassImport, uuid.UUID(d["id"]))
        from app.services.storage.base import get_storage
        assert get_storage().get(imp.storage_key) == FIXTURE
    ctx["fx"] = d["id"]


def test_no_autosave_accept_reject_per_field_and_apply_audited(client, ctx):
    iid = ctx["fx"]
    before = client.get(f"{ctx['base']}/ac-2/emass", headers=ctx["h"]).json()["values"]
    assert before["slcm_frequency"] == "Monthly"
    u = f"{ctx['url']}/{iid}/decisions"
    assert client.put(u, json={"decisions": [{"control_id": "ac-2", "field": "slcm_frequency", "decision": "accept"},
                                             {"control_id": "ac-2", "field": "severity", "decision": "reject"}]}, headers=ctx["h"]).status_code == 200
    assert client.put(u, json={"decisions": [{"control_id": "cm-6", "field": "slcm_frequency", "decision": "accept"}]}, headers=ctx["h"]).status_code == 422
    assert client.put(u, json={"decisions": [{"control_id": "ia-2.1", "field": "severity", "decision": "accept"}]}, headers=ctx["h"]).status_code == 422
    assert client.get(f"{ctx['base']}/ac-2/emass", headers=ctx["h"]).json()["values"] == before, "decisions never save"
    d = client.put(u, json={"bulk": "accept_safe"}, headers=ctx["h"]).json()
    items = {i["control_id"]: i for i in d["items"]}
    assert items["ac-2"]["fields"]["severity"]["decision"] == "reject", "bulk accept keeps explicit rejections"
    assert items["au-2"]["fields"]["implementation_status"]["blocked"] and items["au-2"]["fields"]["implementation_status"]["decision"] is None, \
        "a status whose eMASS required fields are missing is not applied (row warning), never bulk-accepted"
    assert client.put(u, json={"decisions": [{"control_id": "au-2", "field": "implementation_status", "decision": "accept"}]}, headers=ctx["h"]).status_code == 422
    assert client.get(f"{ctx['base']}/ac-2/emass", headers=ctx["h"]).json()["values"] == before
    res = client.post(f"{ctx['url']}/{iid}/apply", headers=ctx["h"])
    assert res.status_code == 200, res.text
    out = {x["control"]: x for x in res.json()["results"]}
    assert "slcm_frequency" in out["AC-2"]["applied"] and "severity" not in out["AC-2"]["applied"]
    assert "implementation_status" not in (out.get("AU-2") or {}).get("applied", []), "required-rule violation is flagged, not saved"
    v = client.get(f"{ctx['base']}/ac-2/emass", headers=ctx["h"]).json()
    assert v["values"]["slcm_frequency"] == "Weekly" and v["values"]["severity"] == "Low" and v["assisted"]["slcm_frequency"]["source"] == "emass_import"
    assert client.get(f"{ctx['base']}/au-2/emass", headers=ctx["h"]).json()["implementation_status"] != "Not Applicable"
    with SessionLocal() as db:
        aid = str(db.scalar(select(ControlAssignment.id).where(ControlAssignment.system_id == uuid.UUID(ctx["sid"]), ControlAssignment.control_id == "ac-2")))
        ev = db.scalar(select(AuditEvent).where(AuditEvent.entity_id == aid, AuditEvent.action == "emass.plan_updated").order_by(AuditEvent.occurred_at.desc()))
        assert ev.before["slcm_frequency"] == "Monthly" and ev.after["slcm_frequency"] == "Weekly"
        assert ev.details["source"].startswith("eMASS import Control Information SYNTHETIC_ControlInfoExport.xlsx (sha256 ") and ev.details["import_id"] == iid
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.entity_id == iid, AuditEvent.action == "emass.import_applied"))
    assert client.post(f"{ctx['url']}/{iid}/apply", headers=ctx["h"]).status_code == 409
    h = client.get(ctx["url"], headers=ctx["h"]).json()["items"]
    assert h[0]["id"] == iid and h[0]["status"] == "applied" and h[0]["counts"]["applied_fields"] >= 1


def test_status_import_uses_single_status_sync_and_inherited_needs_record(client, ctx):
    rows = [["Control Acronym", "Implementation Status", *[ei.ef.FIELD_META[k][0] for k in FULL]],
            ["AC-2", "Implemented", *FULL.values()], ["AC-3", "Inherited"]]
    d = _up(client, ctx, _xlsx(rows)).json()
    it = {i["control_id"]: i for i in d["items"]}
    assert it["ac-3"]["fields"]["implementation_status"]["blocked"].startswith("Inherited requires an inheritance record")
    client.put(f"{ctx['url']}/{d['id']}/decisions", json={"decisions": [{"control_id": "ac-2", "field": "*", "decision": "accept"}]}, headers=ctx["h"])
    assert client.post(f"{ctx['url']}/{d['id']}/apply", headers=ctx["h"]).status_code == 200
    det = client.get(f"{ctx['base']}/ac-2", headers=ctx["h"]).json()
    assert det["assignment"]["implementation_status"] == "implemented"


def test_rbac_view_only_for_sca(client, ctx):
    sca = ctx["role"]("sca")
    assert _up(client, ctx, FIXTURE, h=sca).status_code == 403
    d = _up(client, ctx, FIXTURE).json()
    v = client.get(f"{ctx['url']}/{d['id']}", headers=sca)
    assert v.status_code == 200 and v.json()["can_apply"] is False
    assert client.put(f"{ctx['url']}/{d['id']}/decisions", json={"bulk": "accept_safe"}, headers=sca).status_code == 403
    assert client.post(f"{ctx['url']}/{d['id']}/apply", headers=sca).status_code == 403
    assert client.post(f"{ctx['url']}/{d['id']}/discard", headers=ctx["h"]).json()["status"] == "discarded"
    assert client.put(f"{ctx['url']}/{d['id']}/decisions", json={"bulk": "accept_safe"}, headers=ctx["h"]).status_code == 409


def test_round_trip_from_our_own_export(client, ctx):
    x = client.get(f"/api/v1/systems/{ctx['sid']}/emass/implementation-plan.xlsx", headers=ctx["h"]).content
    d = _up(client, ctx, x, "own-export.xlsx").json()
    assert d["detection"]["header_row"] == 2 and d["report"]["not_in_system"] == [] and d["report"]["matched"] == d["detection"]["data_rows"]
    assert d["report"]["invalid"] == [] and d["counts"]["changed_fields"] == 0, "re-importing our own export proposes no changes"


@pytest.mark.parametrize("name,data,code", [
    ("evil.xlsx", b"MZ\x90\x00not a zip", 422),
    ("legacy.xlsx", b"\xd0\xcf\x11\xe0" + b"\x00" * 100, 422),
    ("notes.txt", b"PK\x03\x04", 422),
    ("big.xlsx", b"PK" + b"\x00" * (10 * 1024 * 1024), 413),
])
def test_rejects_malicious_or_oversized(client, ctx, name, data, code):
    assert _up(client, ctx, data, name).status_code == code


def test_rejects_zip_without_workbook_and_header_less_sheet(client, ctx):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("xl/vbaProject.bin", b"\x00macro")
    assert _up(client, ctx, b.getvalue(), "macro.xlsm").status_code == 422
    r = _up(client, ctx, _xlsx([["a", "b"], [1, 2]]))
    assert r.status_code == 422 and "Control Acronym" in r.json()["detail"]
    rows = [["Control Acronym", "Severity"]] + [[f"AC-{i}", "Low"] for i in range(ei.MAX_ROWS + 2)]
    assert _up(client, ctx, _xlsx(rows)).status_code == 422
