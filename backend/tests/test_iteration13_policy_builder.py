"""
Iteration 13 Backend Tests
Tests for:
1. Policy Builder - control families, questions, drafts CRUD
2. Vendor edit/delete endpoints
3. Cross-framework mappings (existing)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEMO_ADMIN = {"email": "demo-admin@grc.com", "password": "DemoAdmin123!"}
DEMO_VIEWER = {"email": "demo-user@grc.com", "password": "DemoUser123!"}


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_ADMIN)
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def viewer_token():
    """Get viewer auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_VIEWER)
    assert response.status_code == 200, f"Viewer login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture
def viewer_headers(viewer_token):
    return {"Authorization": f"Bearer {viewer_token}", "Content-Type": "application/json"}


class TestPolicyBuilderControlFamilies:
    """Tests for GET /api/policy-builder/control-families"""
    
    def test_get_control_families_returns_20_families(self, admin_headers):
        """Should return 20 NIST 800-53 control families"""
        response = requests.get(f"{BASE_URL}/api/policy-builder/control-families", headers=admin_headers)
        assert response.status_code == 200
        families = response.json()
        assert len(families) == 20, f"Expected 20 families, got {len(families)}"
        
        # Verify structure
        for family in families:
            assert "id" in family
            assert "name" in family
        
        # Verify some expected families
        family_ids = [f["id"] for f in families]
        assert "AC" in family_ids, "Access Control (AC) should be present"
        assert "AT" in family_ids, "Awareness and Training (AT) should be present"
        assert "AU" in family_ids, "Audit and Accountability (AU) should be present"
        print(f"✓ Control families endpoint returns {len(families)} families")


