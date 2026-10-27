"""Import Center: detection routing for every type, RBAC per type, unified history (tenant isolation), retry of failed imports."""
import json
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import IngestRun, Job
from app.services import emass_migration as em
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

FX = Path(__file__).parent / "fixtures"
FIPS = {"baseline_key": "moderate", "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}], "processes_pii": False}
CKL = b'<?xml version="1.0"?><CHECKLIST><ASSET><HOST_NAME>syn-01</HOST_NAME></ASSET><STIGS><iSTIG><STIG_INFO/><VULN><STATUS>Open</STATUS></VULN></iSTIG></STIGS></CHECKLIST>'
XCCDF = b'<?xml version="1.0"?><Benchmark xmlns="http://checklists.nist.gov/xccdf/1.2"><TestResult><rule-result idref="r1"><result>pass</result></rule-result></TestResult></Benchmark>'
NESSUS = b'<?xml version="1.0"?><NessusClientData_v2><Report><ReportHost name="h"><ReportItem pluginID="1" severity="2"/></ReportHost></Report></NessusClientData_v2>'
CSV = b"Plugin ID,Host,Name,Risk\n19506,syn-01,Scan Info,None\n"


def _emass(client, h, typ):
    return client.get(f"/api/v1/emass-imports/samples/{typ}", headers=h).content


@pytest.fixture(scope="module")
def ctx(client, signup_on):  # noqa: F811
    t = _signup(client, f"ic-{uuid.uuid4().hex[:6]}@example.com", "IC Org")
    h = auth(t["access_token"])
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])  # noqa: E731
    sid = client.post("/api/v1/systems", json={"name": "IC Target", "acronym": "ICT" + uuid.uuid4().hex[:3], **FIPS}, headers=h).json()["id"]
    return {"sid": sid, "h": h, "role": role, "isso": role("isso")}


def _detect(client, ctx, name, data, h=None):
    r = client.post("/api/v1/import-center/detect", files={"file": (name, data)}, data={"system_id": ctx["sid"]}, headers=h or ctx["isso"])
    assert r.status_code == 200, r.text
    return r.json()


def test_detection_routes_every_type(client, ctx):
    cases = {
        "policy": ("ac_policy.docx", (FX / "policies" / "ac_policy_raven_demo.docx").read_bytes()),
        "ckl": ("syn.ckl", CKL), "cklb": ("syn.cklb", json.dumps({"stigs": []}).encode()), "xccdf": ("syn-xccdf.xml", XCCDF),
        "nessus_xml": ("syn.nessus", NESSUS), "nessus_csv": ("acas.csv", CSV), "sarif": ("code.sarif", json.dumps({"runs": []}).encode()),
        "control_information": ("plan.xlsx", (FX / "emass" / "IV_eMASS_implementation_plan_user_edited.xlsx").read_bytes()),
        "test_results": ("tr.xlsx", (FX / "emass" / "BLANK_TRExport.xlsx").read_bytes()),
        "hwsw": ("hwsw.xlsm", (FX / "emass" / "HWSWList_Template-eMASS3.xlsm").read_bytes()),
        "slcm": ("slcm.xlsx", em.sample("slcm")), "ppsm": ("ppsm.xlsx", em.sample("ppsm")), "categorization": ("cat.xlsx", em.sample("categorization")),
        "system_details": ("sd.xlsx", _emass(client, ctx["isso"], "system_details")), "poam": ("poam.xlsx", _emass(client, ctx["isso"], "poam")),
    }
    for typ, (name, data) in cases.items():
        d = _detect(client, ctx, name, data)
        assert d["type"] == typ, (typ, d)
        assert d["label"] and d["step"] and d["dest"] and d["endpoint"], d
    plan = _detect(client, ctx, *cases["control_information"])
    assert plan["record_count"] == 423 and plan["step"] == "Implement"
    tr = _detect(client, ctx, *cases["test_results"])
    assert "test_plan" in tr["candidates"], "Test Plan is offered as manual override for the TR layout"
    assert _detect(client, ctx, *cases["ckl"])["record_count"] == 1


