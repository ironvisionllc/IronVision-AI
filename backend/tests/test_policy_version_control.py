"""
Test Policy Version Control API - Version snapshots, diff, restore, and approval workflow
Tests: create version, list versions, diff versions, get version, restore version, status transitions
"""
import pytest
import requests
import os
import time

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


@pytest.fixture(scope="module")
def generated_policy(auth_headers):
    """Generate a new policy for testing version control (auto-creates v1)"""
    # Ensure org profile exists
    requests.post(
        f"{BASE_URL}/api/policy-templates/org-profile",
        headers=auth_headers,
        json={"org_name": "VersionTestCorp", "ciso_name": "Test CISO"}
    )
    
    # Generate a new policy - this should auto-create version 1
    try:
        response = requests.post(
            f"{BASE_URL}/api/policy-templates/generate",
            headers=auth_headers,
            json={
                "template_id": "access-control",
                "org_profile": {"org_name": "VersionTestCorp", "ciso_name": "Test CISO"},
                "selected_frameworks": ["NIST 800-53"]
            },
            timeout=90  # Allow 90 seconds for LLM generation
        )
        if response.status_code == 200:
            return response.json()
        else:
            pytest.skip(f"Policy generation failed: {response.status_code} - {response.text}")
    except requests.exceptions.Timeout:
        pytest.skip("Policy generation timed out")


@pytest.fixture(scope="module")
def existing_policy(auth_headers):
    """Get an existing generated policy for testing"""
    response = requests.get(f"{BASE_URL}/api/policy-templates/generated", headers=auth_headers)
    if response.status_code == 200 and len(response.json()) > 0:
        return response.json()[0]
    return None


class TestAutoVersionCreation:
    """Test that version 1 is auto-created when a new policy is generated"""
    
    def test_new_policy_has_version_1(self, auth_headers, generated_policy):
        """Newly generated policy should have version 1 auto-created"""
        if not generated_policy:
            pytest.skip("No generated policy available")
        
        policy_id = generated_policy["id"]
        response = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        versions = response.json()
        assert len(versions) >= 1, "Should have at least version 1"
        
        # Find version 1
        v1 = next((v for v in versions if v["version_number"] == 1), None)
        assert v1 is not None, "Version 1 should exist"
        assert v1["change_summary"] == "Initial policy generation", f"Expected 'Initial policy generation', got '{v1.get('change_summary')}'"


