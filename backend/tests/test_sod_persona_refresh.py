"""Sandbox persona SoD across token refresh: /auth/refresh must keep the persona's operator ("op"), otherwise the persona becomes its own
"real person" – persona switching fails (422) and SoD compares the wrong identity. ISCM strategy: ISSO submit → ISSM approve (sandbox label),
same persona refused, real org same person refused, real org different person allowed."""
import uuid

import jwt
import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent, System
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401
from tests.test_sod import _real_user, _set_sandbox


@pytest.fixture(scope="module")
def sb(client, signup_on):  # noqa: F811
    t = _signup(client, f"rf-{uuid.uuid4().hex[:6]}@example.com", "Refresh SoD Org")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "Refresh SoD System", "acronym": f"RF{uuid.uuid4().hex[:3]}", "baseline_key": "moderate",
                                                "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    with SessionLocal() as db:
        org = db.get(System, uuid.UUID(sid)).org_id

    def role(r: str, refreshed: bool = False) -> dict:
        p = client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()
        if refreshed:
            p = client.post("/api/v1/auth/refresh", json={"refresh_token": p["refresh_token"]}).json()
        return auth(p["access_token"])
    return {"login": t, "h": h, "sid": sid, "org": org, "role": role, "u": f"/api/v1/systems/{sid}"}


def _submit(client, sb, h):
    assert client.put(f"{sb['u']}/iscm", json={"narrative": "SYNTHETIC", "defaults": {"slcm_frequency": "Monthly"}}, headers=h).status_code == 200
    r = client.post(f"{sb['u']}/iscm/submit", headers=h)
    assert r.status_code == 200, r.text


def _decide(client, sb, h, approve=True):
    return client.post(f"{sb['u']}/iscm/decision", json={"approve": approve, "comment": "SoD test"}, headers=h)


def _last_sod(action="iscm.strategy_approved"):
    with SessionLocal() as db:
        return db.scalar(select(AuditEvent).where(AuditEvent.action == action).order_by(AuditEvent.occurred_at.desc())).details


def test_refresh_keeps_the_persona_operator(client, sb):
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": sb["login"]["refresh_token"]})
    assert r.status_code == 200 and r.json()["user"]["persona_role"] == "isso"
    claims = jwt.decode(r.json()["access_token"], options={"verify_signature": False})
    assert claims.get("op"), "refreshed persona token must still name its operator"
    h = auth(r.json()["access_token"])
    assert client.get("/api/v1/sandbox/status", headers=h).json()["operator"]["email"].endswith("@example.com")
    sw = client.post("/api/v1/sandbox/act-as", json={"role": "issm"}, headers=h)
    assert sw.status_code == 200 and sw.json()["user"]["persona_role"] == "issm", sw.text


def test_sandbox_isso_submit_issm_approve_ok_and_labelled(client, sb):
    _submit(client, sb, sb["role"]("isso"))
    r = _decide(client, sb, sb["role"]("issm"))
    assert r.status_code == 200 and r.json()["strategy"]["status"] == "approved", r.text
    d = _last_sod()
    assert d["label"] == "Sandbox: same person" and d["prepared_by"]["persona_role"] == "isso" and d["approved_by"]["persona_role"] == "issm"


def test_sandbox_after_refresh_still_same_person_label(client, sb):
    _submit(client, sb, sb["role"]("isso", refreshed=True))
    r = _decide(client, sb, sb["role"]("issm", refreshed=True))
    assert r.status_code == 200, r.text
    d = _last_sod()
    assert d["sod"] == "Sandbox: same person", "a refreshed persona is still the same real person, never 'different person'"
    assert d["prepared_by"]["real_user_id"] == d["approved_by"]["real_user_id"]


def test_sandbox_same_persona_refused(client, sb):
    _submit(client, sb, sb["role"]("isso"))
    isso = _decide(client, sb, sb["role"]("isso"))
    assert isso.status_code == 403 and "ISSM" in isso.json()["detail"]
    assert _decide(client, sb, sb["role"]("issm"), approve=False).status_code == 200
    _submit(client, sb, sb["role"]("issm"))
    same = _decide(client, sb, sb["role"]("issm", refreshed=True))
    assert same.status_code == 403 and "same role" in same.json()["detail"]
    assert _decide(client, sb, sb["role"]("isso")).status_code == 403


def test_real_org_same_person_refused_different_person_ok(client, sb):
    assert _decide(client, sb, _real_user(sb["org"], "issm"), approve=False).status_code == 200  # clear the pending one from the last test
    isso, issm = sb["role"]("isso"), sb["role"]("issm")
    _set_sandbox(sb["org"], False)
    try:
        _submit(client, sb, isso)
        r = _decide(client, sb, issm)
        assert r.status_code == 403 and "persona does not count" in r.json()["detail"]
        ok = _decide(client, sb, _real_user(sb["org"], "issm"))
        assert ok.status_code == 200 and ok.json()["strategy"]["status"] == "approved", ok.text
        assert _last_sod()["sod"] == "different person"
    finally:
        _set_sandbox(sb["org"], True)
