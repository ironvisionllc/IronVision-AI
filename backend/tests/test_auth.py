import pytest

from app.seed import DEMO_USERS, demo_email
from tests.conftest import PASSWORD, auth

ALL_EMAILS = [demo_email(r) for r, _, _ in DEMO_USERS]


@pytest.mark.parametrize("email", ALL_EMAILS)
def test_login_all_demo_accounts(client, email):
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == email
    assert body["user"]["auth_provider"] == "dev_password"
    assert body["user"]["auth_is_simulated"] is True
    me = client.get("/api/v1/auth/me", headers=auth(body["access_token"]))
    assert me.status_code == 200
    org_roles = [r for r in me.json()["roles"] if r["scope_type"] == "org"]
    assert len(org_roles) == 1


def test_bad_password_rejected_and_audited(client, token):
    r = client.post("/api/v1/auth/login", json={"email": "sca@aegisrmf.demo", "password": "wrong"})
    assert r.status_code == 401
    events = client.get("/api/v1/audit-events", params={"action": "auth.login", "outcome": "failure"},
                        headers=auth(token("issm@aegisrmf.demo"))).json()
    assert any(e["actor_email"] == "sca@aegisrmf.demo" for e in events)


def test_unknown_user_rejected(client):
    r = client.post("/api/v1/auth/login", json={"email": "nobody@aegisrmf.demo", "password": PASSWORD})
    assert r.status_code == 401


def test_requires_token(client):
    assert client.get("/api/v1/auth/me").status_code == 401
    assert client.get("/api/v1/auth/me", headers=auth("garbage")).status_code == 401


def test_success_login_audited(client, token):
    token("devsecops@aegisrmf.demo")
    events = client.get("/api/v1/audit-events", params={"action": "auth.login", "outcome": "success"},
                        headers=auth(token("issm@aegisrmf.demo"))).json()
    assert any(e["actor_email"] == "devsecops@aegisrmf.demo" for e in events)


def test_provider_info_has_no_public_account_picker(client):
    body = client.get("/api/v1/auth/provider").json()
    assert body["label"] == "DEVELOPMENT AUTHENTICATION – SIMULATED, NOT CAC/PIV"
    assert body["dev_accounts"] == []  # single demo account is documented, never listed publicly
