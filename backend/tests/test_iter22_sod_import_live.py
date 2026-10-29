"""Live (preview URL) checks – iteration 22: persona refresh keeps act-as working, ISCM SoD (ISSO submit → ISSM approve sandbox label,
same-role message names the submitter, withdraw), Import Center remove endpoint validation. ZERO AI spend."""
import os
import uuid

import pytest
import requests

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]).rstrip("/")
API = f"{BASE}/api/v1"


def h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def demo():
    r = requests.post(f"{API}/auth/demo-login", timeout=30)
    if r.status_code != 200:
        pytest.skip(f"demo login failed {r.status_code}")
    return r.json()


@pytest.fixture(scope="module")
def ltp(demo):
    r = requests.get(f"{API}/systems", headers=h(demo["access_token"]), timeout=30)
    items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    s = next((x for x in items if x.get("acronym") == "LTP"), None)
    assert s, "LTP not found"
    return s["id"]


def act(tok, role):
    r = requests.post(f"{API}/sandbox/act-as", json={"role": role}, headers=h(tok), timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def strat(tok, sid):
    return requests.get(f"{API}/systems/{sid}/iscm", headers=h(tok), timeout=30).json().get("strategy")


def to_draft(tok, sid):
    s = strat(tok, sid)
    if s and s["status"] == "pending_approval":
        isso = act(tok, "isso")["access_token"]
        r = requests.post(f"{API}/systems/{sid}/iscm/withdraw", headers=h(isso), timeout=30)
        assert r.status_code == 200, r.text


def body(tok, sid):
    s = strat(tok, sid) or {}
    return {k: s.get(k) for k in ("narrative", "scope", "defaults", "profiles", "reporting", "review_activities", "evidence_requirements") if s.get(k) is not None}


# Auth: login user is the ISSO persona; refresh keeps persona operator → act-as 200
def test_demo_login_isso_persona(demo):
    assert demo["user"]["persona_role"] == "isso"
    assert demo.get("refresh_token")


def test_refresh_then_act_as_ok(demo):
    r = requests.post(f"{API}/auth/refresh", json={"refresh_token": demo["refresh_token"]}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["user"]["persona_role"] == "isso"
    sw = requests.post(f"{API}/sandbox/act-as", json={"role": "issm"}, headers=h(r.json()["access_token"]), timeout=30)
    assert sw.status_code == 200, sw.text
    assert sw.json()["user"]["persona_role"] == "issm"


def test_refresh_issm_persona_then_act_as(demo):
    p = act(demo["access_token"], "issm")
    r = requests.post(f"{API}/auth/refresh", json={"refresh_token": p["refresh_token"]}, timeout=30)
    assert r.status_code == 200 and r.json()["user"]["persona_role"] == "issm"
    sw = requests.post(f"{API}/sandbox/act-as", json={"role": "sca"}, headers=h(r.json()["access_token"]), timeout=30)
    assert sw.status_code == 200, sw.text


# ISCM SoD: ISSO submit → ISSM approve OK; label + withdraw; ISSM self-submit → 403 naming the role
def test_iscm_isso_submit_issm_approve(demo, ltp):
    tok = demo["access_token"]
    to_draft(tok, ltp)
    isso = act(tok, "isso")["access_token"]
    b = body(isso, ltp)
    b["narrative"] = (b.get("narrative") or "SYNTHETIC") [:3000]
    assert requests.put(f"{API}/systems/{ltp}/iscm", json=b, headers=h(isso), timeout=30).status_code == 200
    r = requests.post(f"{API}/systems/{ltp}/iscm/submit", headers=h(isso), timeout=30)
    assert r.status_code == 200, r.text
    s = strat(isso, ltp)
    assert s["status"] == "pending_approval"
    assert "ISSO persona at" in (s.get("submitted_by_label") or ""), s.get("submitted_by_label")
    # ISSO cannot approve at all (role check precedes SoD)
    r = requests.post(f"{API}/systems/{ltp}/iscm/decision", json={"approve": True}, headers=h(isso), timeout=30)
    assert r.status_code == 403
    issm = act(tok, "issm")["access_token"]
    r = requests.post(f"{API}/systems/{ltp}/iscm/decision", json={"approve": True}, headers=h(issm), timeout=30)
    assert r.status_code == 200, r.text
    assert strat(issm, ltp)["status"] == "approved"


def test_iscm_withdraw(demo, ltp):
    tok = demo["access_token"]
    to_draft(tok, ltp)
    isso = act(tok, "isso")["access_token"]
    b = body(isso, ltp)
    assert requests.put(f"{API}/systems/{ltp}/iscm", json=b, headers=h(isso), timeout=30).status_code == 200
    assert requests.post(f"{API}/systems/{ltp}/iscm/submit", headers=h(isso), timeout=30).status_code == 200
    r = requests.post(f"{API}/systems/{ltp}/iscm/withdraw", headers=h(isso), timeout=30)
    assert r.status_code == 200, r.text
    assert strat(isso, ltp)["status"] == "draft"
    # withdraw again when draft → 4xx
    r2 = requests.post(f"{API}/systems/{ltp}/iscm/withdraw", headers=h(isso), timeout=30)
    assert r2.status_code in (400, 409, 422), r2.status_code


def test_iscm_issm_self_submit_blocked(demo, ltp):
    tok = demo["access_token"]
    to_draft(tok, ltp)
    issm = act(tok, "issm")["access_token"]
    b = body(issm, ltp)
    put = requests.put(f"{API}/systems/{ltp}/iscm", json=b, headers=h(issm), timeout=30)
    if put.status_code == 403:
        pytest.skip("ISSM persona cannot edit the strategy")
    sub = requests.post(f"{API}/systems/{ltp}/iscm/submit", headers=h(issm), timeout=30)
    assert sub.status_code == 200, sub.text
    r = requests.post(f"{API}/systems/{ltp}/iscm/decision", json={"approve": True}, headers=h(issm), timeout=30)
    assert r.status_code == 403, r.text
    d = r.json()["detail"]
    assert "same role" in d and "submitted by the ISSM persona at" in d, d
    # clean up: ISSO approves? ISSO lacks approve → withdraw then ISSO submit, ISSM approve
    isso = act(tok, "isso")["access_token"]
    assert requests.post(f"{API}/systems/{ltp}/iscm/withdraw", headers=h(isso), timeout=30).status_code == 200
    assert requests.post(f"{API}/systems/{ltp}/iscm/submit", headers=h(isso), timeout=30).status_code == 200
    issm = act(tok, "issm")["access_token"]
    assert requests.post(f"{API}/systems/{ltp}/iscm/decision", json={"approve": True}, headers=h(issm), timeout=30).status_code == 200


# Import Center remove: validation + unknown id skipped + browser-only file removed
def test_remove_empty_items_422(demo, ltp):
    r = requests.post(f"{API}/import-center/remove", json={"system_id": ltp, "items": []}, headers=h(demo["access_token"]), timeout=30)
    assert r.status_code == 422


def test_remove_unknown_emass_id_skipped(demo, ltp):
    r = requests.post(f"{API}/import-center/remove", json={"system_id": ltp, "items": [
        {"file_name": "TEST_x.xlsx", "size_bytes": 10, "state": "imported", "emass_import_id": str(uuid.uuid4())},
        {"file_name": "TEST_y.ckl", "size_bytes": 10, "state": "ready", "emass_import_id": None}]}, headers=h(demo["access_token"]), timeout=30)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["skipped"][0]["reason"] == "Not found"
    assert j["removed"][0]["file_name"] == "TEST_y.ckl"


def test_remove_unknown_system_404(demo):
    r = requests.post(f"{API}/import-center/remove", json={"system_id": str(uuid.uuid4()), "items": [
        {"file_name": "a", "size_bytes": 1, "state": "ready"}]}, headers=h(demo["access_token"]), timeout=30)
    assert r.status_code in (403, 404)
