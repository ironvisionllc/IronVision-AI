"""
Test NIST SP 800-53 expansion to 20 control families with 190 controls.
Tests the new families: MA, MP, PL, PM, PS, PT, SI, SR
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Expected control counts per family
EXPECTED_FAMILY_COUNTS = {
    "AC": 17, "AT": 4, "AU": 11, "CA": 7, "CM": 11, "CP": 9,
    "IA": 9, "IR": 8, "MA": 6, "MP": 7, "PE": 16, "PL": 5,
    "PM": 11, "PS": 9, "PT": 8, "RA": 6, "SA": 9, "SC": 16,
    "SI": 12, "SR": 9
}

# New families added in this iteration
NEW_FAMILIES = ["MA", "MP", "PL", "PM", "PS", "PT", "SI", "SR"]

# Sample controls from new families to verify CCIs
NEW_FAMILY_CCI_SAMPLES = {
    "MA-1": 2,  # Maintenance policy
    "MP-1": 2,  # Media protection policy
    "PL-1": 2,  # Planning policy
    "PM-1": 2,  # Program management
    "PS-1": 2,  # Personnel security policy
    "PT-1": 2,  # PII processing policy
    "SI-1": 2,  # System integrity policy
    "SI-2": 3,  # Flaw remediation
    "SR-1": 2,  # Supply chain risk management policy
}


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API calls"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo-admin@grc.com",
        "password": "DemoAdmin123!"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json().get("token")


@pytest.fixture(scope="module")
def nist_800_53_framework_id(auth_token):
    """Get the NIST SP 800-53 framework ID"""
    headers = {"Authorization": f"Bearer {auth_token}"}
    response = requests.get(f"{BASE_URL}/api/frameworks", headers=headers)
    assert response.status_code == 200
    frameworks = response.json()
    nist_fw = next((f for f in frameworks if f["name"] == "NIST SP 800-53"), None)
    assert nist_fw is not None, "NIST SP 800-53 framework not found"
    return nist_fw["id"]


class TestNIST80053ControlCount:
    """Test that NIST SP 800-53 has exactly 190 controls across 20 families"""
    
    def test_total_control_count_is_190(self, auth_token, nist_800_53_framework_id):
        """Verify total control count is 190"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/controls/{nist_800_53_framework_id}", headers=headers)
        assert response.status_code == 200
        controls = response.json()
        assert len(controls) == 190, f"Expected 190 controls, got {len(controls)}"
    
    def test_all_20_families_present(self, auth_token, nist_800_53_framework_id):
        """Verify all 20 control families are present"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/controls/{nist_800_53_framework_id}", headers=headers)
        assert response.status_code == 200
        controls = response.json()
        
        families = set()
        for ctrl in controls:
            family = ctrl["control_id"].split("-")[0]
            families.add(family)
        
        expected_families = set(EXPECTED_FAMILY_COUNTS.keys())
        assert families == expected_families, f"Missing families: {expected_families - families}, Extra families: {families - expected_families}"
    
    def test_family_control_counts(self, auth_token, nist_800_53_framework_id):
        """Verify each family has the expected number of controls"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/controls/{nist_800_53_framework_id}", headers=headers)
        assert response.status_code == 200
        controls = response.json()
        
        family_counts = {}
        for ctrl in controls:
            family = ctrl["control_id"].split("-")[0]
            family_counts[family] = family_counts.get(family, 0) + 1
        
        for family, expected_count in EXPECTED_FAMILY_COUNTS.items():
            actual_count = family_counts.get(family, 0)
            assert actual_count == expected_count, f"Family {family}: expected {expected_count}, got {actual_count}"


class TestNewFamiliesPresent:
    """Test that the 8 new families (MA, MP, PL, PM, PS, PT, SI, SR) are present"""
    
    @pytest.mark.parametrize("family", NEW_FAMILIES)
    def test_new_family_exists(self, auth_token, nist_800_53_framework_id, family):
        """Verify each new family has controls"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/controls/{nist_800_53_framework_id}", headers=headers)
        assert response.status_code == 200
        controls = response.json()
        
        family_controls = [c for c in controls if c["control_id"].startswith(f"{family}-")]
        expected_count = EXPECTED_FAMILY_COUNTS[family]
        assert len(family_controls) == expected_count, f"Family {family}: expected {expected_count} controls, got {len(family_controls)}"
    
    @pytest.mark.parametrize("family", NEW_FAMILIES)
    def test_new_family_controls_have_required_fields(self, auth_token, nist_800_53_framework_id, family):
        """Verify controls in new families have all required fields"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/controls/{nist_800_53_framework_id}", headers=headers)
        assert response.status_code == 200
        controls = response.json()
        
        family_controls = [c for c in controls if c["control_id"].startswith(f"{family}-")]
        for ctrl in family_controls:
            assert "control_id" in ctrl, f"Control missing control_id"
            assert "title" in ctrl, f"Control {ctrl.get('control_id')} missing title"
            assert "category" in ctrl, f"Control {ctrl.get('control_id')} missing category"
            assert "description" in ctrl, f"Control {ctrl.get('control_id')} missing description"


