"""
Test CCI (Control Correlation Identifiers) and Control Detail endpoints
Tests the new CCI layer for NIST SP 800-53 controls
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEMO_ADMIN_EMAIL = "demo-admin@grc.com"
DEMO_ADMIN_PASSWORD = "DemoAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for demo admin"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEMO_ADMIN_EMAIL,
        "password": DEMO_ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


@pytest.fixture(scope="module")
def nist_800_53_framework_id(auth_headers):
    """Get NIST SP 800-53 framework ID"""
    response = requests.get(f"{BASE_URL}/api/frameworks", headers=auth_headers)
    assert response.status_code == 200
    frameworks = response.json()
    nist_fw = next((fw for fw in frameworks if fw["name"] == "NIST SP 800-53"), None)
    assert nist_fw is not None, "NIST SP 800-53 framework not found"
    return nist_fw["id"]


@pytest.fixture(scope="module")
def iso_27001_framework_id(auth_headers):
    """Get ISO 27001 framework ID"""
    response = requests.get(f"{BASE_URL}/api/frameworks", headers=auth_headers)
    assert response.status_code == 200
    frameworks = response.json()
    iso_fw = next((fw for fw in frameworks if fw["name"] == "ISO 27001"), None)
    assert iso_fw is not None, "ISO 27001 framework not found"
    return iso_fw["id"]


class TestFrameworksControlCounts:
    """Test that frameworks page shows control counts for all 12 frameworks"""
    
    def test_all_12_frameworks_exist(self, auth_headers):
        """Verify all 12 frameworks are present"""
        response = requests.get(f"{BASE_URL}/api/frameworks", headers=auth_headers)
        assert response.status_code == 200
        frameworks = response.json()
        assert len(frameworks) == 12, f"Expected 12 frameworks, got {len(frameworks)}"
        
        expected_names = [
            "NIST Cybersecurity Framework", "NIST SP 800-53", "NIST SP 800-171",
            "ISO 27001", "GDPR", "HIPAA", "SOC 2", "CMMC", "NIS2",
            "NIST AI Risk Management Framework", "Financial Services AI Risk Management Framework", "StateRAMP"
        ]
        actual_names = [fw["name"] for fw in frameworks]
        for name in expected_names:
            assert name in actual_names, f"Framework '{name}' not found"
    
    def test_frameworks_have_controls(self, auth_headers):
        """Verify each framework has controls"""
        response = requests.get(f"{BASE_URL}/api/frameworks", headers=auth_headers)
        frameworks = response.json()
        
        for fw in frameworks:
            ctrl_response = requests.get(f"{BASE_URL}/api/controls/{fw['id']}", headers=auth_headers)
            assert ctrl_response.status_code == 200, f"Failed to get controls for {fw['name']}"
            controls = ctrl_response.json()
            assert len(controls) > 0, f"Framework {fw['name']} has no controls"


class TestControlDetailEndpoint:
    """Test GET /api/controls/{framework_id}/detail/{control_id}"""
    
    def test_ac1_has_5_ccis(self, auth_headers, nist_800_53_framework_id):
        """NIST SP 800-53 AC-1 should have 5 CCIs"""
        response = requests.get(
            f"{BASE_URL}/api/controls/{nist_800_53_framework_id}/detail/AC-1",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify control info
        assert data["control"]["control_id"] == "AC-1"
        assert data["control"]["title"] == "Policy and Procedures"
        assert data["control"]["category"] == "Access Control"
        assert "description" in data["control"]
        
        # Verify CCI count
        assert data["cci_count"] == 5, f"Expected 5 CCIs for AC-1, got {data['cci_count']}"
        assert len(data["ccis"]) == 5
    
    def test_ac2_has_10_ccis(self, auth_headers, nist_800_53_framework_id):
        """NIST SP 800-53 AC-2 should have 10 CCIs"""
        response = requests.get(
            f"{BASE_URL}/api/controls/{nist_800_53_framework_id}/detail/AC-2",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["cci_count"] == 10, f"Expected 10 CCIs for AC-2, got {data['cci_count']}"
        assert len(data["ccis"]) == 10
    
    def test_cci_card_structure(self, auth_headers, nist_800_53_framework_id):
        """Verify CCI cards have required fields: cci_id, definition, type"""
        response = requests.get(
            f"{BASE_URL}/api/controls/{nist_800_53_framework_id}/detail/AC-1",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        for cci in data["ccis"]:
            assert "cci_id" in cci, "CCI missing cci_id"
            assert "definition" in cci, "CCI missing definition"
            assert "type" in cci, "CCI missing type"
            assert cci["type"] in ["policy", "procedure", "implementation", "technical", "review", "monitoring"]
    
    def test_cross_framework_mappings_present(self, auth_headers, nist_800_53_framework_id):
        """Verify cross-framework mappings section is present"""
        response = requests.get(
            f"{BASE_URL}/api/controls/{nist_800_53_framework_id}/detail/AC-1",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "cross_framework_mappings" in data
        assert len(data["cross_framework_mappings"]) > 0, "AC-1 should have cross-framework mappings"
    
    def test_policy_mappings_present(self, auth_headers, nist_800_53_framework_id):
        """Verify policy mappings section is present"""
        response = requests.get(
            f"{BASE_URL}/api/controls/{nist_800_53_framework_id}/detail/AC-1",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "policy_mappings" in data
        # AC-1 should have at least one policy mapping from seed data
        assert len(data["policy_mappings"]) >= 1


class TestCCIEndpoint:
    """Test GET /api/ccis/{framework_id}/{control_id}"""
    
    def test_get_ccis_for_ac1(self, auth_headers, nist_800_53_framework_id):
        """Get CCIs for AC-1 via dedicated endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/ccis/{nist_800_53_framework_id}/AC-1",
            headers=auth_headers
        )
        assert response.status_code == 200
        ccis = response.json()
        assert len(ccis) == 5
    
    def test_get_ccis_for_ac2(self, auth_headers, nist_800_53_framework_id):
        """Get CCIs for AC-2 via dedicated endpoint"""
        response = requests.get(
            f"{BASE_URL}/api/ccis/{nist_800_53_framework_id}/AC-2",
            headers=auth_headers
        )
        assert response.status_code == 200
        ccis = response.json()
        assert len(ccis) == 10


