"""SME section 3: RMF 7 steps – step status/next action, Prepare roles, SP 800-60 categorization (high-water mark), Select (baseline/overlays/tailoring)."""
import uuid

import pytest

from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401


@pytest.fixture(scope="module")
def ws(client, signup_on):  # noqa: F811
    t = _signup(client, f"s3-{uuid.uuid4().hex[:6]}@example.com", "S3 Org")
    h = auth(t["access_token"])
    body = {"name": "Section Three System", "acronym": "S3S", "baseline_key": "low", "categorization_mode": "fips199",
            "information_types": [{"id": "C.2.1.1"}, {"id": "D.16.3"}]}
    r = client.post("/api/v1/systems", json=body, headers=h)
    assert r.status_code == 201, r.text
    return {"h": h, "sid": r.json()["id"], "user": t["user"]}


def test_info_type_catalog_is_complete_and_sourced(client, ws):
    d = client.get("/api/v1/reference/info-types", headers=ws["h"]).json()
    assert "800-60" in d["source"] and len(d["types"]) >= 165
    ids = {t["id"]: t for t in d["types"]}
    assert ids["C.2.1.1"]["name"] == "Corrective Action" and (ids["C.2.1.1"]["c"], ids["C.2.1.1"]["i"], ids["C.2.1.1"]["a"]) == ("Low", "Low", "Low")
    assert all(t["c"] in ("Low", "Moderate", "High", "N/A") for t in d["types"])


def test_high_water_mark_and_adjust_requires_rationale(client, ws):
    p = client.post("/api/v1/reference/categorize", json={"information_types": [{"id": "C.2.1.1"}, {"id": "D.16.3"}]}, headers=ws["h"]).json()
    assert (p["c"], p["i"], p["a"], p["overall"], p["baseline"]) == ("Moderate", "Moderate", "Moderate", "Moderate", "moderate")
    assert any("high-water" in s for s in p["steps"])
    bad = client.post("/api/v1/reference/categorize", json={"information_types": [{"id": "C.2.1.1", "c": "High"}]}, headers=ws["h"]).json()
    assert bad["errors"] and "rationale" in bad["errors"][0]
    ok = client.post("/api/v1/reference/categorize", json={"information_types": [{"id": "C.2.1.1", "c": "High", "rationale": "Contains sensitive audit data"}]},
                     headers=ws["h"]).json()
    assert not ok["errors"] and ok["overall"] == "High"
    cn = client.post("/api/v1/reference/categorize", json={"mode": "cnssi1253", "information_types": [{"id": "C.2.1.1"}], "cia": {"c": "High", "i": "Moderate", "a": "Low"}},
                     headers=ws["h"]).json()
    assert (cn["c"], cn["i"], cn["a"]) == ("High", "Moderate", "Low")


def test_registration_computes_categorization_and_steps(client, ws):
    s = client.get(f"/api/v1/systems/{ws['sid']}", headers=ws["h"]).json()
    assert s["categorization"] == "moderate" and s["categorization_detail"]["steps"]
    st = client.get(f"/api/v1/systems/{ws['sid']}/rmf-steps", headers=ws["h"]).json()
    assert [x["label"] for x in st["steps"]] == ["Prepare", "Categorize", "Select", "Implement", "Assess", "Authorize", "Monitor"]
    assert all(x["status"] in ("not_started", "needs_attention", "complete") and x["criteria"] for x in st["steps"])
    sel = next(x for x in st["steps"] if x["key"] == "select")
    assert sel["status"] == "needs_attention" and "baseline is Low" in sel["summary"]
    assert st["next_action"]["link"] == "/rmf/prepare"


def test_prepare_roles_users_and_placeholders(client, ws):
    r = client.put(f"/api/v1/systems/{ws['sid']}/prepare", headers=ws["h"], json={"roles": {
        "isso": {"user_id": ws["user"]["id"]}, "system_owner": {"name": "Pat Owner", "email": "pat@example.mil"}, "issm": {"name": "Ina Manager"},
        "ao": {"name": "Alex AO"}, "sca": {"name": "Sam Assessor"}}})
    assert r.status_code == 200, r.text
    roles = r.json()["roles"]
    assert "placeholder" in roles["system_owner"]["display"] and roles["isso"]["display"]
    prep = client.get(f"/api/v1/systems/{ws['sid']}/rmf-steps", headers=ws["h"]).json()["steps"][0]
    assert prep["status"] == "complete"


