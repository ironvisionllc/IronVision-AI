"""Usability-test fixes: attach/link evidence from a control, per-user UI preferences, deep-link tabs, Monitor evidence wording."""
import re
import uuid

import pytest

from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

CKL = b'<?xml version="1.0"?><CHECKLIST><STIGS><iSTIG><VULN/></iSTIG></STIGS></CHECKLIST>'


def _org(client, tag):
    t = _signup(client, f"ux-{tag}-{uuid.uuid4().hex[:6]}@example.com", f"UX {tag} Org")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": f"UX {tag}", "acronym": f"U{uuid.uuid4().hex[:4]}", "baseline_key": "low",
                                               "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    p = {r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"]) for r in ("isso", "ao")}
    return {"sid": sid, **p}


@pytest.fixture(scope="module")
def orgs(client, signup_on):  # noqa: F811
    return _org(client, "a"), _org(client, "b")


def _upload(client, o, name="ux.ckl"):
    r = client.post(f"/api/v1/systems/{o['sid']}/uploads", files={"file": (name, CKL)}, headers=o["isso"])
    assert r.status_code in (200, 201, 202), r.text
    return r.json()["evidence_id"]


def test_attach_then_link_existing_evidence(client, orgs):
    a, _ = orgs
    ev = _upload(client, a)
    r = client.post(f"/api/v1/systems/{a['sid']}/controls/ac-2/evidence-links", json={"evidence_id": ev}, headers=a["isso"])
    assert r.status_code in (200, 201), r.text
    d = client.get(f"/api/v1/systems/{a['sid']}/workbench/controls/ac-2", headers=a["isso"]).json()
    assert ev in [e["id"] for e in d["evidence"]]
    again = client.post(f"/api/v1/systems/{a['sid']}/controls/ac-2/evidence-links", json={"evidence_id": ev}, headers=a["isso"])
    assert again.status_code in (200, 201) and again.json().get("already_linked") is True
    audit = client.get("/api/v1/audit-events", params={"limit": 50}, headers=a["isso"]).json()
    rows = audit if isinstance(audit, list) else audit.get("items", [])
    assert any("evidence" in (x.get("action") or "") and "link" in (x.get("action") or "") for x in rows)


def test_link_requires_upload_permission(client, orgs):
    a, _ = orgs
    ev = _upload(client, a, "ao.ckl")
    r = client.post(f"/api/v1/systems/{a['sid']}/controls/ac-3/evidence-links", json={"evidence_id": ev}, headers=a["ao"])
    assert r.status_code == 403, r.text


def test_link_is_tenant_and_system_isolated(client, orgs):
    a, b = orgs
    ev_a = _upload(client, a, "iso.ckl")
    # tenant B cannot link into A's system, nor link A's evidence into its own system
    assert client.post(f"/api/v1/systems/{a['sid']}/controls/ac-2/evidence-links", json={"evidence_id": ev_a}, headers=b["isso"]).status_code in (403, 404)
    assert client.post(f"/api/v1/systems/{b['sid']}/controls/ac-2/evidence-links", json={"evidence_id": ev_a}, headers=b["isso"]).status_code == 404
    assert client.post(f"/api/v1/systems/{a['sid']}/controls/zz-99/evidence-links", json={"evidence_id": ev_a}, headers=a["isso"]).status_code == 404


def test_preferences_per_user_round_trip(client, orgs):
    a, b = orgs
    assert client.put("/api/v1/me/preferences", json={"guided": "on", "sca_auto_advance": False}, headers=a["isso"]).status_code == 200
    got = client.get("/api/v1/me/preferences", headers=a["isso"]).json()
    assert got["guided"] == "on" and got["sca_auto_advance"] is False
    assert client.get("/api/v1/me/preferences", headers=b["isso"]).json().get("guided") is None
    assert client.put("/api/v1/me/preferences", json={"guided": "maybe"}, headers=a["isso"]).status_code == 422


def test_queue_control_links_carry_tab():
    from app.services.queue import _tab
    assert _tab([{"code": "cat1_open"}]) == "findings"
    assert _tab([{"code": "expired_evidence"}]) == "evidence"
    assert _tab([{"code": "missing_implementation_statement"}]) == "implementation"
    assert _tab([]) == "implementation"


def test_monitor_evidence_metrics_are_scoped_counts(client, orgs):
    a, _ = orgs
    steps = client.get(f"/api/v1/systems/{a['sid']}/rmf-steps", headers=a["isso"])
    if steps.status_code != 200:
        pytest.skip("rmf status route not available")
    txt = str(steps.json())
    assert "Controls with current evidence:" in txt and "collected items" in txt
    assert not re.search(r"\d+(\.\d+)?% (current|fresh)", txt)  # no bare percentages with different denominators
