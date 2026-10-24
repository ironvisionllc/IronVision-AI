import pytest
from sqlalchemy import text

from app.security.rbac import DECISION_PERMISSIONS, ROLE_PERMISSIONS
from tests.conftest import auth

ENDPOINT = "/api/v1/authorization-decisions/test"


def test_isso_forbidden_and_audited(client, token):
    r = client.post(ENDPOINT, headers=auth(token("isso@aegisrmf.demo")))
    assert r.status_code == 403
    events = client.get("/api/v1/audit-events", params={"action": "authz.denied"},
                        headers=auth(token("issm@aegisrmf.demo"))).json()
    assert any(e["actor_email"] == "isso@aegisrmf.demo" and e["entity_id"] == "authorization.decide" for e in events)


def test_ao_allowed(client, token):
    r = client.post(ENDPOINT, headers=auth(token("ao@aegisrmf.demo")))
    assert r.status_code == 200
    assert r.json()["ok"] is True


@pytest.mark.parametrize("email", ["platform.admin@aegisrmf.demo", "sca@aegisrmf.demo", "issm@aegisrmf.demo",
                                   "system.owner@aegisrmf.demo", "devsecops@aegisrmf.demo",
                                   "leadership.viewer@aegisrmf.demo"])
def test_non_ao_forbidden(client, token, email):
    assert client.post(ENDPOINT, headers=auth(token(email))).status_code == 403


def test_platform_admin_has_no_decision_rights():
    assert not ROLE_PERMISSIONS["platform_admin"] & DECISION_PERMISSIONS


def test_ai_health_admin_only(client, token):
    assert client.post("/api/v1/ai/health", headers=auth(token("ao@aegisrmf.demo"))).status_code == 403


def test_ai_status_visible_to_every_role_without_secrets(client, token):
    for email, can_test in (("ao@aegisrmf.demo", False), ("isso@aegisrmf.demo", False), ("platform.admin@aegisrmf.demo", True)):
        s = client.get("/api/v1/ai/status", headers=auth(token(email))).json()
        assert {"provider", "model", "configured", "mode_label", "last_success_at", "calls_24h"} <= s.keys()
        assert s["can_test"] is can_test and s["mode_label"]
        assert not any("key" in k and k != "api_key_configured" for k in s)
        if not s["configured"]:
            assert s["mode_label"] == "Deterministic analysis (no AI)"



def test_audit_chain_valid_and_append_only(client, token):
    r = client.get("/api/v1/audit-events/verify", headers=auth(token("issm@aegisrmf.demo")))
    assert r.json()["valid"] is True and r.json()["checked"] > 0
    from app.db import SessionLocal

    with SessionLocal() as db, pytest.raises(Exception, match="append-only"):
        db.execute(text("UPDATE audit_events SET outcome='tampered'"))
    with SessionLocal() as db, pytest.raises(Exception, match="append-only"):
        db.execute(text("DELETE FROM audit_events"))
