"""
Iteration 22 — Asset Inventory Module tests
- Authentication: demo-admin login
- Tenable demo sync seeds 7 assets
- /api/assets list, stats, CRUD, validation, backfill
- /api/risk-scoring/org-score 6 factors + top_risky_assets
- /api/risk-scoring/asset-risk criticality-weighted
- Criticality-multiplier verification (api-gateway-01 > others)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "demo-admin@grc.com"
ADMIN_PASS = "DemoAdmin123!"


# ─── Fixtures ────────────────────────────────────────────

@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"no token in login response: {data}"
    return tok


@pytest.fixture(scope="session")
def client(admin_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session", autouse=True)
def seed_demo_assets(client):
    """Run tenable demo sync once to populate 7 demo assets."""
    r = client.post(f"{API}/tenable/sync", json={"mode": "demo"}, timeout=120)
    assert r.status_code == 200, f"tenable demo sync failed: {r.status_code} {r.text}"
    return r.json()


# ─── Auth ─────────────────────────────────────────────────

def test_login_returns_token():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200
    assert "token" in r.json() or "access_token" in r.json()


# ─── Assets: list/stats ──────────────────────────────────

def test_assets_stats_after_sync(client):
    r = client.get(f"{API}/assets/stats", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    for key in ("total_assets", "vulnerable_assets", "by_criticality", "by_environment", "by_os"):
        assert key in data, f"missing {key} in stats"
    assert data["total_assets"] >= 7, f"expected >=7 assets, got {data['total_assets']}"
    assert isinstance(data["by_criticality"], dict)
    # Expected from review: 2 critical (api-gateway-01, db-server-01)
    assert data["by_criticality"].get("critical", 0) >= 2


def test_list_assets_shape(client):
    r = client.get(f"{API}/assets", timeout=30)
    assert r.status_code == 200, r.text
    assets = r.json()
    assert isinstance(assets, list)
    assert len(assets) >= 7
    a = assets[0]
    assert "hostname" in a
    assert "vuln_summary" in a
    for k in ("open_critical", "open_high", "open_medium", "fixed", "total_open"):
        assert k in a["vuln_summary"]
    assert "software_count" in a
    assert isinstance(a["software_count"], int)


def test_list_assets_filter_by_criticality(client):
    r = client.get(f"{API}/assets", params={"criticality": "critical"}, timeout=30)
    assert r.status_code == 200
    for a in r.json():
        assert a["criticality"] == "critical"


# ─── Asset detail ────────────────────────────────────────

@pytest.fixture(scope="session")
def api_gateway_asset(client):
    r = client.get(f"{API}/assets", timeout=30)
    for a in r.json():
        if a.get("hostname") == "api-gateway-01":
            return a
    pytest.skip("api-gateway-01 not seeded")


def test_asset_detail_shape(client, api_gateway_asset):
    aid = api_gateway_asset["id"]
    r = client.get(f"{API}/assets/{aid}", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("asset", "vulnerabilities", "compliance_checks", "poam_entries"):
        assert k in d
    for k in ("open", "fixed", "summary"):
        assert k in d["vulnerabilities"]
    s = d["vulnerabilities"]["summary"]
    for k in ("open_critical", "open_high", "open_medium", "fixed_total"):
        assert k in s
    # api-gateway-01 is critical — should have vulns
    assert d["asset"]["criticality"] == "critical"
    assert len(d["asset"].get("installed_software", [])) > 0, "expected installed_software populated"


def test_asset_detail_not_found(client):
    r = client.get(f"{API}/assets/does-not-exist-xyz", timeout=30)
    assert r.status_code == 404


# ─── Create/Update/Delete ────────────────────────────────

def test_create_update_delete_asset(client):
    # CREATE
    payload = {
        "hostname": "TEST_asset_host_01",
        "ip_addresses": ["10.0.99.99"],
        "operating_system": "Ubuntu 22.04",
        "criticality": "high",
        "environment": "staging",
        "owner": "test-owner",
        "tags": ["test"],
    }
    r = client.post(f"{API}/assets", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["hostname"] == "TEST_asset_host_01"
    assert created["criticality"] == "high"
    assert "id" in created
    aid = created["id"]

    # GET verify
    r2 = client.get(f"{API}/assets/{aid}", timeout=30)
    assert r2.status_code == 200
    assert r2.json()["asset"]["hostname"] == "TEST_asset_host_01"

    # UPDATE
    r3 = client.put(f"{API}/assets/{aid}", json={"criticality": "critical", "notes": "promoted"}, timeout=30)
    assert r3.status_code == 200, r3.text
    upd = r3.json()
    assert upd["criticality"] == "critical"
    assert upd["notes"] == "promoted"

    # GET verify update persisted
    r4 = client.get(f"{API}/assets/{aid}", timeout=30)
    assert r4.json()["asset"]["criticality"] == "critical"

    # DELETE
    r5 = client.delete(f"{API}/assets/{aid}", timeout=30)
    assert r5.status_code == 200

    # GET verify removed
    r6 = client.get(f"{API}/assets/{aid}", timeout=30)
    assert r6.status_code == 404


def test_create_asset_invalid_criticality(client):
    r = client.post(f"{API}/assets", json={"hostname": "TEST_bad", "criticality": "bogus"}, timeout=30)
    assert r.status_code == 400


def test_create_asset_invalid_environment(client):
    r = client.post(f"{API}/assets", json={"hostname": "TEST_bad2", "environment": "mars"}, timeout=30)
    assert r.status_code == 400


def test_update_asset_invalid_criticality(client, api_gateway_asset):
    r = client.put(f"{API}/assets/{api_gateway_asset['id']}", json={"criticality": "nope"}, timeout=30)
    assert r.status_code == 400


# ─── Backfill ────────────────────────────────────────────

def test_backfill_is_idempotent(client):
    r1 = client.post(f"{API}/assets/backfill-from-tenable", timeout=60)
    assert r1.status_code == 200
    total1 = r1.json()["total_assets"]
    r2 = client.post(f"{API}/assets/backfill-from-tenable", timeout=60)
    assert r2.status_code == 200
    total2 = r2.json()["total_assets"]
    assert total2 == total1, f"backfill not idempotent: {total1} -> {total2}"


# ─── Risk Scoring ────────────────────────────────────────

def test_org_risk_score_has_six_factors(client):
    r = client.get(f"{API}/risk-scoring/org-score", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "factors" in d
    expected = {"siem", "compliance", "pipeline", "ingestion", "policy", "asset"}
    assert set(d["factors"].keys()) == expected, f"factor mismatch: {set(d['factors'].keys())}"
    assert d["factors"]["asset"]["weight"] == 0.25
    assert "top_risky_assets" in d
    assert isinstance(d["top_risky_assets"], list)


def test_asset_risk_endpoint(client):
    r = client.get(f"{API}/risk-scoring/asset-risk", timeout=30)
    assert r.status_code == 200, r.text
    d = r.json()
    for k in ("asset_risk_score", "top_risky_assets", "criticality_multipliers", "severity_base_points"):
        assert k in d
    assert d["criticality_multipliers"]["critical"] == 2.0
    assert d["criticality_multipliers"]["medium"] == 1.0
    assert d["criticality_multipliers"]["low"] == 0.5
    assert d["severity_base_points"]["critical"] == 25


def test_criticality_multiplier_ranks_api_gateway_high(client):
    """api-gateway-01 (critical) should outrank an asset with same/similar vulns but lower criticality."""
    r = client.get(f"{API}/risk-scoring/asset-risk", timeout=30)
    top = r.json()["top_risky_assets"]
    assert len(top) > 0
    # api-gateway-01 should be in top and have score consistent with critical multiplier
    hosts = [t["hostname"] for t in top]
    assert "api-gateway-01" in hosts, f"api-gateway-01 missing from top risky: {hosts}"
    ag = next(t for t in top if t["hostname"] == "api-gateway-01")
    assert ag["criticality"] == "critical"
    # Among critical-criticality assets, api-gateway-01 should not be outranked by a 'medium' with fewer vulns
    for t in top:
        if t["hostname"] == "api-gateway-01":
            continue
        if t["criticality"] in ("low", "medium") and t["open_vulns"] <= ag["open_vulns"]:
            assert ag["score"] >= t["score"], f"critical asset outranked by {t}"