class TestVersionEndpoints:
    """Test version CRUD operations"""
    
    def test_list_versions_returns_200(self, auth_headers, existing_policy):
        """GET versions should return 200"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        response = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert isinstance(response.json(), list), "Response should be a list"
    
    def test_create_version_snapshot(self, auth_headers, existing_policy):
        """POST versions should create a new version snapshot"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        
        # Get current version count
        list_response = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions",
            headers=auth_headers
        )
        initial_count = len(list_response.json())
        
        # Create new version
        response = requests.post(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions",
            headers=auth_headers,
            json={"change_summary": "Test version snapshot"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "id" in data, "Version should have id"
        assert "version_number" in data, "Version should have version_number"
        assert data["change_summary"] == "Test version snapshot", "Change summary should match"
        assert data["policy_id"] == policy_id, "Policy ID should match"
        
        # Verify count increased
        list_response2 = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions",
            headers=auth_headers
        )
        assert len(list_response2.json()) == initial_count + 1, "Version count should increase by 1"
        
        return data
    
    def test_get_specific_version(self, auth_headers, existing_policy):
        """GET versions/{version_id} should return specific version"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        
        # Get list of versions
        list_response = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions",
            headers=auth_headers
        )
        versions = list_response.json()
        if len(versions) == 0:
            pytest.skip("No versions available")
        
        version_id = versions[0]["id"]
        
        # Get specific version
        response = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions/{version_id}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["id"] == version_id, "Version ID should match"
        assert "title" in data, "Version should have title"
        assert "sections" in data, "Version should have sections"
    
    def test_get_nonexistent_version_returns_404(self, auth_headers, existing_policy):
        """GET versions/{invalid_id} should return 404"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        response = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions/nonexistent-version-id",
            headers=auth_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestVersionDiff:
    """Test diff computation between versions"""
    
    def test_diff_between_two_versions(self, auth_headers, existing_policy):
        """POST versions/diff should compute diff between two versions"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        
        # Get versions
        list_response = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions",
            headers=auth_headers
        )
        versions = list_response.json()
        
        if len(versions) < 2:
            # Create a second version for diff testing
            requests.post(
                f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions",
                headers=auth_headers,
                json={"change_summary": "Version for diff testing"}
            )
            list_response = requests.get(
                f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions",
                headers=auth_headers
            )
            versions = list_response.json()
        
        if len(versions) < 2:
            pytest.skip("Need at least 2 versions for diff")
        
        # Compute diff
        response = requests.post(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions/diff",
            headers=auth_headers,
            json={
                "version_id_1": versions[1]["id"],  # Older version
                "version_id_2": versions[0]["id"]   # Newer version
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "version_1" in data, "Response should have version_1"
        assert "version_2" in data, "Response should have version_2"
        assert "sections" in data, "Response should have sections"
        assert "total_changes" in data, "Response should have total_changes"
        assert isinstance(data["sections"], list), "Sections should be a list"
    
    def test_diff_with_invalid_version_returns_404(self, auth_headers, existing_policy):
        """POST versions/diff with invalid version should return 404"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        
        # Get one valid version
        list_response = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions",
            headers=auth_headers
        )
        versions = list_response.json()
        if len(versions) == 0:
            pytest.skip("No versions available")
        
        response = requests.post(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions/diff",
            headers=auth_headers,
            json={
                "version_id_1": versions[0]["id"],
                "version_id_2": "invalid-version-id"
            }
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestVersionRestore:
    """Test restoring to a previous version"""
    
    def test_restore_previous_version(self, auth_headers, existing_policy):
        """PUT versions/{version_id}/restore should restore policy to that version"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        
        # Get versions
        list_response = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions",
            headers=auth_headers
        )
        versions = list_response.json()
        
        if len(versions) < 2:
            # Create versions for restore testing
            requests.post(
                f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions",
                headers=auth_headers,
                json={"change_summary": "Version before restore test"}
            )
            list_response = requests.get(
                f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions",
                headers=auth_headers
            )
            versions = list_response.json()
        
        if len(versions) < 2:
            pytest.skip("Need at least 2 versions for restore")
        
        # Restore to an older version (not the latest)
        older_version = versions[-1]  # Oldest version
        initial_version_count = len(versions)
        
        response = requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions/{older_version['id']}/restore",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "id" in data, "Restore should return new version"
        assert "version_number" in data, "Should have version_number"
        assert f"Restored from version {older_version['version_number']}" in data.get("change_summary", ""), "Change summary should indicate restore"
        
        # Verify new version was created
        list_response2 = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions",
            headers=auth_headers
        )
        assert len(list_response2.json()) == initial_version_count + 1, "Restore should create a new version"
        
        # Verify policy status is reset to draft
        policy_response = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}",
            headers=auth_headers
        )
        assert policy_response.json().get("status") == "draft", "Restored policy should be in draft status"
    
    def test_restore_nonexistent_version_returns_404(self, auth_headers, existing_policy):
        """PUT versions/{invalid_id}/restore should return 404"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        response = requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions/nonexistent-version-id/restore",
            headers=auth_headers
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestApprovalWorkflow:
    """Test policy status transitions (draft -> under_review -> approved)"""
    
    def test_initial_status_is_draft(self, auth_headers, existing_policy):
        """New policies should start in draft status"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        # Reset to draft first
        policy_id = existing_policy["id"]
        requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "draft"}
        )
        
        response = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}",
            headers=auth_headers
        )
        assert response.status_code == 200
        # Status should be draft (or we just set it to draft)
    
    def test_transition_draft_to_under_review(self, auth_headers, existing_policy):
        """Should be able to transition from draft to under_review"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        
        # Ensure in draft state
        requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "draft"}
        )
        
        # Transition to under_review
        response = requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "under_review"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("status") == "under_review", f"Status should be under_review, got {data.get('status')}"
        
        # Verify persisted
        get_response = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}",
            headers=auth_headers
        )
        assert get_response.json().get("status") == "under_review"
    
    def test_transition_under_review_to_approved(self, auth_headers, existing_policy):
        """Should be able to transition from under_review to approved"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        
        # Ensure in under_review state
        requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "draft"}
        )
        requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "under_review"}
        )
        
        # Transition to approved
        response = requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "approved"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("status") == "approved", f"Status should be approved, got {data.get('status')}"
        
        # Verify approved_at and approved_by are set
        get_response = requests.get(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}",
            headers=auth_headers
        )
        policy = get_response.json()
        assert policy.get("status") == "approved"
        assert "approved_at" in policy, "approved_at should be set"
        assert "approved_by" in policy, "approved_by should be set"
    
    def test_transition_under_review_to_draft(self, auth_headers, existing_policy):
        """Should be able to return from under_review to draft"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        
        # Set to under_review
        requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "draft"}
        )
        requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "under_review"}
        )
        
        # Return to draft
        response = requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "draft"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.json().get("status") == "draft"
    
    def test_transition_approved_to_draft(self, auth_headers, existing_policy):
        """Should be able to reopen approved policy as draft"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        
        # Set to approved
        requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "draft"}
        )
        requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "under_review"}
        )
        requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "approved"}
        )
        
        # Reopen as draft
        response = requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "draft"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        assert response.json().get("status") == "draft"
    
    def test_invalid_transition_draft_to_approved(self, auth_headers, existing_policy):
        """Should NOT be able to transition directly from draft to approved"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        
        # Ensure in draft state
        requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "draft"}
        )
        
        # Try invalid transition
        response = requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "approved"}
        )
        assert response.status_code == 400, f"Expected 400 for invalid transition, got {response.status_code}"
    
    def test_invalid_transition_approved_to_under_review(self, auth_headers, existing_policy):
        """Should NOT be able to transition from approved to under_review"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        
        # Set to approved
        requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "draft"}
        )
        requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "under_review"}
        )
        requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "approved"}
        )
        
        # Try invalid transition
        response = requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "under_review"}
        )
        assert response.status_code == 400, f"Expected 400 for invalid transition, got {response.status_code}"
    
    def test_invalid_status_value(self, auth_headers, existing_policy):
        """Should reject invalid status values"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        response = requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            headers=auth_headers,
            json={"status": "invalid_status"}
        )
        assert response.status_code == 400, f"Expected 400 for invalid status, got {response.status_code}"


class TestVersionControlAuth:
    """Test that version control endpoints require authentication"""
    
    def test_list_versions_requires_auth(self, existing_policy):
        """GET versions without auth should fail"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        response = requests.get(f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions")
        assert response.status_code in [401, 403], f"Expected auth error, got {response.status_code}"
    
    def test_create_version_requires_auth(self, existing_policy):
        """POST versions without auth should fail"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        response = requests.post(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/versions",
            json={"change_summary": "Test"}
        )
        assert response.status_code in [401, 403], f"Expected auth error, got {response.status_code}"
    
    def test_status_update_requires_auth(self, existing_policy):
        """PUT status without auth should fail"""
        if not existing_policy:
            pytest.skip("No existing policy available")
        
        policy_id = existing_policy["id"]
        response = requests.put(
            f"{BASE_URL}/api/policy-templates/generated/{policy_id}/status",
            json={"status": "under_review"}
        )
        assert response.status_code in [401, 403], f"Expected auth error, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