class TestPolicyBuilderQuestions:
    """Tests for GET /api/policy-builder/questions/{control_family}"""
    
    def test_get_ac_questions_returns_61(self, admin_headers):
        """AC (Access Control) should have 61 questions"""
        response = requests.get(f"{BASE_URL}/api/policy-builder/questions/AC", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 61, f"Expected 61 AC questions, got {data['total']}"
        assert data["control_family"] == "AC"
        assert data["control_family_name"] == "Access Control"
        assert len(data["questions"]) == 61
        print(f"✓ AC questions: {data['total']} questions")
    
    def test_get_at_questions_returns_37(self, admin_headers):
        """AT (Awareness and Training) should have 37 questions"""
        response = requests.get(f"{BASE_URL}/api/policy-builder/questions/AT", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 37, f"Expected 37 AT questions, got {data['total']}"
        assert data["control_family"] == "AT"
        assert data["control_family_name"] == "Awareness and Training"
        print(f"✓ AT questions: {data['total']} questions")
    
    def test_get_questions_invalid_family_returns_404(self, admin_headers):
        """Invalid control family should return 404"""
        response = requests.get(f"{BASE_URL}/api/policy-builder/questions/INVALID", headers=admin_headers)
        assert response.status_code == 404
        print("✓ Invalid control family returns 404")


class TestPolicyBuilderDrafts:
    """Tests for /api/policy-builder/drafts CRUD"""
    
    def test_get_drafts_returns_array(self, admin_headers):
        """GET /api/policy-builder/drafts should return array"""
        response = requests.get(f"{BASE_URL}/api/policy-builder/drafts", headers=admin_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        print(f"✓ Drafts endpoint returns array with {len(response.json())} items")
    
    def test_create_draft_admin_succeeds(self, admin_headers):
        """Admin should be able to create draft"""
        payload = {
            "policy_name": "TEST_Admin Draft Policy",
            "framework": "nist-800-53",
            "control_family": "AC",
            "answers": {"q_0": "Test answer 1", "q_1": "Test answer 2"}
        }
        response = requests.post(f"{BASE_URL}/api/policy-builder/drafts", headers=admin_headers, json=payload)
        assert response.status_code == 200, f"Create draft failed: {response.text}"
        data = response.json()
        assert data["policy_name"] == "TEST_Admin Draft Policy"
        assert data["control_family"] == "AC"
        assert data["answered_count"] == 2
        assert data["status"] == "draft"
        print(f"✓ Admin created draft: {data['id']}")
        return data["id"]
    
    def test_create_draft_viewer_blocked(self, viewer_headers):
        """Demo viewer should be blocked from creating drafts (403)"""
        payload = {
            "policy_name": "TEST_Viewer Draft Policy",
            "framework": "nist-800-53",
            "control_family": "AC",
            "answers": {}
        }
        response = requests.post(f"{BASE_URL}/api/policy-builder/drafts", headers=viewer_headers, json=payload)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Demo viewer blocked from creating drafts (403)")


class TestVendorEditDelete:
    """Tests for PUT and DELETE /api/vendors/{id}"""
    
    def test_get_vendors_returns_list(self, admin_headers):
        """GET /api/vendors should return list"""
        response = requests.get(f"{BASE_URL}/api/vendors", headers=admin_headers)
        assert response.status_code == 200
        vendors = response.json()
        assert isinstance(vendors, list)
        print(f"✓ Vendors endpoint returns {len(vendors)} vendors")
        return vendors
    
    def test_create_vendor_for_edit_delete_test(self, admin_headers):
        """Create a test vendor for edit/delete testing"""
        payload = {
            "name": "TEST_Edit Delete Vendor",
            "contact_email": "test@editdelete.com",
            "risk_level": "low",
            "assessment_status": "pending"
        }
        response = requests.post(f"{BASE_URL}/api/vendors", headers=admin_headers, json=payload)
        assert response.status_code == 200, f"Create vendor failed: {response.text}"
        data = response.json()
        assert data["name"] == "TEST_Edit Delete Vendor"
        print(f"✓ Created test vendor: {data['id']}")
        return data["id"]
    
    def test_update_vendor_admin_succeeds(self, admin_headers):
        """Admin should be able to update vendor"""
        # First create a vendor
        create_payload = {
            "name": "TEST_Update Vendor",
            "contact_email": "update@test.com",
            "risk_level": "low",
            "assessment_status": "pending"
        }
        create_response = requests.post(f"{BASE_URL}/api/vendors", headers=admin_headers, json=create_payload)
        assert create_response.status_code == 200
        vendor_id = create_response.json()["id"]
        
        # Update the vendor
        update_payload = {
            "name": "TEST_Update Vendor UPDATED",
            "contact_email": "updated@test.com",
            "risk_level": "high",
            "assessment_status": "completed"
        }
        response = requests.put(f"{BASE_URL}/api/vendors/{vendor_id}", headers=admin_headers, json=update_payload)
        assert response.status_code == 200, f"Update vendor failed: {response.text}"
        data = response.json()
        assert data["name"] == "TEST_Update Vendor UPDATED"
        assert data["risk_level"] == "high"
        assert data["assessment_status"] == "completed"
        print(f"✓ Admin updated vendor: {vendor_id}")
        
        # Cleanup - delete the vendor
        requests.delete(f"{BASE_URL}/api/vendors/{vendor_id}", headers=admin_headers)
    
    def test_delete_vendor_admin_succeeds(self, admin_headers):
        """Admin should be able to delete vendor"""
        # First create a vendor
        create_payload = {
            "name": "TEST_Delete Vendor",
            "contact_email": "delete@test.com",
            "risk_level": "low",
            "assessment_status": "pending"
        }
        create_response = requests.post(f"{BASE_URL}/api/vendors", headers=admin_headers, json=create_payload)
        assert create_response.status_code == 200
        vendor_id = create_response.json()["id"]
        
        # Delete the vendor
        response = requests.delete(f"{BASE_URL}/api/vendors/{vendor_id}", headers=admin_headers)
        assert response.status_code == 200, f"Delete vendor failed: {response.text}"
        assert response.json()["message"] == "Vendor deleted"
        
        # Verify deletion
        get_response = requests.get(f"{BASE_URL}/api/vendors", headers=admin_headers)
        vendors = get_response.json()
        vendor_ids = [v["id"] for v in vendors]
        assert vendor_id not in vendor_ids, "Vendor should be deleted"
        print(f"✓ Admin deleted vendor: {vendor_id}")
    
    def test_update_vendor_viewer_blocked(self, viewer_headers, admin_headers):
        """Demo viewer should be blocked from updating vendors (403)"""
        # Get a vendor ID
        vendors_response = requests.get(f"{BASE_URL}/api/vendors", headers=admin_headers)
        vendors = vendors_response.json()
        if not vendors:
            pytest.skip("No vendors to test with")
        vendor_id = vendors[0]["id"]
        
        update_payload = {
            "name": "Viewer Update Attempt",
            "contact_email": "viewer@test.com",
            "risk_level": "low",
            "assessment_status": "pending"
        }
        response = requests.put(f"{BASE_URL}/api/vendors/{vendor_id}", headers=viewer_headers, json=update_payload)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Demo viewer blocked from updating vendors (403)")
    
    def test_delete_vendor_viewer_blocked(self, viewer_headers, admin_headers):
        """Demo viewer should be blocked from deleting vendors (403)"""
        # Get a vendor ID
        vendors_response = requests.get(f"{BASE_URL}/api/vendors", headers=admin_headers)
        vendors = vendors_response.json()
        if not vendors:
            pytest.skip("No vendors to test with")
        vendor_id = vendors[0]["id"]
        
        response = requests.delete(f"{BASE_URL}/api/vendors/{vendor_id}", headers=viewer_headers)
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✓ Demo viewer blocked from deleting vendors (403)")


class TestCrossFrameworkMappings:
    """Tests for cross-framework mappings (regression)"""
    
    def test_get_cross_framework_matrix(self, admin_headers):
        """GET /api/cross-framework-mappings/matrix should return data"""
        response = requests.get(f"{BASE_URL}/api/cross-framework-mappings/matrix", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "frameworks" in data
        assert "mappings" in data
        print(f"✓ Cross-framework matrix: {len(data['frameworks'])} frameworks, {len(data['mappings'])} mappings")


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_drafts(self, admin_headers):
        """Delete TEST_ prefixed drafts"""
        response = requests.get(f"{BASE_URL}/api/policy-builder/drafts", headers=admin_headers)
        drafts = response.json()
        deleted = 0
        for draft in drafts:
            if draft.get("policy_name", "").startswith("TEST_"):
                requests.delete(f"{BASE_URL}/api/policy-builder/drafts/{draft['id']}", headers=admin_headers)
                deleted += 1
        print(f"✓ Cleaned up {deleted} test drafts")
    
    def test_cleanup_test_vendors(self, admin_headers):
        """Delete TEST_ prefixed vendors"""
        response = requests.get(f"{BASE_URL}/api/vendors", headers=admin_headers)
        vendors = response.json()
        deleted = 0
        for vendor in vendors:
            if vendor.get("name", "").startswith("TEST_"):
                requests.delete(f"{BASE_URL}/api/vendors/{vendor['id']}", headers=admin_headers)
                deleted += 1
        print(f"✓ Cleaned up {deleted} test vendors")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
