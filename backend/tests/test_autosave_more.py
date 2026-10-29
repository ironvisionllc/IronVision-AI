"""Auto-save on the provider modal and Key roles: draft field values, conflicts 409, one coalesced audit event per session."""
import uuid

import pytest

from tests.conftest import auth
from tests.test_autosave import AS, _close, _events
from tests.test_sandbox import _signup, signup_on  # noqa: F401

SYS = {"baseline_key": "low", "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}


@pytest.fixture(scope="module")
def ctx(client, signup_on):  # noqa: F811
    t = _signup(client, f"as2-{uuid.uuid4().hex[:6]}@example.com", "AS2 Org")
    h = auth(t["access_token"])
    isso = auth(client.post("/api/v1/sandbox/act-as", json={"role": "isso"}, headers=h).json()["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "Roles Sys", "acronym": "RLS", **SYS}, headers=isso).json()["id"]
    return {"sid": sid, "isso": isso}


def test_provider_autosave(client, ctx):
    p = client.post("/api/v1/providers", json={"name": "Cloud Provider"}, headers=ctx["isso"]).json()
    v = p["updated_at"]
    for basis in ("FedRAMP High", "FedRAMP High P-ATO"):
        r = client.patch(f"/api/v1/providers/{p['id']}", json={"name": "Cloud Provider", "basis": basis}, headers={**ctx["isso"], **AS, "X-Base-Version": v})
        assert r.status_code == 200, r.text
        v = r.json()["updated_at"]
    stale = client.patch(f"/api/v1/providers/{p['id']}", json={"name": "Cloud Provider", "basis": "x"}, headers={**ctx["isso"], **AS, "X-Base-Version": p["updated_at"]})
    assert stale.status_code == 409 and stale.json()["detail"]["theirs"]["basis"] == "FedRAMP High P-ATO"
    assert _events(p["id"], "provider.updated") == []
    _close(client, ctx)
    ev = _events(p["id"], "provider.updated")
    assert len(ev) == 1 and ev[0].details["saves"] == 2 and ev[0].after["basis"] == "FedRAMP High P-ATO"


def test_key_roles_autosave(client, ctx):
    url = f"/api/v1/systems/{ctx['sid']}/prepare"
    v = client.get(url, headers=ctx["isso"]).json()["version"]
    for name in ("Pat Owner", "Pat Q. Owner"):
        r = client.put(url, json={"roles": {"system_owner": {"name": name, "email": "pat@example.com"}}}, headers={**ctx["isso"], **AS, "X-Base-Version": v})
        assert r.status_code == 200, r.text
        v = r.json()["version"]
    assert client.put(url, json={"roles": {}}, headers={**ctx["isso"], **AS, "X-Base-Version": "2020-01-01T00:00:00+00:00"}).status_code == 409
    _close(client, ctx)
    ev = _events(ctx["sid"], "system.roles_updated")
    assert len([e for e in ev if (e.details or {}).get("autosave")]) == 1