def test_categorize_save_flags_select_and_privacy(client, ws):
    r = client.put(f"/api/v1/systems/{ws['sid']}/categorization", headers=ws["h"], json={
        "information_types": [{"id": "C.2.1.1"}, {"id": "D.16.3"}], "mission_criticality": "ME", "operating_environment": "cloud_iaas",
        "environment_detail": {"csp": "Example CSP", "impact_level": "IL4"}, "processes_pii": True, "pta": {"pii_types": "names"}})
    assert r.status_code == 200, r.text
    assert any("baseline" in a for a in r.json()["select_actions"]) and any("privacy" in a for a in r.json()["select_actions"])
    cat = next(x for x in client.get(f"/api/v1/systems/{ws['sid']}/rmf-steps", headers=ws["h"]).json()["steps"] if x["key"] == "categorize")
    assert cat["status"] == "complete"


def test_select_baseline_overlay_tailoring_counts_reconcile(client, ws):
    sid, h = ws["sid"], ws["h"]
    low = client.get(f"/api/v1/systems/{sid}/select", headers=h).json()["counts"]["assigned"]
    r = client.post(f"/api/v1/systems/{sid}/select/baseline", headers=h, json={"baseline_key": "moderate", "include_privacy": True}).json()
    assert r["added"] > 0 and r["counts"]["assigned"] > low
    v = client.get(f"/api/v1/systems/{sid}/select", headers=h).json()
    assert {"cnssi-privacy", "cnssi-classified", "cnssi-intelligence", "cnssi-space", "cnssi-cds", "cnssi-nc3"} <= {o["key"] for o in v["overlays"]}
    so = next(o for o in v["overlays"] if o["key"] == "cnssi-space")
    assert so["structure_only"] and "Structure only" in so["description"]
    bad = client.post(f"/api/v1/systems/{sid}/select/overlay", headers=h, json={"overlay_key": "cnssi-space", "apply": True})
    assert bad.status_code == 422 and "structure only" in bad.json()["detail"]
    assert client.post(f"/api/v1/systems/{sid}/select/tailor", headers=h, json={"action": "remove", "control_ids": ["ac-2.1"], "justification": ""}).status_code == 422
    t = client.post(f"/api/v1/systems/{sid}/select/tailor", headers=h, json={"action": "remove", "control_ids": ["ac-2.1", "ac-2.2"],
                                                                            "justification": "Accounts are managed by the enterprise IdP"}).json()
    assert t["controls"] == ["ac-2.1", "ac-2.2"]
    c = t["counts"]
    assert c["assigned"] == c["baseline"] - c["removed"] + c["overlay_added"] + c["tailored_in"]
    a = client.post(f"/api/v1/systems/{sid}/select/tailor", headers=h, json={"action": "add", "control_ids": ["ac-2.11"],
                                                                            "justification": "Required by the program security plan"}).json()
    assert a["controls"] == ["ac-2.11"] and a["counts"]["tailored_in"] == c["tailored_in"] + 1
    wb = client.get(f"/api/v1/systems/{sid}/stats", headers=h)
    if wb.status_code == 200 and "assigned" in wb.json():
        assert wb.json()["assigned"] == a["counts"]["assigned"]


def test_authorize_checklist_and_traceability(client, ws):
    d = client.get(f"/api/v1/systems/{ws['sid']}/authorize", headers=ws["h"]).json()
    assert len(d["checklist"]) >= 7 and all("link" in i for i in d["checklist"])
    tr = client.get(f"/api/v1/systems/{ws['sid']}/traceability", headers=ws["h"]).json()
    assert tr and {"control_id", "statement", "evidence", "open_findings", "open_poams"} <= set(tr[0])


def test_overlay_csv_import_needs_admin_and_valid_rows(client, ws):
    files = {"file": ("ov.csv", b"control_id,action\nac-99,add\n", "text/csv")}
    r = client.post("/api/v1/overlays/cnssi-space/import", headers=ws["h"], data={"version": "t1"}, files=files)
    assert r.status_code in (403, 422)
