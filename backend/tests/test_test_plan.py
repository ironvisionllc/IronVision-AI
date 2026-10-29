"""Import Test Plan (eMASS Test Results / Assessment Procedures): format recognition, AP/CCI preservation, required columns, invalid AP/CCI,
unmatched / not-selected controls, duplicates (in-file and against existing), 403 with reason, preview saves nothing, import → rows in the TR workspace."""
import uuid
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import CciControlMap, ControlAssignment, TrRow, TrWorkbook
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

FX = Path(__file__).parent / "fixtures" / "test_plan"


@pytest.fixture(scope="module")
def ctx(client, signup_on):  # noqa: F811
    t = _signup(client, f"tp-{uuid.uuid4().hex[:6]}@example.com", "TP Org")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "Plan System", "acronym": "TPS", "baseline_key": "moderate", "categorization_mode": "fips199",
                                                "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])  # noqa: E731
    return {"sid": sid, "isso": role("isso"), "role": role}


def _post(client, ctx, name, step="preview", data=None, h=None):
    return client.post(f"/api/v1/systems/{ctx['sid']}/tr/test-plan/{step}", files={"file": (name, data if data is not None else (FX / name).read_bytes())},
                       headers=h or ctx["isso"])


def _count():
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(TrWorkbook))


@pytest.mark.parametrize("name", ["SYNTHETIC_TestPlan_valid.xlsx", "SYNTHETIC_TestPlan_valid.csv"])
def test_preview_recognises_format_and_saves_nothing(client, ctx, name):
    n = _count()
    r = _post(client, ctx, name)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["detected"]["type"] == "test_results" and "compatibility pending verification" in p["detected"]["label"]
    assert ("CSV" in p["format"]) == name.endswith(".csv")
    assert p["counts"]["rejected"] == 0 and p["counts"]["accepted"] == (4 if name.endswith(".csv") else 3)
    assert {(a["ap_acronym"], a["cci"]) for a in p["accepted"]} >= {("AC-2.1", "CCI-000010"), ("AC-3.1", "CCI-000213")}, "AP/CCI preserved"
    assert {c["role"] for c in p["columns"]} >= {"AP Acronym", "CCI", "Assessment Procedures"}
    assert _count() == n, "preview never saves"


def test_unsupported_and_corrupt_files(client, ctx):
    r = _post(client, ctx, "INVALID_TestPlan.docx")
    assert r.status_code == 422 and "Unsupported format .docx" in r.json()["detail"]
    r = _post(client, ctx, "INVALID_TestPlan_corrupt.xlsx")
    assert r.status_code == 422 and "not a valid Excel workbook" in r.json()["detail"]


def test_missing_required_columns_are_named(client, ctx):
    r = _post(client, ctx, "INVALID_TestPlan_missing_columns.xlsx")
    assert r.status_code == 422
    d = r.json()["detail"]
    assert d["missing_columns"] == ["AP Acronym", "CCI"] and "Missing required column(s): AP Acronym, CCI" in d["message"]


def test_every_rejected_row_listed_with_reason(client, ctx):
    p = _post(client, ctx, "INVALID_TestPlan_rows.xlsx").json()
    rej = {r["row"]: r["reason"] for r in p["rejected"]}
    assert [a["row"] for a in p["accepted"]] == [3]
    assert rej[4].startswith("Duplicate procedure: same AP Acronym and CCI as row 3")
    assert rej[5].startswith("Invalid AP Acronym “XX_BAD”")
    assert rej[6].startswith("Invalid CCI “CCI-ABC”")
    assert "ZZ-9" in rej[7] and "not in the control catalog" in rej[7]
    assert rej[8] == "AP Acronym is empty (required)"
    assert len(rej) == 5


def test_control_not_selected_for_system_is_rejected(client, ctx):
    from openpyxl import Workbook
    import io
    with SessionLocal() as db:
        have = set(db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == uuid.UUID(ctx["sid"]))))
        ctl, cci = next((c, i) for c, i in db.execute(select(CciControlMap.control_id, CciControlMap.cci_id).order_by(CciControlMap.cci_id))
                        if c not in have and "." not in c)
    wb = Workbook()
    wb.active.append(["AP Acronym", "CCI"])
    wb.active.append([f"{ctl.upper()}.1", cci])
    b = io.BytesIO()
    wb.save(b)
    p = _post(client, ctx, "x.xlsx", data=b.getvalue()).json()
    assert p["rejected"][0]["reason"] == f"{ctl.upper()} is not selected for this system (unmatched control)"


def test_import_creates_workbook_rows_then_duplicates_against_existing(client, ctx):
    r = _post(client, ctx, "INVALID_TestPlan_rows.xlsx", "import")
    assert r.status_code == 201, r.text
    wb = r.json()
    assert wb["status"] == "mapped" and wb["preview"]["counts"] == {"rows": 6, "accepted": 1, "rejected": 5, "unchanged": 0, "needs_mapping_review": 0}
    rows = client.get(f"/api/v1/tr/workbooks/{wb['id']}/rows", headers=ctx["isso"]).json()["items"]
    assert [(x["row"], x["ap_acronym"], x["cci_id"], x["state"]) for x in rows] == [(3, "AC-2.1", "CCI-000010", "missing")], "only accepted rows; nothing approved"
    listed = client.get(f"/api/v1/systems/{ctx['sid']}/tr/workbooks", headers=ctx["isso"]).json()
    assert any(w["id"] == wb["id"] for w in listed), "visible in the Test Results workspace"
    p = _post(client, ctx, "SYNTHETIC_TestPlan_valid.xlsx").json()
    same = [x for x in p["unchanged"] if x["ap_acronym"] == "AC-2.1"]
    assert same and "Already in Test Results workbook" in same[0]["reason"] and "row 3" in same[0]["reason"]
    assert not [x for x in p["rejected"] if x["ap_acronym"] == "AC-2.1"], "a procedure already present is unchanged, not an error"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(TrRow).where(TrRow.workbook_id == uuid.UUID(wb["id"]))) == 1


def test_import_with_no_valid_rows_is_refused(client, ctx):
    from openpyxl import Workbook
    import io
    wb = Workbook()
    wb.active.append(["AP Acronym", "CCI"])
    wb.active.append(["BAD", "CCI-000010"])
    b = io.BytesIO()
    wb.save(b)
    r = _post(client, ctx, "bad.xlsx", "import", data=b.getvalue())
    assert r.status_code == 422 and r.json()["detail"]["rejected"][0]["row"] == 2


def test_wrong_report_type_points_to_emass_import(client, ctx):
    data = (Path(__file__).parent / "fixtures" / "emass" / "SYNTHETIC_poam.xlsx").read_bytes()
    r = _post(client, ctx, "poam.xlsx", data=data)
    assert r.status_code == 422 and "POA&M" in r.json()["detail"] and "Import from eMASS" in r.json()["detail"]


def test_read_only_role_gets_403_with_reason(client, ctx):
    r = _post(client, ctx, "SYNTHETIC_TestPlan_valid.xlsx", h=ctx["role"]("leadership_viewer"))
    assert r.status_code == 403
    d = r.json()["detail"]
    assert d["permission"] == "ingest.upload" and "Importing a Test Plan needs the ingest.upload permission" in d["message"] and d["roles"]
