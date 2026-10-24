"""NSS systems: CNSSI 1253 Appendix D parameter values beside ODPs (adopt / undo / conflicts) and the Privacy Overlay prompt."""
import csv
import io
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent, OdpValue, Overlay, Policy, System
from app.services import cnssi1253 as cn
from app.services import cnssi_params as cp
from tests.conftest import auth
from tests.test_cnssi1253 import NSS
from tests.test_sandbox import _signup, signup_on  # noqa: F401


@pytest.fixture(scope="module")
def org(client, signup_on):  # noqa: F811
    t = _signup(client, f"cp-{uuid.uuid4().hex[:6]}@example.com", "CNSSI PV Org")
    h = auth(t["access_token"])
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])  # noqa: E731
    return {"h": h, "role": role}


def _mk(client, org, **kw):
    body = {"name": f"PV {uuid.uuid4().hex[:4]}", "acronym": f"P{uuid.uuid4().hex[:3]}", **NSS, **kw}
    r = client.post("/api/v1/systems", json=body, headers=org["h"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_mapping_is_conservative_and_cites_pages(db_session=None):
    with SessionLocal() as db:
        m = cp.mapping(db)
    assert len(m) == 162 and sum(len(v["odps"]) for v in m.values()) == 204 and sum(len(v["control_level"]) for v in m.values()) == 27
    assert m["ac-2"]["odps"]["ac-02_odp.10"]["value"] == "at least quarterly" and m["ac-2"]["source"] == "CNSSI 1253 (2022) Table D-1 p. D-4"
    assert {k: v["value"] for k, v in m["ac-1"]["odps"].items()} == {"ac-01_odp.05": "at least annually", "ac-01_odp.07": "at least annually"}
    assert m["ac-2.3"]["odps"]["ac-02.03_odp.02"]["value"] == "90 days", "'d.' = paragraph (d) of the enhancement"
    at1 = m["at-1"]["control_level"][0]
    assert at1["value"] == "all personnel" and "several ODPs" in at1["reason"], "aggregated placeholder: never guessed"
    assert not m["si-3"]["odps"].get("si-03_odp.05") and any("nested" in x["reason"] for x in m["si-3"]["control_level"])


def test_values_shown_with_page_in_workbench_comparison_and_csv(client, org):
    sid = _mk(client, org)
    wb = client.get(f"/api/v1/systems/{sid}/workbench/controls/ac-2", headers=org["h"]).json()["cnssi_parameters"]
    o = next(x for x in wb["odps"] if x["parameter_id"] == "ac-02_odp.10")
    assert o["cnssi_value"] == "at least quarterly" and o["cnssi_ref"] == "Table D-1, p. D-4" and o["cnssi_status"] == "not_set"
    pc = client.get(f"/api/v1/systems/{sid}/parameter-comparison", params={"family": "at", "limit": 500}, headers=org["h"]).json()
    assert pc["cnssi"] and [c["key"] for c in pc["columns"]][-3:] == ["cnssi_value", "cnssi_ref", "cnssi_status_label"]
    lvl = [r for r in pc["items"] if r["parameter_id"] == "(control level)" and r["enhancement"] == "" and r["control_id"] == "AT-1"]
    assert lvl and lvl[0]["cnssi_status_label"] == "applies to control – choose parameter" and lvl[0]["cnssi_value"] == "all personnel"
    rows = list(csv.DictReader(io.StringIO(client.get(f"/api/v1/systems/{sid}/parameters.csv", params={"family": "ac"}, headers=org["h"]).text.lstrip("\ufeff"))))
    r = next(x for x in rows if x["Parameter ID"] == "ac-02_odp.10")
    assert r["CNSSI 1253 value"] == "at least quarterly" and r["CNSSI 1253 reference"] == "Table D-1, p. D-4" and r["CNSSI comparison"] == "Not set – CNSSI value available"


def test_adopt_sets_value_source_audit_and_undo(client, org):
    sid = _mk(client, org)
    url = f"/api/v1/systems/{sid}/parameters/cnssi-adopt"
    r = client.post(url, json={"items": [{"control_id": "ac-2", "parameter_id": "ac-02_odp.10"}]}, headers=org["role"]("isso"))
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        o = db.scalar(select(OdpValue).where(OdpValue.system_id == uuid.UUID(sid), OdpValue.parameter == "ac-02_odp.10"))
        assert (o.value, o.source) == ("at least quarterly", "CNSSI 1253 (2022) Table D-1 p. D-4") and o.approved_by and o.approved_at
        ev = db.get(AuditEvent, uuid.UUID(r.json()["undo_id"]))
        assert ev.action == "system.parameter_cnssi_adopted" and ev.after["changes"][0]["before"] is None
    st = next(x for x in client.get(f"/api/v1/systems/{sid}/workbench/controls/ac-2", headers=org["h"]).json()["cnssi_parameters"]["odps"]
              if x["parameter_id"] == "ac-02_odp.10")["cnssi_status"]
    assert st == "matches"
    u = client.post(f"{url}/{r.json()['undo_id']}/undo", headers=org["role"]("isso"))
    assert u.status_code == 200 and u.json()["restored"] == 1
    with SessionLocal() as db:
        assert db.scalar(select(OdpValue).where(OdpValue.system_id == uuid.UUID(sid), OdpValue.parameter == "ac-02_odp.10")) is None
        assert db.scalar(select(AuditEvent).where(AuditEvent.entity_id == sid, AuditEvent.action == "system.parameter_cnssi_undone"))
    assert client.post(f"{url}/{r.json()['undo_id']}/undo", headers=org["role"]("isso")).status_code == 422, "undo once"


def test_existing_value_is_restored_on_undo_and_role_without_permission_gets_403(client, org):
    sid = _mk(client, org)
    with SessionLocal() as db:
        db.add(OdpValue(system_id=uuid.UUID(sid), control_id="ac-2", parameter="ac-02_odp.06", value="12 hours", source="SSP", approved_by="ISSM"))
        db.commit()
    url = f"/api/v1/systems/{sid}/parameters/cnssi-adopt"
    body = {"items": [{"control_id": "ac-2", "parameter_id": "ac-02_odp.06"}]}
    assert client.post(url, json=body, headers=org["role"]("leadership_viewer")).status_code == 403
    c = client.post(url, json=body, headers=org["h"])
    assert c.status_code == 409 and c.json()["conflicts"][0]["kind"] == "System value"
    r = client.post(url, json={**body, "confirm_conflicts": True}, headers=org["h"]).json()
    client.post(f"{url}/{r['undo_id']}/undo", headers=org["h"])
    with SessionLocal() as db:
        o = db.scalar(select(OdpValue).where(OdpValue.system_id == uuid.UUID(sid), OdpValue.parameter == "ac-02_odp.06"))
        assert (o.value, o.source, o.approved_by) == ("12 hours", "SSP", "ISSM")


def test_policy_conflict_needs_confirmation(client, org):
    sid = _mk(client, org)
    with SessionLocal() as db:
        db.add(Policy(org_id=db.get(System, uuid.UUID(sid)).org_id, policy_key=f"p-{uuid.uuid4().hex[:6]}", title="Account Policy", version=1, system_ids=[sid],
                      analysis={"values": [{"control_id": "ac-2", "parameter": "ac-02_odp.10", "value": "annually", "quote": "annually"}]}))
        db.commit()
    url = f"/api/v1/systems/{sid}/parameters/cnssi-adopt"
    body = {"items": [{"control_id": "ac-2", "parameter_id": "ac-02_odp.10"}]}
    c = client.post(url, json=body, headers=org["h"])
    assert c.status_code == 409
    msg = c.json()["conflicts"][0]["message"]
    assert "Policy: Account Policy" in msg and "sets 'annually'; CNSSI says 'at least quarterly' – replace?" in msg
    r = client.post(url, json={**body, "confirm_conflicts": True}, headers=org["h"])
    assert r.status_code == 200 and r.json()["confirmed_conflicts"][0]["kind"] == "Policy"


def test_bulk_adopt_control_and_family(client, org):
    sid = _mk(client, org)
    url = f"/api/v1/systems/{sid}/parameters/cnssi-adopt"
    r = client.post(url, json={"control_id": "ac-2"}, headers=org["h"]).json()
    assert r["adopted"] == 4 and {c["parameter"] for c in r["changes"]} == {"ac-02_odp.06", "ac-02_odp.07", "ac-02_odp.08", "ac-02_odp.10"}
    f = client.post(url, json={"family": "ia"}, headers=org["h"]).json()
    with SessionLocal() as db:
        m = cp.mapping(db)
        have = {c for c in m if c.startswith("ia-")}
        n = sum(1 for o in db.scalars(select(OdpValue).where(OdpValue.system_id == uuid.UUID(sid), OdpValue.control_id.in_(have))))
    assert f["adopted"] == n > 0


def test_fips_systems_unaffected(client, org):
    sid = client.post("/api/v1/systems", json={"name": "FIPS PV", "acronym": f"F{uuid.uuid4().hex[:3]}", "baseline_key": "moderate", "categorization_mode": "fips199",
                                               "information_types": [{"id": "D.16.3"}], "processes_pii": True}, headers=org["h"]).json()["id"]
    pc = client.get(f"/api/v1/systems/{sid}/parameter-comparison", params={"family": "ac"}, headers=org["h"]).json()
    assert not pc["cnssi"] and "cnssi_value" not in [c["key"] for c in pc["columns"]] and all("cnssi_value" not in r for r in pc["items"])
    assert "CNSSI 1253 value" not in client.get(f"/api/v1/systems/{sid}/parameters.csv", params={"family": "ac"}, headers=org["h"]).text.splitlines()[0]
    assert client.get(f"/api/v1/systems/{sid}/workbench/controls/ac-2", headers=org["h"]).json()["cnssi_parameters"] is None
    r = client.post(f"/api/v1/systems/{sid}/parameters/cnssi-adopt", json={"items": [{"control_id": "ac-2", "parameter_id": "ac-02_odp.10"}]}, headers=org["h"])
    assert r.status_code == 422
    assert client.get(f"/api/v1/systems/{sid}/select", headers=org["h"]).json()["privacy_prompt"] is None
    assert client.get(f"/api/v1/systems/{sid}/categorization", headers=org["h"]).json()["privacy_prompt"] is None


def _pii(sid, value, status=None):
    with SessionLocal() as db:
        s = db.get(System, uuid.UUID(sid))
        s.processes_pii, s.pta = value, ({"pii_status": status} if status else {})
        db.commit()


def test_privacy_prompt_yes_unknown_no_and_computed_count(client, org):
    sid = _mk(client, org)
    with SessionLocal() as db:
        gap = cn.privacy_gap(db)
    assert len(gap) == 27 and "pt-2" in gap and "ac-3.14" in gap
    for v, st, shown in ((True, "yes", True), (None, "unknown", True), (False, "no", False), (None, None, False)):
        _pii(sid, v, st)
        p = client.get(f"/api/v1/systems/{sid}/select", headers=org["h"]).json()["privacy_prompt"]
        assert (p is not None) == shown, (v, st)
        if p:
            assert p["state"] == "prompt" and p["count"] == len(gap) and len(p["items"]) == 27
            assert p["message"].startswith(f"This system handles PII. CNSSI 1253 leaves {len(gap)} NIST privacy-baseline controls to the CNSSI 1253F Privacy Overlay")
            assert client.get(f"/api/v1/systems/{sid}/categorization", headers=org["h"]).json()["privacy_prompt"]["count"] == 27


def test_coverage_cross_check_and_state_after_applying(client, org):
    sid = _mk(client, org)
    _pii(sid, True, "yes")
    p = client.get(f"/api/v1/systems/{sid}/select", headers=org["h"]).json()["privacy_prompt"]
    items = {i["control_id"]: i for i in p["items"]}
    with SessionLocal() as db:
        ovs = {o.variant: o for o in db.scalars(select(Overlay).where(Overlay.group_key == "privacy", Overlay.is_active.is_(True)))}
    for cid, i in items.items():  # coverage only as recorded in the overlay data
        assert set(i["variants"]) == {v for v, o in ovs.items() if cid in o.controls_add}
    assert p["by_variant"] == {"acct": 23, "high": 27, "low": 27, "moderate": 27}
    assert items["pt-2"]["coverage"] == "covered by Privacy Overlay p. 69"
    assert items["sa-4"]["coverage"].startswith("covered only by the high, low, moderate variant(s)")
    r = client.post(f"/api/v1/systems/{sid}/select/overlay", json={"overlay_key": "cnssi-privacy-acct", "apply": True}, headers=org["h"])
    assert r.status_code == 200, r.text
    p = client.get(f"/api/v1/systems/{sid}/select", headers=org["h"]).json()["privacy_prompt"]
    assert p["state"] == "applied" and p["message"] == "Privacy Overlay applied – 23 of 27 covered"
    assert {i["control_id"] for i in p["items"] if not i["covered"]} == {"sa-4", "sc-7.24", "si-12.2", "si-19"}
    assert all(i["coverage"].endswith("– SME review") for i in p["items"] if not i["covered"])
    client.post(f"/api/v1/systems/{sid}/select/overlay", json={"overlay_key": "cnssi-privacy-moderate", "apply": True}, headers=org["h"])
    assert client.get(f"/api/v1/systems/{sid}/select", headers=org["h"]).json()["privacy_prompt"]["message"] == "Privacy Overlay applied – 27 of 27 covered"
    _pii(sid, False, "no")
    assert client.get(f"/api/v1/systems/{sid}/select", headers=org["h"]).json()["privacy_prompt"] is None
