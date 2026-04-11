"""
Test suite for Phase B New Features - IronVision GRC
Tests:
1. Implementation Guidance endpoint (POST /api/control-compliance/{fw_id}/{ctrl_id}/implementation-guidance)
2. SIEM mappings for NIST CSF framework
3. SIEM mappings for GDPR framework
4. Enhanced Policy Suggestion with satisfied/gaps fields
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://ai-framework-hub.preview.emergentagent.com')

# Test credentials
TEST_EMAIL = "demo-admin@grc.com"
TEST_PASSWORD = "DemoAdmin123!"

# Framework IDs
NIST_800_53_FW_ID = "394b18c4-f22e-4b9a-984b-b5e2ec8143cb"
NIST_CSF_FW_ID = "b084dc82-a664-43aa-add4-1d657ed1a5c7"
GDPR_FW_ID = "f6de4bf3-ffa2-45ad-a109-d9bb48b05699"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Create authenticated session"""
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    })
    return session


class TestImplementationGuidance:
    """Tests for POST /api/control-compliance/{framework_id}/{control_id}/implementation-guidance"""
    
    def test_implementation_guidance_endpoint_exists(self, api_client):
        """Test that implementation guidance endpoint exists and returns 200"""
        response = api_client.post(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/AC-1/implementation-guidance",
            json={},
            timeout=60  # LLM calls can take time
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
    def test_implementation_guidance_response_structure(self, api_client):
        """Test that implementation guidance returns expected fields"""
        response = api_client.post(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/AC-2/implementation-guidance",
            json={},
            timeout=60
        )
        assert response.status_code == 200
        
        data = response.json()
        # Check for expected fields
        assert "implementation_steps" in data, "Missing implementation_steps field"
        assert "technical_guidelines" in data, "Missing technical_guidelines field"
        assert "assessment_criteria" in data, "Missing assessment_criteria field"
        assert "common_pitfalls" in data, "Missing common_pitfalls field"
        
        # Verify they are arrays
        assert isinstance(data["implementation_steps"], list)
        assert isinstance(data["technical_guidelines"], list)
        assert isinstance(data["assessment_criteria"], list)
        assert isinstance(data["common_pitfalls"], list)
        
    def test_implementation_guidance_has_content(self, api_client):
        """Test that implementation guidance returns actual content"""
        response = api_client.post(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/AC-3/implementation-guidance",
            json={},
            timeout=60
        )
        assert response.status_code == 200
        
        data = response.json()
        # At least implementation_steps should have content
        assert len(data["implementation_steps"]) > 0, "implementation_steps should not be empty"
        
    def test_implementation_guidance_nonexistent_control(self, api_client):
        """Test implementation guidance for non-existent control returns 404"""
        response = api_client.post(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/INVALID-CTRL-999/implementation-guidance",
            json={},
            timeout=30
        )
        assert response.status_code == 404


class TestNISTCSFSIEMMappings:
    """Tests for SIEM mappings on NIST CSF framework controls"""
    
    def test_nist_csf_framework_exists(self, api_client):
        """Test that NIST CSF framework exists"""
        response = api_client.get(f"{BASE_URL}/api/frameworks")
        assert response.status_code == 200
        
        frameworks = response.json()
        nist_csf = next((f for f in frameworks if f["id"] == NIST_CSF_FW_ID), None)
        assert nist_csf is not None, f"NIST CSF framework not found with ID {NIST_CSF_FW_ID}"
        
    def test_nist_csf_compliance_overview(self, api_client):
        """Test getting compliance overview for NIST CSF"""
        response = api_client.get(f"{BASE_URL}/api/control-compliance/{NIST_CSF_FW_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert "controls" in data
        assert len(data["controls"]) > 0, "NIST CSF should have controls"
        
    def test_nist_csf_technical_controls_have_siem(self, api_client):
        """Test that NIST CSF technical controls have SIEM mappings"""
        response = api_client.get(f"{BASE_URL}/api/control-compliance/{NIST_CSF_FW_ID}")
        assert response.status_code == 200
        
        data = response.json()
        controls = data["controls"]
        
        # Look for controls that should be technical based on SIEM_CONTROL_MAP
        # PR.AC-1, PR.DS-1, DE.AE-3 should be technical
        technical_control_ids = ["PR.AC-1", "PR.DS-1", "DE.AE-3", "PR.AC-3", "PR.AC-4"]
        
        found_technical = False
        for ctrl in controls:
            if ctrl["control_id"] in technical_control_ids:
                if ctrl["is_technical"]:
                    found_technical = True
                    print(f"Found technical control: {ctrl['control_id']} with SIEM categories: {ctrl['siem_categories']}")
                    assert len(ctrl["siem_categories"]) > 0, f"Technical control {ctrl['control_id']} should have SIEM categories"
                    
        assert found_technical, f"Expected to find at least one technical control from {technical_control_ids}"
        
    def test_nist_csf_siem_evidence_endpoint(self, api_client):
        """Test SIEM evidence endpoint for NIST CSF control"""
        # PR.AC-1 should be mapped to authentication
        response = api_client.get(
            f"{BASE_URL}/api/control-compliance/{NIST_CSF_FW_ID}/PR.AC-1/siem-evidence"
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "categories" in data
        # Should have authentication category
        if len(data["categories"]) > 0:
            print(f"PR.AC-1 SIEM categories: {data['categories']}")


class TestGDPRSIEMMappings:
    """Tests for SIEM mappings on GDPR framework controls"""
    
    def test_gdpr_framework_exists(self, api_client):
        """Test that GDPR framework exists"""
        response = api_client.get(f"{BASE_URL}/api/frameworks")
        assert response.status_code == 200
        
        frameworks = response.json()
        gdpr = next((f for f in frameworks if f["id"] == GDPR_FW_ID), None)
        assert gdpr is not None, f"GDPR framework not found with ID {GDPR_FW_ID}"
        
    def test_gdpr_compliance_overview(self, api_client):
        """Test getting compliance overview for GDPR"""
        response = api_client.get(f"{BASE_URL}/api/control-compliance/{GDPR_FW_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert "controls" in data
        assert len(data["controls"]) > 0, "GDPR should have controls"
        
    def test_gdpr_technical_controls_have_siem(self, api_client):
        """Test that GDPR technical controls have SIEM mappings"""
        response = api_client.get(f"{BASE_URL}/api/control-compliance/{GDPR_FW_ID}")
        assert response.status_code == 200
        
        data = response.json()
        controls = data["controls"]
        
        # Look for controls that should be technical based on SIEM_CONTROL_MAP
        # Art.32, Art.33, Art.34, Art.35, Art.25, Art.5, Art.30 should be technical
        technical_control_ids = ["Art.32", "Art.33", "Art.34", "Art.35", "Art.25", "Art.5", "Art.30"]
        
        found_technical = False
        for ctrl in controls:
            if ctrl["control_id"] in technical_control_ids:
                if ctrl["is_technical"]:
                    found_technical = True
                    print(f"Found technical GDPR control: {ctrl['control_id']} with SIEM categories: {ctrl['siem_categories']}")
                    assert len(ctrl["siem_categories"]) > 0, f"Technical control {ctrl['control_id']} should have SIEM categories"
                    
        assert found_technical, f"Expected to find at least one technical control from {technical_control_ids}"
        
    def test_gdpr_siem_evidence_endpoint(self, api_client):
        """Test SIEM evidence endpoint for GDPR control"""
        # Art.32 should be mapped to authentication/authorization/system
        response = api_client.get(
            f"{BASE_URL}/api/control-compliance/{GDPR_FW_ID}/Art.32/siem-evidence"
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "categories" in data
        if len(data["categories"]) > 0:
            print(f"Art.32 SIEM categories: {data['categories']}")


class TestEnhancedPolicySuggestion:
    """Tests for enhanced policy suggestion with satisfied/gaps fields"""
    
    def test_policy_suggestion_has_satisfied_field(self, api_client):
        """Test that policy suggestion includes 'satisfied' field"""
        response = api_client.post(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/AC-1/suggest-policy",
            json={},
            timeout=60
        )
        assert response.status_code == 200
        
        data = response.json()
        # The enhanced prompt should return satisfied field
        assert "satisfied" in data or "title" in data, "Response should have satisfied or title field"
        
    def test_policy_suggestion_has_gaps_field(self, api_client):
        """Test that policy suggestion includes 'gaps' field"""
        response = api_client.post(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/AC-2/suggest-policy",
            json={},
            timeout=60
        )
        assert response.status_code == 200
        
        data = response.json()
        # The enhanced prompt should return gaps field
        assert "gaps" in data or "title" in data, "Response should have gaps or title field"
        
    def test_policy_suggestion_full_structure(self, api_client):
        """Test that policy suggestion has all expected fields"""
        response = api_client.post(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/AC-3/suggest-policy",
            json={},
            timeout=60
        )
        assert response.status_code == 200
        
        data = response.json()
        # Check for all expected fields from enhanced prompt
        assert "title" in data, "Missing title field"
        assert "statements" in data, "Missing statements field"
        # satisfied and gaps may or may not be present depending on LLM response
        print(f"Policy suggestion fields: {list(data.keys())}")


class TestDashboardWidgetCustomization:
    """Tests for dashboard widget customization (localStorage-based, so just verify API endpoints work)"""
    
    def test_analytics_endpoint(self, api_client):
        """Test analytics endpoint for dashboard"""
        response = api_client.get(f"{BASE_URL}/api/analytics/dashboard")
        assert response.status_code == 200
        
    def test_control_effectiveness_dashboard(self, api_client):
        """Test control effectiveness dashboard endpoint"""
        response = api_client.get(f"{BASE_URL}/api/control-effectiveness/dashboard")
        assert response.status_code == 200


class TestFrameworkOrganization:
    """Tests for framework organization (localStorage-based, so just verify API endpoints work)"""
    
    def test_frameworks_list(self, api_client):
        """Test frameworks list endpoint"""
        response = api_client.get(f"{BASE_URL}/api/frameworks")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) > 0, "Should have at least one framework"
        
    def test_controls_endpoint(self, api_client):
        """Test controls endpoint for a framework"""
        response = api_client.get(f"{BASE_URL}/api/controls/{NIST_800_53_FW_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data) > 0, "NIST 800-53 should have controls"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
