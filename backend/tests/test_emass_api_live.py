"""Live API tests against preview URL for eMASS conditional validation."""
import os, requests, pytest

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
SID = os.environ.get("EMASS_LIVE_SYSTEM_ID") or ""
pytestmark = pytest.mark.skipif(not (BASE and SID), reason="live preview test: set REACT_APP_BACKEND_URL and EMASS_LIVE_SYSTEM_ID")

@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE}/api/v1/auth/demo-login", json={})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]

@pytest.fixture
def h(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def test_demo_login(token):
    assert token

def test_emass_get_ra5(h):
    r = requests.get(f"{BASE}/api/v1/systems/{SID}/workbench/controls/ra-5/emass", headers=h)
    assert r.status_code == 200, r.text
    j = r.json()
    assert "values" in j
    assert "implementation_status" in j

def test_plan_missing_required_422(h):
    # Status Implemented only -> expect 422 with required fields listed
    r = requests.put(
        f"{BASE}/api/v1/systems/{SID}/workbench/controls/ac-3/emass/plan",
        headers=h,
        json={"implementation_status": "Implemented"},
    )
    assert r.status_code == 422, r.text
    body = r.text.lower()
    # At least one required field name should appear
    assert any(k in body for k in ["control designation", "estimated completion date", "responsible entities", "slcm frequency"])

def test_plan_invalid_enum(h):
    r = requests.put(
        f"{BASE}/api/v1/systems/{SID}/workbench/controls/ac-3/emass/plan",
        headers=h,
        json={"implementation_status": "Implemented", "slcm_frequency": "Biweekly"},
    )
    assert r.status_code == 422, r.text

def test_plan_responsible_entities_2001(h):
    r = requests.put(
        f"{BASE}/api/v1/systems/{SID}/workbench/controls/ac-3/emass/plan",
        headers=h,
        json={"implementation_status": "Implemented", "responsible_entities": "x" * 2001},
    )
    assert r.status_code == 422, r.text

def test_plan_slcm_comments_4001(h):
    r = requests.put(
        f"{BASE}/api/v1/systems/{SID}/workbench/controls/ac-3/emass/plan",
        headers=h,
        json={"implementation_status": "Implemented", "slcm_comments": "x" * 4001},
    )
    assert r.status_code == 422, r.text

def test_inherited_risk_locked_422(h):
    r = requests.put(
        f"{BASE}/api/v1/systems/{SID}/workbench/controls/ia-2.1/emass/risk",
        headers=h,
        json={"severity": "Low", "impact_description": "x"},
    )
    assert r.status_code == 422, r.text

def test_controls_payload_mock(h):
    r = requests.get(f"{BASE}/api/v1/systems/{SID}/emass/controls-payload", headers=h)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j.get("mock") is True
    label = j.get("label", "")
    assert "MOCKED" in label.upper()
    # Spot-check eMASS API-name serialization
    body_str = str(j).lower()
    assert "implementationstatus" in body_str or "acronym" in body_str

def test_sca_persona_plan_403(token):
    # Switch to SCA via act-as
    r = requests.post(f"{BASE}/api/v1/sandbox/act-as", json={"role": "sca"}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    sca_tok = r.json()["access_token"]
    r2 = requests.put(
        f"{BASE}/api/v1/systems/{SID}/workbench/controls/ac-3/emass/plan",
        headers={"Authorization": f"Bearer {sca_tok}", "Content-Type": "application/json"},
        json={"implementation_status": "Planned",
              "control_designation": "System-Specific",
              "estimated_completion_date": "2026-12-31",
              "responsible_entities": "ISSO",
              "slcm_criticality": "Low",
              "slcm_frequency": "Annually",
              "slcm_method": "Automated",
              "slcm_reporting": "Dashboard",
              "slcm_tracking": "JIRA",
              "slcm_comments": "test"},
    )
    assert r2.status_code == 403, r2.text
