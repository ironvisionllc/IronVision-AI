"""SME section 5: inheritance – bulk set, CRM import (CSV/XLSX, mapping, preview, row errors, apply + audit), provider expiry warnings."""
import io
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401


@pytest.fixture(scope="module")
def ws(client, signup_on):  # noqa: F811
    t = _signup(client, f"s5-{uuid.uuid4().hex[:6]}@example.com", "S5 Org")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "Section Five", "acronym": "S5", "baseline_key": "low"}, headers=h).json()["id"]
    p = client.post("/api/v1/providers", headers=h, json={"name": "Example Cloud Platform", "package": "ECP GovCloud package", "authorization_type": "FedRAMP P-ATO",
                                                        "package_expiration": (date.today() + timedelta(days=30)).isoformat()})
    assert p.status_code == 201, p.text
    return {"h": h, "sid": sid, "pid": p.json()["id"]}


def test_provider_record_and_expiry_warning(client, ws):
    d = client.get(f"/api/v1/systems/{ws['sid']}/inheritance", headers=ws["h"]).json()
    p = next(x for x in d["providers"] if x["id"] == ws["pid"])
    assert p["authorization_type"] == "FedRAMP P-ATO" and p["expiry"]["status"] == "expiring" and "30 day" in p["expiry"]["message"]
    client.patch(f"/api/v1/providers/{ws['pid']}", headers=ws["h"], json={"name": "Example Cloud Platform", "package_expiration": (date.today() - timedelta(days=2)).isoformat()})
    d = client.get(f"/api/v1/systems/{ws['sid']}/inheritance", headers=ws["h"]).json()
    assert next(x for x in d["providers"] if x["id"] == ws["pid"])["expiry"]["status"] == "expired"
    client.patch(f"/api/v1/providers/{ws['pid']}", headers=ws["h"], json={"name": "Example Cloud Platform", "package_expiration": (date.today() + timedelta(days=400)).isoformat()})


def test_bulk_inheritance(client, ws):
    url = f"/api/v1/systems/{ws['sid']}/inheritance/bulk"
    assert client.post(url, headers=ws["h"], json={"control_ids": ["pe-2", "pe-3"], "responsibility": "inherited"}).status_code == 422
    r = client.post(url, headers=ws["h"], json={"control_ids": ["pe-2", "PE-3", "zz-9"], "responsibility": "inherited", "provider_id": ws["pid"]}).json()
    assert r["updated"] == ["pe-2", "pe-3"] and r["not_assigned"] == ["zz-9"]
    d = client.get(f"/api/v1/systems/{ws['sid']}/inheritance", headers=ws["h"]).json()
    row = next(x for x in d["shared"] if x["control_id"] == "pe-3")
    assert row["responsibility"] == "inherited" and row["provider_name"] == "Example Cloud Platform"


CSV = (b"Control,Type,CSP Responsibility,Customer Responsibility\n"
       b"AC-2,shared,Provider manages admin accounts,System manages app users\n"
       b"sc-12,Fully Inherited,Provider manages keys,\n"
       b"au-6,maybe,,\n"
       b"ia-2,shared,Provider MFA only,\n")


def _xlsx(rows):
    import zipfile
    from xml.sax.saxutils import escape

    cells = "".join(f'<row r="{i + 1}">' + "".join(f'<c r="{chr(65 + j)}{i + 1}" t="inlineStr"><is><t>{escape(v)}</t></is></c>' for j, v in enumerate(r) if v)
                    + "</row>" for i, r in enumerate(rows))
    m = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/workbook.xml", f'<?xml version="1.0"?><workbook xmlns="{m}"/>')
        z.writestr("xl/worksheets/sheet1.xml", f'<?xml version="1.0"?><worksheet xmlns="{m}"><sheetData>{cells}</sheetData></worksheet>')
    return buf.getvalue()


def _f(name, data):
    return {"file": (name, data, "application/octet-stream")}


def test_crm_preview_mapping_and_row_errors(client, ws):
    r = client.post(f"/api/v1/providers/{ws['pid']}/crm/preview", headers=ws["h"], data={"system_id": ws["sid"]}, files=_f("crm.csv", CSV))
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["mapping"]["control_id"] == "Control" and d["mapping"]["responsibility"] == "Type"
    assert d["mapping"]["provider_responsibility"] == "CSP Responsibility" and d["mapping"]["customer_responsibility"] == "Customer Responsibility"
    rows = {x["control_id"]: x for x in d["rows"]}
    assert rows["sc-12"]["responsibility"] == "inherited" and not rows["sc-12"]["errors"]
    assert rows["au-6"]["errors"] and "not inherited, shared or system" in rows["au-6"]["errors"][0]
    assert rows["ia-2"]["errors"] and "both provider and customer" in rows["ia-2"]["errors"][0]
    assert rows["ac-2"]["change"] == "system → shared" and d["summary"]["errors"] == 2
    bad = client.post(f"/api/v1/providers/{ws['pid']}/crm/preview", headers=ws["h"], data={"system_id": ws["sid"], "mapping": '{"control_id":"Control"}'},
                      files=_f("crm.csv", CSV)).json()
    assert bad["missing_columns"]


def test_crm_xlsx_apply_audited(client, ws):
    buf = _xlsx([["control_id", "responsibility", "provider_responsibility", "customer_responsibility"],
                 ["ac-2", "shared", "Provider manages admin accounts", "System manages app users"], ["sc-12", "inherited", "Provider manages keys", ""],
                 ["bad", "nope", "", ""]])
    r = client.post(f"/api/v1/providers/{ws['pid']}/crm/apply", headers=ws["h"], data={"system_id": ws["sid"]}, files=_f("crm.xlsx", buf))
    assert r.status_code == 200, r.text
    assert r.json()["skipped_errors"] == 1 and r.json()["controls_updated"] >= 1
    d = client.get(f"/api/v1/systems/{ws['sid']}/inheritance", headers=ws["h"]).json()
    ac2 = next(x for x in d["shared"] if x["control_id"] == "ac-2")
    assert ac2["responsibility"] == "shared" and ac2["system_responsibility"] == "System manages app users"
    with SessionLocal() as db:
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == "provider.crm_applied", AuditEvent.entity_id == ws["pid"]))


def test_sample_crm_is_labelled(client, ws):
    r = client.get("/api/v1/crm/sample.csv", headers=ws["h"])
    assert r.status_code == 200 and "SAMPLE" in r.text and "control_id,responsibility" in r.text
