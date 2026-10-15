"""Preview-only tests for OIDC hardening + logout + identity-mappings admin endpoint.
Preview config: AUTH_PROVIDERS=dev_password, ALLOW_DEMO_LOGIN=true, oidc NOT enabled.
"""
import os
import requests
import pytest

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE}/api/v1"

DEMO_EMAIL = "demo@ironvision.ai"
DEMO_PASS = "IronVisionDemo!2026"


def _login(email: str, password: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def demo_token() -> str:
    return _login(DEMO_EMAIL, DEMO_PASS)


# --- demo-login availability + password login regression ---------------------

def test_password_login_demo_account():
    r = requests.post(f"{API}/auth/login", json={"email": DEMO_EMAIL, "password": DEMO_PASS}, timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert "access_token" in body


def test_demo_login_endpoint_enabled_in_preview():
    r = requests.post(f"{API}/auth/demo-login", timeout=15)
    # Should NOT be 404 (demo enabled on preview). Accept 200 or 429 (rate-limit).
    assert r.status_code in (200, 429), f"unexpected {r.status_code} {r.text}"
    if r.status_code == 200:
        assert "access_token" in r.json()


# --- OIDC endpoints must 404 in preview (oidc disabled) ----------------------

def test_oidc_login_404_when_disabled():
    r = requests.get(f"{API}/auth/oidc/login", allow_redirects=False, timeout=15)
    assert r.status_code == 404, f"got {r.status_code} {r.text[:200]}"


def test_oidc_callback_404_when_disabled():
    r = requests.get(f"{API}/auth/oidc/callback", params={"code": "x", "state": "y"}, allow_redirects=False, timeout=15)
    assert r.status_code == 404


def test_oidc_exchange_404_when_disabled():
    r = requests.post(f"{API}/auth/oidc/exchange", json={"code": "x"}, timeout=15)
    assert r.status_code == 404


# --- logout returns 200 + {end_session_url: null} for password sessions ------

def test_logout_returns_200_json_and_revokes_session():
    tok = _login(DEMO_EMAIL, DEMO_PASS)
    h = {"Authorization": f"Bearer {tok}"}
    # Confirm session alive
    me = requests.get(f"{API}/auth/me", headers=h, timeout=15)
    assert me.status_code == 200
    # Logout
    out = requests.post(f"{API}/auth/logout", headers=h, timeout=15)
    assert out.status_code == 200, f"got {out.status_code} {out.text}"
    body = out.json()
    assert "end_session_url" in body
    assert body["end_session_url"] is None, f"expected null end_session_url for password session, got {body}"
    # Session revoked
    me2 = requests.get(f"{API}/auth/me", headers=h, timeout=15)
    assert me2.status_code == 401


# --- /admin/identity-mappings ACL -------------------------------------------

def test_identity_mappings_unauthenticated_401():
    r = requests.get(f"{API}/admin/identity-mappings", timeout=15)
    assert r.status_code == 401


def test_identity_mappings_platform_admin_ok(demo_token):
    # Demo account defaults to ISSO persona; switch to platform_admin via act-as.
    h = {"Authorization": f"Bearer {demo_token}"}
    sw = requests.post(f"{API}/sandbox/act-as", json={"role": "platform_admin"}, headers=h, timeout=15)
    assert sw.status_code == 200, f"act-as platform_admin failed: {sw.status_code} {sw.text}"
    admin_tok = sw.json()["access_token"]
    r = requests.get(f"{API}/admin/identity-mappings", headers={"Authorization": f"Bearer {admin_tok}"}, timeout=15)
    assert r.status_code == 200, f"platform_admin got {r.status_code} {r.text}"
    data = r.json()
    assert isinstance(data, list)


def test_identity_mappings_isso_forbidden(demo_token):
    # Demo lands on ISSO; call directly with that token.
    h = {"Authorization": f"Bearer {demo_token}"}
    r = requests.get(f"{API}/admin/identity-mappings", headers=h, timeout=15)
    assert r.status_code == 403, f"ISSO should be forbidden, got {r.status_code} {r.text}"
