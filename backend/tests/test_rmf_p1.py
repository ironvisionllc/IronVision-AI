"""RMF Accuracy release – Phase 1: registration roles (1), authorization type moved to Authorize (3), Yes/No/Unknown storage (8),
parameter comparison CSV (5)."""
import csv
import io
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent, ControlAssignment, OdpValue, Policy, System
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

SYS = {"baseline_key": "moderate", "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}


@pytest.fixture(scope="module")
def org(client, signup_on):  # noqa: F811
    t = _signup(client, f"p1-{uuid.uuid4().hex[:6]}@example.com", "P1 Org")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "P1 System", "acronym": f"P1{uuid.uuid4().hex[:3]}", **SYS}, headers=h).json()["id"]
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])  # noqa: E731
    return {"h": h, "sid": sid, "role": role}


def test_registration_role_picker_excludes_three_roles(client, org):
    roles = {r["key"]: r for r in client.get("/api/v1/reference/rmf", headers=org["h"]).json()["key_roles"]}
    assert {k for k, r in roles.items() if not r["registration"]} == {"aodr", "ccp", "user_rep"}
    assert roles["ao"]["registration"] and roles["isso"]["registration"]
    for k in ("aodr", "ccp", "user_rep"):
        r = client.post("/api/v1/systems", json={"name": "Bad", "acronym": "BAD", **SYS, "key_roles": {k: {"name": "Pat Doe"}}}, headers=org["h"])
        assert r.status_code == 422 and ("cannot be assigned at system registration" in r.json()["detail"] or "isn't assigned" in r.json()["detail"])


def test_authorization_type_moved_to_authorize(client, org):
    r = client.post("/api/v1/systems", json={"name": "Bad", "acronym": "BAD", **SYS, "authorization_type": "ATO"}, headers=org["h"])
    assert r.status_code == 422 and "Authorize" in r.json()["detail"]
    url = f"/api/v1/systems/{org['sid']}/authorization-strategy"
    assert client.put(url, json={"authorization_type": "ATO", "justification": "Initial strategy"}, headers=org["role"]("sca")).status_code == 403
    ok = client.put(url, json={"authorization_type": "ATO", "justification": "Initial strategy"}, headers=org["role"]("issm"))
    assert ok.status_code == 200 and ok.json()["authorization_type"] == "ATO"
    assert client.get(f"/api/v1/systems/{org['sid']}/authorize", headers=org["h"]).json()["authorization_type"] == "ATO"
    with SessionLocal() as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "system.authorization_strategy_updated", AuditEvent.entity_id == org["sid"]))


def test_pii_unknown_is_distinct_from_no_and_unanswered(client, org):
    base = {"acronym": f"PI{uuid.uuid4().hex[:3]}", **SYS}
    unk = client.post("/api/v1/systems", json={"name": "Unknown PII", **base, "pta": {"pii_status": "unknown"}}, headers=org["h"]).json()
    no = client.post("/api/v1/systems", json={"name": "No PII", **base, "processes_pii": False, "pta": {"pii_status": "no"}}, headers=org["h"]).json()
    blank = client.post("/api/v1/systems", json={"name": "Blank PII", **base}, headers=org["h"]).json()
    assert unk["processes_pii"] is None and unk["pta"]["pii_status"] == "unknown"
    assert no["processes_pii"] is False and blank["processes_pii"] is None and not (blank.get("pta") or {}).get("pii_status")


def _rows(text: str) -> list[list[str]]:
    assert text.startswith("\ufeff"), "UTF-8 BOM for Excel"
    return list(csv.reader(io.StringIO(text.lstrip("\ufeff"))))


def test_parameter_comparison_populated_filtered_and_equal_to_screen(client, org):
    sid = org["sid"]
    with SessionLocal() as db:
        assert db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(sid), ControlAssignment.control_id == "ac-7"))
        db.add(OdpValue(system_id=uuid.UUID(sid), control_id="ac-7", parameter="ac-07_odp.01", value="3", source="SSP", approved_by="ISSM (synthetic)"))
        db.add(Policy(org_id=db.get(System, uuid.UUID(sid)).org_id, policy_key=f"p1-{uuid.uuid4().hex[:6]}", title="P1 Access Policy", version=1, system_ids=[sid],
                      analysis={"values": [{"control_id": "ac-7", "parameter": "ac-07_odp.01", "value": "5", "quote": "five attempts"}]}))
        db.commit()
    screen = client.get(f"/api/v1/systems/{sid}/parameter-comparison", params={"limit": 500}, headers=org["h"]).json()
    assert screen["total"] > 50 and "Baseline value" in screen["omitted_columns"]
    full = _rows(client.get(f"/api/v1/systems/{sid}/parameters.csv", headers=org["h"]).text)
    assert full[0][:4] == ["Control ID", "Enhancement", "Parameter ID", "Parameter description"] and len(full) - 1 == screen["total"]
    ac7 = next(r for r in screen["items"] if r["parameter_id"] == "ac-07_odp.01")
    assert ac7["status"] == "conflict" and ac7["effective_value"] == "3" and ac7["policy_value"] == "5"
    fam = client.get(f"/api/v1/systems/{sid}/parameter-comparison", params={"family": "ac", "limit": 500}, headers=org["h"]).json()
    fcsv = _rows(client.get(f"/api/v1/systems/{sid}/parameters.csv", params={"family": "ac"}, headers=org["h"]).text)
    assert 0 < fam["total"] < screen["total"] and len(fcsv) - 1 == fam["total"] and all(r[0].startswith("AC-") for r in fcsv[1:])
    st = _rows(client.get(f"/api/v1/systems/{sid}/parameters.csv", params={"status": "conflict"}, headers=org["h"]).text)
    assert len(st) == 2 and st[1][2] == "ac-07_odp.01"


def test_parameter_csv_empty_injection_and_scope(client, org):
    sid = org["sid"]
    e = client.get(f"/api/v1/systems/{sid}/parameters.csv", params={"q": "no-such-parameter-zz"}, headers=org["h"])
    assert e.status_code == 204 and e.content == b"" and "No parameter rows match" in e.headers["x-empty-reason"]
    with SessionLocal() as db:
        db.add(OdpValue(system_id=uuid.UUID(sid), control_id="ac-11", parameter="ac-11_odp.01", value="=HYPERLINK(\"http://x\")", source="@evil", approved_by="+me"))
        db.commit()
    rows = _rows(client.get(f"/api/v1/systems/{sid}/parameters.csv", params={"q": "ac-11_odp.01"}, headers=org["h"]).text)
    r = rows[1]
    assert r[5] == "'=HYPERLINK(\"http://x\")" and r[9].startswith("System ODP: @evil") and r[11] == "'+me"
    other = _signup(client, f"p1o-{uuid.uuid4().hex[:6]}@example.com", "Other Org")
    oh = auth(other["access_token"])
    assert client.get(f"/api/v1/systems/{sid}/parameters.csv", headers=oh).status_code in (403, 404)
    assert client.get(f"/api/v1/systems/{sid}/parameter-comparison", headers=oh).status_code in (403, 404)
    with SessionLocal() as db:
        p = Policy(org_id=db.get(System, uuid.UUID(sid)).org_id, policy_key=f"e-{uuid.uuid4().hex[:6]}", title="Empty Policy", version=1, system_ids=[], analysis={"values": []})
        db.add(p)
        db.commit()
        pid = p.id
    assert client.get(f"/api/v1/policies/{pid}/parameters.csv", headers=org["h"]).status_code == 204
