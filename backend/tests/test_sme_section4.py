"""SME section 4: evidence sources split – file uploads never take credentials; every source type explains when to use it."""
import uuid

import pytest

from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401


@pytest.fixture(scope="module")
def ws(client, signup_on):  # noqa: F811
    t = _signup(client, f"s4-{uuid.uuid4().hex[:6]}@example.com", "S4 Org")
    h = auth(t["access_token"])
    r = client.post("/api/v1/systems", json={"name": "Section Four", "acronym": "S4", "baseline_key": "low"}, headers=h)
    return {"h": h, "sid": r.json()["id"]}


def test_every_source_type_has_when_to_use(client, ws):
    types = client.get("/api/v1/source-types", headers=ws["h"]).json()
    assert types and all(t["when"] for t in types)
    assert {t["adapter_mode"] for t in types} == {"file_import", "mock"}


def test_file_sources_refuse_credentials(client, ws):
    r = client.post(f"/api/v1/systems/{ws['sid']}/sources", headers=ws["h"], json={"name": "Monthly ACAS", "source_type": "acas", "credential": "tok"})
    assert r.status_code == 422 and "never take credentials" in r.json()["detail"]
    ok = client.post(f"/api/v1/systems/{ws['sid']}/sources", headers=ws["h"], json={"name": "Monthly ACAS", "source_type": "acas"})
    assert ok.status_code in (200, 201) and not ok.json()["credential_set"]
    live = client.post(f"/api/v1/systems/{ws['sid']}/sources", headers=ws["h"], json={"name": "Pipeline", "source_type": "devsecops_pipeline", "credential": "tok"})
    assert live.status_code in (200, 201) and live.json()["credential_set"]
