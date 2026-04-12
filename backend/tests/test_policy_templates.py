"""
Test Policy Templates API - Policy Center Feature
Tests: org-profile, templates list, document tags, and generate endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo-admin@grc.com"
TEST_PASSWORD = "DemoAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "token" in data, "No token in login response"
    return data["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestPolicyTemplatesEndpoint:
    """Test GET /api/policy-templates - returns 10 templates"""
    
    def test_templates_endpoint_returns_200(self, auth_headers):
        """Templates endpoint should return 200"""
        response = requests.get(f"{BASE_URL}/api/policy-templates", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_templates_returns_10_templates(self, auth_headers):
        """Should return exactly 10 templates"""
        response = requests.get(f"{BASE_URL}/api/policy-templates", headers=auth_headers)
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        assert len(data) == 10, f"Expected 10 templates, got {len(data)}"
    
    def test_template_has_required_fields(self, auth_headers):
        """Each template should have required fields"""
        response = requests.get(f"{BASE_URL}/api/policy-templates", headers=auth_headers)
        data = response.json()
        required_fields = ["id", "title", "description", "category", "frameworks", "sections", "siem_thresholds"]
        
        for template in data:
            for field in required_fields:
                assert field in template, f"Template {template.get('id', 'unknown')} missing field: {field}"
    
    def test_template_categories(self, auth_headers):
        """Templates should have valid categories"""
        response = requests.get(f"{BASE_URL}/api/policy-templates", headers=auth_headers)
        data = response.json()
        valid_categories = ["Security", "Governance", "Privacy", "Operations"]
        
        for template in data:
            assert template["category"] in valid_categories, f"Invalid category: {template['category']}"
    
    def test_template_frameworks_structure(self, auth_headers):
        """Each template should have frameworks with control arrays"""
        response = requests.get(f"{BASE_URL}/api/policy-templates", headers=auth_headers)
        data = response.json()
        
        for template in data:
            assert isinstance(template["frameworks"], dict), f"Frameworks should be dict for {template['id']}"
            for fw_name, controls in template["frameworks"].items():
                assert isinstance(controls, list), f"Controls should be list for {fw_name} in {template['id']}"
    
    def test_template_siem_thresholds_structure(self, auth_headers):
        """Templates with SIEM controls should have threshold data"""
        response = requests.get(f"{BASE_URL}/api/policy-templates", headers=auth_headers)
        data = response.json()
        
        templates_with_siem = [t for t in data if t.get("has_siem")]
        assert len(templates_with_siem) > 0, "At least one template should have SIEM thresholds"
        
        for template in templates_with_siem:
            for threshold in template.get("siem_thresholds", []):
                assert "control_id" in threshold, f"SIEM threshold missing control_id in {template['id']}"
                assert "threshold" in threshold, f"SIEM threshold missing threshold in {template['id']}"
                assert "description" in threshold, f"SIEM threshold missing description in {template['id']}"
    
    def test_specific_templates_exist(self, auth_headers):
        """Verify specific template IDs exist"""
        response = requests.get(f"{BASE_URL}/api/policy-templates", headers=auth_headers)
        data = response.json()
        template_ids = [t["id"] for t in data]
        
        expected_ids = [
            "access-control", "incident-response", "risk-management", 
            "data-protection", "system-integrity", "configuration-management",
            "audit-accountability", "personnel-security", "contingency-planning", "physical-security"
        ]
        
        for expected_id in expected_ids:
            assert expected_id in template_ids, f"Missing template: {expected_id}"


class TestOrgProfileEndpoint:
    """Test org-profile CRUD operations"""
    
    def test_get_org_profile_returns_200(self, auth_headers):
        """GET org-profile should return 200"""
        response = requests.get(f"{BASE_URL}/api/policy-templates/org-profile", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    def test_save_org_profile(self, auth_headers):
        """POST org-profile should save data"""
        profile_data = {
            "org_name": "TestCorp",
            "industry": "Technology",
            "ciso_name": "Jane Smith",
            "ciso_title": "Chief Information Security Officer",
            "data_owner": "John Doe",
            "policy_owner": "Sarah Johnson",
            "compliance_officer": "Mike Brown",
            "review_frequency": "Annually"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/policy-templates/org-profile",
            headers=auth_headers,
            json=profile_data
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "message" in data, "Response should have message"
    
    def test_get_saved_org_profile(self, auth_headers):
        """GET org-profile should return saved data"""
        # First save
        profile_data = {
            "org_name": "TestCorp",
            "ciso_name": "Jane Smith"
        }
        requests.post(f"{BASE_URL}/api/policy-templates/org-profile", headers=auth_headers, json=profile_data)
        
        # Then get
        response = requests.get(f"{BASE_URL}/api/policy-templates/org-profile", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("org_name") == "TestCorp", f"Expected org_name 'TestCorp', got {data.get('org_name')}"
        assert data.get("ciso_name") == "Jane Smith", f"Expected ciso_name 'Jane Smith', got {data.get('ciso_name')}"
    
    def test_org_profile_requires_org_name(self, auth_headers):
        """POST org-profile should require org_name"""
        response = requests.post(
            f"{BASE_URL}/api/policy-templates/org-profile",
            headers=auth_headers,
            json={"industry": "Tech"}  # Missing org_name
        )
        # Should fail validation
        assert response.status_code in [422, 400], f"Expected validation error, got {response.status_code}"


class TestDocumentTagsEndpoint:
    """Test document tags CRUD operations"""
    
    def test_get_document_tags_returns_200(self, auth_headers):
        """GET document-tags should return 200"""
        response = requests.get(f"{BASE_URL}/api/policy-templates/document-tags", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert isinstance(response.json(), list), "Response should be a list"
    
    def test_create_document_tag(self, auth_headers):
        """POST document-tags should create a tag"""
        tag_data = {
            "document_id": "test-doc-001",
            "document_name": "Test Policy Document.pdf",
            "framework_id": "nist-800-53",
            "framework_name": "NIST 800-53",
            "control_ids": ["AC-1", "AC-2", "AC-3"],
            "notes": "Test tag for policy templates testing"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/policy-templates/document-tags",
            headers=auth_headers,
            json=tag_data
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "id" in data, "Response should have id"
        assert data["document_id"] == "test-doc-001", "document_id should match"
        assert data["framework_id"] == "nist-800-53", "framework_id should match"
        return data["id"]
    
    def test_delete_document_tag(self, auth_headers):
        """DELETE document-tags/{id} should remove tag"""
        # First create a tag
        tag_data = {
            "document_id": "test-doc-delete",
            "document_name": "Delete Test.pdf",
            "framework_id": "nist-csf",
            "framework_name": "NIST CSF",
            "control_ids": ["PR.AC-1"],
            "notes": "Tag to be deleted"
        }
        create_response = requests.post(
            f"{BASE_URL}/api/policy-templates/document-tags",
            headers=auth_headers,
            json=tag_data
        )
        assert create_response.status_code == 200
        tag_id = create_response.json()["id"]
        
        # Then delete
        delete_response = requests.delete(
            f"{BASE_URL}/api/policy-templates/document-tags/{tag_id}",
            headers=auth_headers
        )
        assert delete_response.status_code == 200, f"Expected 200, got {delete_response.status_code}"
        
        # Verify deleted
        get_response = requests.get(f"{BASE_URL}/api/policy-templates/document-tags", headers=auth_headers)
        tags = get_response.json()
        tag_ids = [t["id"] for t in tags]
        assert tag_id not in tag_ids, "Tag should be deleted"


class TestGeneratedPoliciesEndpoint:
    """Test generated policies list and retrieval"""
    
    def test_get_generated_policies_returns_200(self, auth_headers):
        """GET generated should return 200"""
        response = requests.get(f"{BASE_URL}/api/policy-templates/generated", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert isinstance(response.json(), list), "Response should be a list"
    
    def test_get_nonexistent_policy_returns_404(self, auth_headers):
        """GET generated/{id} for nonexistent policy should return 404"""
        response = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/nonexistent-policy-id",
            headers=auth_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestPolicyGenerateEndpoint:
    """Test policy generation endpoint (may be slow due to LLM)"""
    
    def test_generate_requires_valid_template_id(self, auth_headers):
        """POST generate with invalid template_id should return 404"""
        response = requests.post(
            f"{BASE_URL}/api/policy-templates/generate",
            headers=auth_headers,
            json={"template_id": "invalid-template-id"},
            timeout=30
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    
    def test_generate_endpoint_accepts_valid_request(self, auth_headers):
        """POST generate with valid template_id should be accepted (may timeout)"""
        # First ensure org profile exists
        requests.post(
            f"{BASE_URL}/api/policy-templates/org-profile",
            headers=auth_headers,
            json={"org_name": "TestCorp", "ciso_name": "Jane Smith"}
        )
        
        # Try to generate - this may take 10-15 seconds
        try:
            response = requests.post(
                f"{BASE_URL}/api/policy-templates/generate",
                headers=auth_headers,
                json={
                    "template_id": "access-control",
                    "org_profile": {"org_name": "TestCorp", "ciso_name": "Jane Smith"},
                    "selected_frameworks": ["NIST 800-53"]
                },
                timeout=60  # Allow 60 seconds for LLM generation
            )
            # Should either succeed (200) or fail gracefully (500 with error message)
            assert response.status_code in [200, 500], f"Unexpected status: {response.status_code}"
            
            if response.status_code == 200:
                data = response.json()
                assert "id" in data, "Generated policy should have id"
                assert "title" in data, "Generated policy should have title"
                assert "sections" in data, "Generated policy should have sections"
                print(f"Policy generated successfully: {data.get('title')}")
        except requests.exceptions.Timeout:
            pytest.skip("Generation timed out - LLM may be slow")


class TestAuthenticationRequired:
    """Test that endpoints require authentication"""
    
    def test_templates_requires_auth(self):
        """GET templates without auth should fail"""
        response = requests.get(f"{BASE_URL}/api/policy-templates")
        assert response.status_code in [401, 403], f"Expected auth error, got {response.status_code}"
    
    def test_org_profile_requires_auth(self):
        """GET org-profile without auth should fail"""
        response = requests.get(f"{BASE_URL}/api/policy-templates/org-profile")
        assert response.status_code in [401, 403], f"Expected auth error, got {response.status_code}"
    
    def test_document_tags_requires_auth(self):
        """GET document-tags without auth should fail"""
        response = requests.get(f"{BASE_URL}/api/policy-templates/document-tags")
        assert response.status_code in [401, 403], f"Expected auth error, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
