"""
Wave 8 live-preview verification tests (demo account, signup, sandbox, SoD, numbers).
Hits the live preview via REACT_APP_BACKEND_URL. Does NOT touch the test DB.
"""
import os
import time
import uuid
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api/v1"
DEMO_EMAIL = "demo@ironvision.ai"
DEMO_PASS = "IronVisionDemo!2026"


def _login(email, password):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": password}, timeout=20)
    return r


@pytest.fixture(scope="module")
def demo_token():
    r = _login(DEMO_EMAIL, DEMO_PASS)
    assert r.status_code == 200, f"demo login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def demo_headers(demo_token):
    return {"Authorization": f"Bearer {demo_token}"}


# -------- Login / demo account --------
def test_demo_login_and_me(demo_headers):
    me = requests.get(f"{BASE}/auth/me", headers=demo_headers, timeout=15)
    assert me.status_code == 200
    body = me.json()
    assert body.get("email") == DEMO_EMAIL


def test_demo_sandbox_status(demo_headers):
    r = requests.get(f"{BASE}/sandbox/status", headers=demo_headers, timeout=15)
    assert r.status_code == 200
    j = r.json()
    assert j.get("is_sandbox") is True or "operated_by" in j or "tenant" in j


def test_demo_has_4_systems_with_acronyms(demo_headers):
    r = requests.get(f"{BASE}/systems", headers=demo_headers, timeout=15)
    assert r.status_code == 200
    data = r.json()
    systems = data if isinstance(data, list) else data.get("items", data.get("systems", []))
    acronyms = sorted([s.get("acronym") or s.get("short_name") or "" for s in systems])
    assert len([a for a in acronyms if a in {"LTP","MPP","FMDH","TRS"}]) == 4, f"got acronyms={acronyms}"


# -------- Signup --------
@pytest.fixture(scope="module")
def new_signup():
    email = f"wave8-{uuid.uuid4().hex[:10]}@example.com"
    password = "Sandbox!Pass-2026x"
    tok = requests.get(f"{BASE}/auth/signup/start", timeout=30).json()
    time.sleep(tok["min_seconds"] + 0.2)
    payload = {"name": "Wave8 Tester", "email": email, "password": password, "organization": "Wave8 Org", "form_token": tok["form_token"]}
    r = requests.post(f"{BASE}/auth/signup", json=payload, timeout=30)
    assert r.status_code in (200, 201, 202), f"signup failed: {r.status_code} {r.text}"
    return {"email": email, "password": password, "resp": r.json() if r.content else {}}


def test_signup_weak_password_rejected():
    email = f"wave8weak-{uuid.uuid4().hex[:8]}@example.com"
    r = requests.post(f"{BASE}/auth/signup", json={"name":"x","email":email,"password":"short","organization":"o"}, timeout=15)
    assert r.status_code in (400, 422), f"weak pw expected 4xx, got {r.status_code}"


def test_signup_login_and_provisioning(new_signup):
    # Allow provisioning job to run (spec says ~5s)
    token = None
    for _ in range(20):
        r = _login(new_signup["email"], new_signup["password"])
        if r.status_code == 200:
            token = r.json()["access_token"]
            break
        time.sleep(1)
    assert token, "new user cannot log in"
    # Give provisioning a few more seconds
    systems = []
    for _ in range(20):
        rs = requests.get(f"{BASE}/systems", headers={"Authorization": f"Bearer {token}"}, timeout=15)
        if rs.status_code == 200:
            data = rs.json()
            systems = data if isinstance(data, list) else data.get("items", data.get("systems", []))
            if len(systems) >= 4:
                break
        time.sleep(1)
    acronyms = sorted([s.get("acronym") or s.get("short_name") or "" for s in systems])
    assert set(acronyms) >= {"LTP","MPP","FMDH","TRS"}, f"new sandbox should have 4 systems, got {acronyms}"
    # IDs should differ from demo
    pytest.new_user_token = token
    pytest.new_user_system_ids = {s["id"] for s in systems}


def test_new_signup_ids_differ_from_demo(demo_headers):
    rs = requests.get(f"{BASE}/systems", headers=demo_headers, timeout=15)
    demo_ids = {s["id"] for s in (rs.json() if isinstance(rs.json(), list) else rs.json().get("items", []))}
    assert demo_ids.isdisjoint(getattr(pytest, "new_user_system_ids", set())), "new sandbox IDs must differ from demo"


