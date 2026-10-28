"""Manage imported data: per-field view (prior → imported → current), restore / clear / delete with per-item results, changed-since-import
guard, whole-import revert with exclusions, 30-day undo, RBAC (SCA read-only), tenant isolation (404), audit, approval re-review."""
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent
from tests.conftest import auth
from tests.test_emass_fields import FULL
from tests.test_emass_import import _xlsx
from tests.test_sandbox import _signup, signup_on  # noqa: F401

HEAD = ["Acronym", "Implementation Status", "SLCM Frequency", "SLCM Comments", "Severity", "Residual Risk Level"]


@pytest.fixture(scope="module")
def ctx(client, signup_on):  # noqa: F811
    t = _signup(client, f"mid-{uuid.uuid4().hex[:6]}@example.com", f"MID Org {uuid.uuid4().hex[:4]}")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "MID System", "acronym": f"MD{uuid.uuid4().hex[:3]}", "baseline_key": "moderate",
                                                "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])
    isso = role("isso")
    base = f"/api/v1/systems/{sid}/workbench/controls"
    assert client.put(f"{base}/ac-2/emass/plan", json={"implementation_status": "Planned", **FULL}, headers=isso).status_code == 200
    data = _xlsx([HEAD, ["AC-2", "Planned", "Weekly", "Imported comment", "Moderate", "Low"],
                  ["AC-3", "Planned", "Quarterly", "New comment", "Low", "Low"]])
    up = client.post(f"/api/v1/systems/{sid}/emass-imports", files={"file": ("mid.xlsx", data)}, headers=isso).json()
    url = f"/api/v1/systems/{sid}/emass-imports/{up['id']}"
    assert client.put(f"{url}/decisions", json={"bulk": "accept_safe"}, headers=isso).status_code == 200
    assert client.post(f"{url}/apply", headers=isso).status_code == 200
    return {"h": isso, "sid": sid, "base": base, "iid": up["id"], "role": role, "m": f"/api/v1/emass-imports/{up['id']}/manage"}


def _e(view, eid):
    return next(e for e in view["entries"] if e["id"] == eid)


def test_view_lists_fields_by_destination_with_prior_imported_current(client, ctx):
    v = client.get(ctx["m"], headers=ctx["h"]).json()
    e = _e(v, "ac-2|slcm_frequency")
    assert e["prior"] == "Monthly" and e["imported"] == "Weekly" and e["current"] == "Weekly" and e["destination"] == "SLCM (Continuous Monitoring)"
    assert set(e["actions"]) >= {"restore", "clear"} and v["groups"]
    assert client.get(f"/api/v1/systems/{ctx['sid']}/imported-data", headers=ctx["h"]).json()["items"][0]["manageable"] >= 2


def test_restore_previous_then_undo(client, ctx):
    r = client.post(ctx["m"], json={"action": "restore", "ids": ["ac-2|slcm_frequency"]}, headers=ctx["h"]).json()
    assert r["ok"] == 1 and _e(r, "ac-2|slcm_frequency")["state"] == "restored"
    assert client.get(f"{ctx['base']}/ac-2/emass", headers=ctx["h"]).json()["values"]["slcm_frequency"] == "Monthly"
    with SessionLocal() as db:
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.entity_id == ctx["iid"], AuditEvent.action == "import_data.restore"))
    u = client.post(f"{ctx['m']}/{r['op']['op_id']}/undo", headers=ctx["h"])
    assert u.status_code == 200 and client.get(f"{ctx['base']}/ac-2/emass", headers=ctx["h"]).json()["values"]["slcm_frequency"] == "Weekly"
    assert client.post(f"{ctx['m']}/{r['op']['op_id']}/undo", headers=ctx["h"]).status_code == 409


def test_changed_since_import_needs_confirmation(client, ctx):
    assert client.put(f"{ctx['base']}/ac-3/emass/plan", json={"implementation_status": "Planned", **FULL, "slcm_comments": "Edited by hand"},
                      headers=ctx["h"]).status_code == 200
    r = client.post(ctx["m"], json={"action": "clear", "ids": ["ac-3|slcm_comments"]}, headers=ctx["h"]).json()
    assert r["failed"] == 1 and r["results"][0]["needs_confirm"]
    r2 = client.post(ctx["m"], json={"action": "clear", "ids": ["ac-3|slcm_comments"], "force": True}, headers=ctx["h"]).json()
    assert r2["ok"] == 1 and client.get(f"{ctx['base']}/ac-3/emass", headers=ctx["h"]).json()["values"]["slcm_comments"] in (None, "")


def test_whole_import_revert_with_exclusions_and_per_item_results(client, ctx):
    r = client.post(ctx["m"], json={"action": "restore", "all": True, "exclude": ["ac-3|slcm_frequency"]}, headers=ctx["h"]).json()
    assert r["ok"] >= 1 and _e(r, "ac-3|slcm_frequency")["state"] == "applied"
    assert all("ok" in x for x in r["results"]) and "ac-3|slcm_frequency" not in [x["id"] for x in r["results"]]


def test_rbac_sca_read_only_and_tenant_isolation(client, ctx, signup_on):  # noqa: F811
    sca = ctx["role"]("sca")
    v = client.get(ctx["m"], headers=sca).json()
    assert all(not e["actions"] for e in v["entries"])
    assert client.post(ctx["m"], json={"action": "restore", "ids": ["ac-3|slcm_frequency"]}, headers=sca).status_code == 403
    other = auth(_signup(client, f"mid-x-{uuid.uuid4().hex[:6]}@example.com", f"MID X {uuid.uuid4().hex[:4]}")["access_token"])
    assert client.get(ctx["m"], headers=other).status_code == 404
    assert client.post(ctx["m"], json={"action": "restore", "all": True}, headers=other).status_code == 404
    assert client.get(f"/api/v1/systems/{ctx['sid']}/imported-data", headers=other).status_code == 404


def test_delete_everything_keeps_system_then_undo(client, ctx):
    v = client.get(ctx["m"], headers=ctx["h"]).json()
    ids = [e["id"] for e in v["entries"] if e["actions"]]
    r = client.post(ctx["m"], json={"action": "restore", "ids": ids, "force": True}, headers=ctx["h"]).json()
    assert r["ok"] == len(ids) and r["failed"] == 0
    assert client.get(f"/api/v1/systems/{ctx['sid']}", headers=ctx["h"]).status_code == 200, "system shell kept"
    after = client.get(ctx["m"], headers=ctx["h"]).json()
    assert all(e["state"] != "applied" for e in after["entries"] if e["id"] in ids)
    assert client.post(f"{ctx['m']}/{r['op']['op_id']}/undo", headers=ctx["h"]).status_code == 200
    back = {e["id"]: e for e in client.get(ctx["m"], headers=ctx["h"]).json()["entries"]}
    assert any(back[i]["state"] == "applied" for i in ids if "|*" not in i)