class TestNewFamilyCCIs:
    """Test that new families have CCIs defined"""
    
    @pytest.mark.parametrize("control_id,expected_cci_count", list(NEW_FAMILY_CCI_SAMPLES.items()))
    def test_new_family_control_has_ccis(self, auth_token, nist_800_53_framework_id, control_id, expected_cci_count):
        """Verify controls in new families have CCIs"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(
            f"{BASE_URL}/api/controls/{nist_800_53_framework_id}/detail/{control_id}",
            headers=headers
        )
        assert response.status_code == 200, f"Failed to get detail for {control_id}: {response.text}"
        data = response.json()
        
        assert "ccis" in data, f"Control {control_id} response missing 'ccis' field"
        assert "cci_count" in data, f"Control {control_id} response missing 'cci_count' field"
        assert data["cci_count"] >= expected_cci_count, f"Control {control_id}: expected at least {expected_cci_count} CCIs, got {data['cci_count']}"
    
    def test_si_2_has_ccis_with_correct_structure(self, auth_token, nist_800_53_framework_id):
        """Verify SI-2 (Flaw Remediation) has CCIs with correct structure"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(
            f"{BASE_URL}/api/controls/{nist_800_53_framework_id}/detail/SI-2",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["cci_count"] >= 3, f"SI-2 should have at least 3 CCIs"
        for cci in data["ccis"]:
            assert "cci_id" in cci, "CCI missing cci_id"
            assert "definition" in cci, "CCI missing definition"
            assert "type" in cci, "CCI missing type"
            assert cci["type"] in ["policy", "procedure", "implementation", "technical", "review", "monitoring"]


class TestControlDetailForNewFamilies:
    """Test control detail page works for new family controls"""
    
    @pytest.mark.parametrize("control_id", ["MA-1", "MP-1", "PL-2", "PM-9", "PS-4", "PT-3", "SI-4", "SR-2"])
    def test_control_detail_returns_valid_response(self, auth_token, nist_800_53_framework_id, control_id):
        """Verify control detail endpoint works for new family controls"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(
            f"{BASE_URL}/api/controls/{nist_800_53_framework_id}/detail/{control_id}",
            headers=headers
        )
        assert response.status_code == 200, f"Failed to get detail for {control_id}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "control" in data, f"Response missing 'control' field"
        assert "ccis" in data, f"Response missing 'ccis' field"
        assert "cci_count" in data, f"Response missing 'cci_count' field"
        assert "cross_framework_mappings" in data, f"Response missing 'cross_framework_mappings' field"
        assert "policy_mappings" in data, f"Response missing 'policy_mappings' field"
        
        # Verify control data
        ctrl = data["control"]
        assert ctrl["control_id"] == control_id
        assert ctrl["title"] is not None and len(ctrl["title"]) > 0


class TestExistingFeaturesStillWork:
    """Regression tests to ensure existing features still work"""
    
    def test_login_works(self):
        """Verify login still works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo-admin@grc.com",
            "password": "DemoAdmin123!"
        })
        assert response.status_code == 200
        assert "token" in response.json()
    
    def test_frameworks_endpoint_returns_all_frameworks(self, auth_token):
        """Verify frameworks endpoint returns all 12 frameworks"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/frameworks", headers=headers)
        assert response.status_code == 200
        frameworks = response.json()
        assert len(frameworks) >= 12, f"Expected at least 12 frameworks, got {len(frameworks)}"
    
    def test_dashboard_analytics_works(self, auth_token):
        """Verify dashboard analytics endpoint works"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/analytics/dashboard", headers=headers)
        assert response.status_code == 200
    
    def test_mappings_endpoint_works(self, auth_token):
        """Verify mappings endpoint works"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/mappings", headers=headers)
        assert response.status_code == 200
    
    def test_existing_ac_controls_still_have_ccis(self, auth_token, nist_800_53_framework_id):
        """Verify existing AC controls still have CCIs"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(
            f"{BASE_URL}/api/controls/{nist_800_53_framework_id}/detail/AC-1",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["cci_count"] == 5, f"AC-1 should have 5 CCIs, got {data['cci_count']}"