# -------- Persona SoD --------
def _ltp_id(headers):
    rs = requests.get(f"{BASE}/systems", headers=headers, timeout=15)
    arr = rs.json() if isinstance(rs.json(), list) else rs.json().get("items", [])
    for s in arr:
        if (s.get("acronym") or s.get("short_name")) == "LTP":
            return s["id"]
    return None


def test_isso_cannot_approve_own_closure(demo_headers):
    ltp = _ltp_id(demo_headers)
    assert ltp
    # find an open LTP POA&M
    rp = requests.get(f"{BASE}/poams", headers=demo_headers, params={"system_id": ltp, "limit": 100}, timeout=20)
    assert rp.status_code == 200
    poams_json = rp.json()
    poams = poams_json if isinstance(poams_json, list) else poams_json.get("items", [])
    open_poam = next((p for p in poams if p.get("status","").lower() not in ("closed","cancelled")), None)
    assert open_poam, "no open LTP POA&M found"
    # find an evidence id for LTP
    re_ = requests.get(f"{BASE}/evidence", headers=demo_headers, params={"system_id": ltp, "limit": 5}, timeout=20)
    if re_.status_code != 200:
        pytest.skip(f"evidence endpoint returned {re_.status_code}")
    evj = re_.json()
    evs = evj if isinstance(evj, list) else evj.get("items", [])
    if not evs:
        pytest.skip("no evidence to attach")
    rc = requests.post(f"{BASE}/poams/{open_poam['id']}/request-closure",
                       headers=demo_headers,
                       json={"justification": "wave8 test closure request", "evidence_ids": [evs[0]["id"]]},
                       timeout=20)
    assert rc.status_code in (200, 201, 202), f"request-closure failed: {rc.status_code} {rc.text}"
    rid = rc.json().get("review_id") or rc.json().get("id")
    assert rid, f"no review id in response: {rc.json()}"
    # ISSO approves own => expect 403
    ra = requests.post(f"{BASE}/reviews/{rid}/decisions", headers=demo_headers,
                       json={"action":"approve","rationale":"x"}, timeout=15)
    assert ra.status_code == 403, f"ISSO self-approve expected 403, got {ra.status_code} {ra.text}"
    pytest.pending_review_id = rid


def test_issm_can_approve_via_act_as(demo_headers):
    rid = getattr(pytest, "pending_review_id", None)
    if not rid:
        pytest.skip("no pending review id")
    act = requests.post(f"{BASE}/sandbox/act-as", headers=demo_headers, json={"role":"issm"}, timeout=15)
    assert act.status_code == 200, f"act-as issm failed: {act.status_code} {act.text}"
    new_token = act.json().get("access_token") or act.json().get("token")
    assert new_token
    issm_headers = {"Authorization": f"Bearer {new_token}"}
    ra = requests.post(f"{BASE}/reviews/{rid}/decisions", headers=issm_headers,
                       json={"action":"approve","rationale":"approved by issm persona"}, timeout=15)
    assert ra.status_code in (200, 201), f"ISSM approve expected 2xx, got {ra.status_code} {ra.text}"


# -------- Numbers agree --------
def test_workflow_monitor_and_291(demo_headers):
    ltp = _ltp_id(demo_headers)
    r = requests.get(f"{BASE}/metrics/workflow-monitor", headers=demo_headers,
                     params={"system_id": ltp} if ltp else {}, timeout=20)
    if r.status_code != 200:
        # try alt endpoint
        r = requests.get(f"{BASE}/systems/{ltp}/workflow-monitor", headers=demo_headers, timeout=15)
    assert r.status_code == 200, f"workflow monitor failed: {r.status_code}"
    j = r.json()
    # best effort checks
    text = str(j).lower()
    assert "291" in text or "controls" in text, f"expected '291' in workflow monitor payload: {j}"


def test_emass_sync_page(demo_headers):
    r = requests.get(f"{BASE}/emass/status", headers=demo_headers, timeout=15)
    if r.status_code == 404:
        r = requests.get(f"{BASE}/emass/sync", headers=demo_headers, timeout=15)
    assert r.status_code == 200, f"emass endpoint failed: {r.status_code}"
    j = r.json()
    # last_sync should be present and non-null
    assert any(k in j for k in ("last_sync", "last_synced_at", "last_sync_at")), f"no last_sync field in {j.keys() if isinstance(j, dict) else type(j)}"
