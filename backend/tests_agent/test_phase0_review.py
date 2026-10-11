"""
Phase-0 end-to-end integration tests against the live preview URL.
Covers: auth (8 accounts), RBAC on AO endpoint, audit events + verify,
content stats/versions, controls search/filter/detail, health, AI health.
Idempotent and read-mostly (does not POST /admin/content/load).
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    # fall back to frontend .env
    with open("/app/frontend/.env") as f:
        for ln in f:
            if ln.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = ln.split("=", 1)[1].strip()
                break
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api/v1"
PWD = "AegisDemo!2026"

ACCOUNTS = {
    "system_owner": "system.owner@aegisrmf.demo",
    "isso": "isso@aegisrmf.demo",
    "issm": "issm@aegisrmf.demo",
    "sca": "sca@aegisrmf.demo",
    "ao": "ao@aegisrmf.demo",
    "devsecops": "devsecops@aegisrmf.demo",
    "leadership_viewer": "leadership.viewer@aegisrmf.demo",
    "platform_admin": "platform.admin@aegisrmf.demo",
}


def _login(email: str, password: str = PWD):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    return r


def _token(email: str) -> str:
    r = _login(email)
    assert r.status_code == 200, f"login failed {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _h(email: str):
    return {"Authorization": f"Bearer {_token(email)}"}


# ---------- Auth ----------
@pytest.mark.parametrize("role,email", list(ACCOUNTS.items()))
def test_login_all_eight_accounts(role, email):
    r = _login(email)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["token_type"].lower() == "bearer"
    assert data["access_token"]
    assert data["user"]["email"] == email


def test_login_wrong_password_401():
    # use a safe email to avoid locking out demo accounts; use ao with 1 bad try
    r = _login("sca@aegisrmf.demo", password="wrong-password-xyz")
    assert r.status_code == 401


def test_auth_me_returns_roles_and_permissions():
    r = requests.get(f"{API}/auth/me", headers=_h(ACCOUNTS["isso"]), timeout=15)
    assert r.status_code == 200
    body = r.json()
    assert body["email"] == ACCOUNTS["isso"]
    assert "roles" in body and isinstance(body["roles"], list) and body["roles"]
    assert "permissions" in body and isinstance(body["permissions"], list)


# ---------- RBAC on AO decision endpoint ----------
def test_authz_decision_isso_forbidden():
    r = requests.post(f"{API}/authorization-decisions/test", headers=_h(ACCOUNTS["isso"]), json={}, timeout=15)
    assert r.status_code == 403


def test_authz_decision_platform_admin_forbidden():
    r = requests.post(f"{API}/authorization-decisions/test", headers=_h(ACCOUNTS["platform_admin"]), json={}, timeout=15)
    assert r.status_code == 403


def test_authz_decision_ao_ok():
    r = requests.post(f"{API}/authorization-decisions/test", headers=_h(ACCOUNTS["ao"]), json={}, timeout=15)
    assert r.status_code == 200


def test_audit_events_shows_isso_denial_and_chain_valid():
    # trigger a fresh denial first
    requests.post(f"{API}/authorization-decisions/test", headers=_h(ACCOUNTS["isso"]), json={}, timeout=15)
    r = requests.get(f"{API}/audit-events", params={"action": "authz.denied"}, headers=_h(ACCOUNTS["issm"]), timeout=15)
    assert r.status_code == 200, r.text
    body = r.json()
    items = body.get("items", body) if isinstance(body, dict) else body
    assert isinstance(items, list) and len(items) >= 1
    # at least one with isso actor
    emails = [str(it.get("actor_email") or it.get("actor") or "") for it in items]
    assert any("isso@aegisrmf.demo" in e for e in emails)
    v = requests.get(f"{API}/audit-events/verify", headers=_h(ACCOUNTS["issm"]), timeout=15)
    assert v.status_code == 200
    vb = v.json()
    assert vb.get("valid") is True


# ---------- Content ----------
def test_content_stats_exact_counts():
    r = requests.get(f"{API}/content/stats", headers=_h(ACCOUNTS["isso"]), timeout=15)
    assert r.status_code == 200
    s = r.json()
    assert s["controls_total"] == 1196
    assert s["enhancements"] == 872
    bl = s["baselines"]
    assert bl["low"] == 149
    assert bl["moderate"] == 287
    assert bl["high"] == 370
    assert bl["privacy"] == 96
    assert s["ccis"] == 5137
    assert s["cci_rev5_mappings"] == 3838


def test_content_versions_six_rows_pinned_v150():
    r = requests.get(f"{API}/content/versions", headers=_h(ACCOUNTS["isso"]), timeout=15)
    assert r.status_code == 200
    body = r.json()
    items = body.get("items", body) if isinstance(body, dict) else body
    assert isinstance(items, list) and len(items) == 6
    for row in items:
        assert row.get("sha256")
        assert len(row["sha256"]) == 64
    # The 5 oscal-content rows (catalog + 4 profiles) must be pinned v1.5.0
    oscal_rows = [r for r in items if (r.get("content_type") or "").startswith("oscal_")]
    assert len(oscal_rows) == 5
    for row in oscal_rows:
        assert row.get("release_tag") == "v1.5.0", row


# ---------- Controls ----------
def test_controls_moderate_total_287():
    r = requests.get(f"{API}/controls", params={"baseline": "moderate", "page": 1, "page_size": 1},
                     headers=_h(ACCOUNTS["isso"]), timeout=15)
    assert r.status_code == 200
    body = r.json()
    total = body.get("total") or body.get("count") or body.get("total_items")
    assert total == 287, f"got {total}: keys={list(body.keys())}"


def test_controls_search_q_ac():
    r = requests.get(f"{API}/controls", params={"q": "ac-2"}, headers=_h(ACCOUNTS["isso"]), timeout=15)
    assert r.status_code == 200
    body = r.json()
    items = body.get("items") or body.get("results") or []
    assert len(items) >= 1
    assert any("ac-2" in (it.get("control_id", "").lower()) for it in items)


def test_controls_family_filter_ac():
    r = requests.get(f"{API}/controls", params={"family": "AC", "page_size": 5},
                     headers=_h(ACCOUNTS["isso"]), timeout=15)
    assert r.status_code == 200
    items = r.json().get("items") or []
    assert items
    for it in items:
        fam = (it.get("family") or it.get("family_id") or "").upper()
        assert fam.startswith("AC")


def test_control_detail_ac_2_has_structure():
    r = requests.get(f"{API}/controls/ac-2", headers=_h(ACCOUNTS["isso"]), timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    # Required substructures
    assert d.get("statement") or d.get("statements")
    assert "parameters" in d
    assert "objectives" in d or "assessment_objectives" in d
    assert "ccis" in d or "cci_mappings" in d


# ---------- Health / OpenAPI ----------
def test_health_all_components_ok():
    r = requests.get(f"{API}/health", timeout=15)
    assert r.status_code == 200
    b = r.json()
    assert b["status"] == "ok"
    comps = b["components"]
    for name in ("database", "storage", "worker", "ai"):
        assert comps[name]["ok"] is True, f"{name} not ok: {comps[name]}"


def test_openapi_and_docs_available():
    r1 = requests.get(f"{BASE_URL}/api/openapi.json", timeout=15)
    assert r1.status_code == 200
    assert "openapi" in r1.json()
    r2 = requests.get(f"{BASE_URL}/api/docs", timeout=15)
    assert r2.status_code == 200


# ---------- AI health (admin-only; one real LLM call) ----------
def test_ai_health_admin_ok_real_llm_call():
    r = requests.post(f"{API}/ai/health", headers=_h(ACCOUNTS["platform_admin"]), json={}, timeout=60)
    assert r.status_code == 200, r.text
    b = r.json()
    assert b.get("ok") is True or b.get("status") == "ok"
    assert b.get("provider") == "emergent"
    assert b.get("model") == "claude-sonnet-5-5"


def test_ai_health_non_admin_forbidden():
    r = requests.post(f"{API}/ai/health", headers=_h(ACCOUNTS["ao"]), json={}, timeout=15)
    assert r.status_code == 403