class TestNonNISTFrameworksCCIs:
    """Test that non-NIST frameworks show 'No CCIs available'"""
    
    def test_iso_27001_control_has_no_ccis(self, auth_headers, iso_27001_framework_id):
        """ISO 27001 controls should have 0 CCIs"""
        # First get a control ID from ISO 27001
        response = requests.get(
            f"{BASE_URL}/api/controls/{iso_27001_framework_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        controls = response.json()
        assert len(controls) > 0
        
        control_id = controls[0]["control_id"]
        
        # Get control detail
        detail_response = requests.get(
            f"{BASE_URL}/api/controls/{iso_27001_framework_id}/detail/{control_id}",
            headers=auth_headers
        )
        assert detail_response.status_code == 200
        data = detail_response.json()
        
        assert data["cci_count"] == 0, f"ISO 27001 control should have 0 CCIs, got {data['cci_count']}"
        assert len(data["ccis"]) == 0


class TestControlNotFound:
    """Test 404 for non-existent controls"""
    
    def test_invalid_control_returns_404(self, auth_headers, nist_800_53_framework_id):
        """Non-existent control should return 404"""
        response = requests.get(
            f"{BASE_URL}/api/controls/{nist_800_53_framework_id}/detail/INVALID-CTRL",
            headers=auth_headers
        )
        assert response.status_code == 404


class TestControlsList:
    """Test controls list for frameworks"""
    
    def test_nist_800_53_has_50_controls(self, auth_headers, nist_800_53_framework_id):
        """NIST SP 800-53 should have 50 controls"""
        response = requests.get(
            f"{BASE_URL}/api/controls/{nist_800_53_framework_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        controls = response.json()
        assert len(controls) == 50, f"Expected 50 controls, got {len(controls)}"
    
    def test_controls_have_required_fields(self, auth_headers, nist_800_53_framework_id):
        """Controls should have control_id, title, category, description"""
        response = requests.get(
            f"{BASE_URL}/api/controls/{nist_800_53_framework_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        controls = response.json()
        
        for ctrl in controls[:5]:  # Check first 5
            assert "control_id" in ctrl
            assert "title" in ctrl
            assert "category" in ctrl
            assert "description" in ctrl
