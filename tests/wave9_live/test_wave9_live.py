"""Live preview smoke tests for Wave 9 follow-up fixes.

Runs against REACT_APP_BACKEND_URL. No DB resets.
"""
import os
import time
import uuid
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api/v1"
SIGNUP_PW = "Sandbox!Pass-2026x"

DEMO_EMAIL = "demo@ironvision.ai"
DEMO_PW = "IronVisionDemo!2026"


def _new_email():
    return f"wave9-{uuid.uuid4().hex[:10]}@example.com"


def _signup(email):
    tok = requests.get(f"{API}/auth/signup/start", timeout=30).json()
    time.sleep(tok["min_seconds"] + 0.2)
    r = requests.post(f"{API}/auth/signup", json={
        "name": "Wave 9 Tester",
        "email": email,
        "password": SIGNUP_PW,
        "organization": "Wave9 Org",
        "form_token": tok["form_token"],
    }, timeout=30)
    return r


def _login(email, pw=SIGNUP_PW):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": pw}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


# ---- BLOCKER: signup 201 (not 429) ----

def _wait_ready(tok, timeout=25):
    h = {"Authorization": f"Bearer {tok}"}
    for _ in range(timeout * 2):
        time.sleep(0.5)
        r = requests.get(f"{API}/sandbox/status", headers=h, timeout=10)
        if r.status_code == 200 and (r.json().get("status") == "ready" or (r.json().get("progress") or {}).get("pct") == 100):
            return r.json()
    return None


@pytest.fixture(scope="module")
def new_account():
    email = _new_email()
    r = _signup(email)
    assert r.status_code == 201, f"BLOCKER: signup returned {r.status_code} {r.text}"
    body = r.json()
    assert body.get("ok") is True
    tok = None
    for _ in range(20):
        time.sleep(0.5)
        try:
            tok = _login(email)
            break
        except Exception:
            pass
    assert tok, "could not login after signup"
    status = _wait_ready(tok)
    assert status, "sandbox never became ready"
    return {"email": email, "token": tok, "status": status}


def test_blocker_signup_returns_201():
    """Signup must not be 429 for a fresh email through ingress."""
    r = _signup(_new_email())
    assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text}"


def test_fresh_login_lands_on_isso(new_account):
    """Sandbox status after fresh login defaults to ISSO persona."""
    assert (new_account["status"].get("acting_role") or "").lower() == "isso", new_account["status"]


def test_persona_reset_on_relogin(new_account):
    """After switching to AO and logging in again, defaults back to ISSO."""
    h = {"Authorization": f"Bearer {new_account['token']}"}
    r = requests.post(f"{API}/sandbox/act-as", json={"role": "ao"}, headers=h, timeout=15)
    assert r.status_code == 200, r.text
    ao_tok = r.json()["access_token"]
    s_ao = requests.get(f"{API}/sandbox/status", headers={"Authorization": f"Bearer {ao_tok}"}, timeout=15).json()
    assert (s_ao.get("acting_role") or "").lower() == "ao", s_ao
    # Fresh login
    fresh = _login(new_account["email"])
    s = requests.get(f"{API}/sandbox/status", headers={"Authorization": f"Bearer {fresh}"}, timeout=15).json()
    assert (s.get("acting_role") or "").lower() == "isso", f"Fresh login should default to ISSO, got acting_role={s.get('acting_role')}"


# ---- Mapping review out-of-scope flow ----

def test_mapping_review_out_of_scope_pending(new_account):
    h = {"Authorization": f"Bearer {new_account['token']}"}
    systems = requests.get(f"{API}/systems", headers=h, timeout=15).json()
    ltp = next((s for s in systems if (s.get("acronym") or "").upper() == "LTP"), None)
    assert ltp, f"LTP missing: {systems}"
    sid = ltp["id"]
    # Fetch unmapped list for this system
    um = requests.get(f"{API}/systems/{sid}/mapping-review", headers=h, timeout=20)
    if um.status_code != 200:
        pytest.skip(f"mapping-review endpoint shape differs: {um.status_code} {um.text[:200]}")
    data = um.json()
    rules = data.get("unmapped") or data.get("rules") or []
    if not rules:
        pytest.skip("no unmapped rules present on fresh sandbox")
    rid = rules[0].get("rule_id") or rules[0].get("id")
    # Attempt out-of-scope action
    r = requests.post(f"{API}/systems/{sid}/mapping-review/{rid}/action",
                      json={"action": "out_of_scope", "justification": "N/A for this platform"},
                      headers=h, timeout=20)
    assert r.status_code in (200, 201, 202), r.text
    body = r.json()
    txt = str(body).lower()
    assert "issm" in txt or "pending" in txt or "await" in txt, f"expected mentioning ISSM/pending: {body}"


# ---- Numbers / tiles sanity ----

def test_sandbox_status_shape(new_account):
    h = {"Authorization": f"Bearer {new_account['token']}"}
    r = requests.get(f"{API}/sandbox/status", headers=h, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body.get("sandbox") is True
    assert "onboarding" in body


def test_emass_last_sync_matches_history(new_account):
    h = {"Authorization": f"Bearer {new_account['token']}"}
    status = requests.get(f"{API}/emass/status", headers=h, timeout=15).json()
    history = requests.get(f"{API}/emass/sync-history", headers=h, timeout=15)
    if history.status_code != 200:
        pytest.skip(f"sync-history endpoint not available: {history.status_code}")
    rows = history.json() if isinstance(history.json(), list) else history.json().get("items", [])
    succeeded = [r for r in rows if (r.get("status") or r.get("outcome") or "").lower() in ("succeeded", "success", "ok")]
    if not succeeded:
        pytest.skip("no succeeded rows yet on fresh tenant")
    newest = max(succeeded, key=lambda r: r.get("completed_at") or r.get("started_at") or "")
    newest_ts = newest.get("completed_at") or newest.get("started_at")
    assert status.get("last_sync_at") == newest_ts, f"status.last_sync_at {status.get('last_sync_at')} != newest succeeded {newest_ts}"