def test_unrecognised_file_explained_not_dropped(client, ctx):
    d = _detect(client, ctx, "notes.bin", b"\x00\x01binary")
    assert d["type"] is None and "Supported:" in d["message"]
    d = _detect(client, ctx, "random.csv", b"a,b,c\n1,2,3\n")
    assert d["type"] is None and "Supported:" in d["message"]


def test_rbac_per_type(client, ctx):
    v = ctx["role"]("leadership_viewer")
    t = {x["key"]: x for x in client.get("/api/v1/import-center/types", params={"system_id": ctx["sid"]}, headers=v).json()["types"]}
    assert not t["control_information"]["allowed"] and "lacks" in t["control_information"]["reason"]
    t2 = {x["key"]: x for x in client.get("/api/v1/import-center/types", params={"system_id": ctx["sid"]}, headers=ctx["isso"]).json()["types"]}
    assert t2["ckl"]["allowed"] and t2["control_information"]["allowed"]
    d = _detect(client, ctx, "syn.ckl", CKL, h=v)
    assert d["type"] == "ckl" and d["allowed"] is False


def test_history_unified_tenant_isolated_and_retry(client, ctx):
    sid = ctx["sid"]
    assert client.post(f"/api/v1/systems/{sid}/uploads", files={"file": ("syn.ckl", CKL)}, headers=ctx["isso"]).status_code in (200, 201, 202)
    assert client.post("/api/v1/emass-imports", files={"file": ("slcm.xlsx", em.sample("slcm"))}, data={"system_id": sid}, headers=ctx["isso"]).status_code == 201
    items = client.get("/api/v1/import-center/history", params={"system_id": sid}, headers=ctx["isso"]).json()["items"]
    kinds = {i["kind"] for i in items}
    assert {"ingest", "emass"} <= kinds and all(i["sha256"] and i["file_name"] and i["status"] for i in items)
    org = client.get("/api/v1/import-center/history", headers=ctx["isso"]).json()["items"]
    assert {i["id"] for i in items} <= {i["id"] for i in org}
    t = _signup(client, f"ic2-{uuid.uuid4().hex[:6]}@example.com", "IC Other")
    oh = auth(t["access_token"])
    assert client.get("/api/v1/import-center/history", params={"system_id": sid}, headers=oh).status_code in (403, 404)
    assert sid not in json.dumps(client.get("/api/v1/import-center/history", headers=oh).json())
    run_id = next(i["id"] for i in items if i["kind"] == "ingest")
    with SessionLocal() as db:
        r = db.get(IngestRun, uuid.UUID(run_id))
        r.status, r.errors = "failed", ["SYNTHETIC failure"]
        db.commit()
    assert client.post(f"/api/v1/import-center/retry/ingest/{run_id}", headers=oh).status_code == 404
    r = client.post(f"/api/v1/import-center/retry/ingest/{run_id}", headers=ctx["isso"])
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.get(IngestRun, uuid.UUID(run_id)).status == "queued"
        assert db.scalar(select(Job).where(Job.id == uuid.UUID(r.json()["job_id"]))).job_type == "ingest.process"
    assert client.post(f"/api/v1/import-center/retry/ingest/{run_id}", headers=ctx["isso"]).status_code == 409


POLICY_TXT = b"""ACCESS CONTROL POLICY
1. Purpose
This policy establishes the access control requirements (AC-2, AC-3).
2. Scope
All system users shall be uniquely identified. Accounts must be reviewed quarterly and the ISSO shall disable inactive accounts.
"""


def test_txt_policy_content_classified_as_policy(client, ctx):
    d = _detect(client, ctx, "ac_policy.txt", POLICY_TXT)
    assert d["type"] == "policy" and d["policy_score"] >= 3 and "NIST SP 800-53 control IDs" in d["signals"]


def test_txt_without_policy_content_not_recognised_with_override(client, ctx):
    d = _detect(client, ctx, "notes.txt", b"grocery list\neggs\nmilk\nbread\ncall the plumber on tuesday\n")
    assert d["type"] is None and "Not recognised as a supported import" in d["message"] and "Supported:" in d["message"]
    assert d["override"] == "policy" and d["override_label"] == "Import as policy anyway"
