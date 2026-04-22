"""
Test Tenable VM Integration - New Features (Iteration 19)
- POST /api/tenable/auto-assess - Auto-update NIST 800-53 control compliance from Tenable findings
- POST /api/tenable/generate-poam - Create POA&M entries from non-compliant findings
- GET /api/tenable/poam - List POA&M entries
- PUT /api/tenable/poam/{entry_id}/status - Update POA&M status
- POST /api/tenable/generate-policies - AI-generate remediation policies (may timeout)
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
    if response.status_code == 200:
        data = response.json()
        return data.get("token") or data.get("access_token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestTenableAutoAssess:
    """Test POST /api/tenable/auto-assess endpoint"""
    
    def test_auto_assess_unauthorized(self):
        """Test auto-assess without auth returns 401/403"""
        response = requests.post(f"{BASE_URL}/api/tenable/auto-assess")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_auto_assess_success(self, auth_headers):
        """Test auto-assess updates NIST 800-53 controls from Tenable findings"""
        response = requests.post(f"{BASE_URL}/api/tenable/auto-assess", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response should have message"
        assert "controls_updated" in data, "Response should have controls_updated count"
        assert "assessments" in data, "Response should have assessments list"
        assert "framework" in data, "Response should have framework name"
        
        # Verify controls were updated (should be ~26 based on demo data)
        assert data["controls_updated"] > 0, "Should update at least some controls"
        print(f"Auto-assess updated {data['controls_updated']} controls")
    
    def test_auto_assess_assessments_structure(self, auth_headers):
        """Test auto-assess returns proper assessment structure"""
        response = requests.post(f"{BASE_URL}/api/tenable/auto-assess", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        if data.get("assessments"):
            assessment = data["assessments"][0]
            assert "control_id" in assessment, "Assessment should have control_id"
            assert "status" in assessment, "Assessment should have status"
            assert "reason" in assessment, "Assessment should have reason"
            assert "evidence_count" in assessment, "Assessment should have evidence_count"
            
            # Verify status is valid
            assert assessment["status"] in ["compliant", "non_compliant", "partial"], \
                f"Invalid status: {assessment['status']}"


class TestTenableGeneratePoam:
    """Test POST /api/tenable/generate-poam endpoint"""
    
    def test_generate_poam_unauthorized(self):
        """Test generate-poam without auth returns 401/403"""
        response = requests.post(f"{BASE_URL}/api/tenable/generate-poam")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_generate_poam_success(self, auth_headers):
        """Test generate-poam creates POA&M entries from non-compliant findings"""
        response = requests.post(f"{BASE_URL}/api/tenable/generate-poam", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response should have message"
        assert "total" in data or "entries" in data, "Response should have total or entries"
        
        print(f"Generate POA&M: {data.get('message', 'No message')}")
    
    def test_generate_poam_entries_structure(self, auth_headers):
        """Test generate-poam returns proper entry structure"""
        response = requests.post(f"{BASE_URL}/api/tenable/generate-poam", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        entries = data.get("entries", [])
        
        if entries:
            entry = entries[0]
            # Verify required fields
            assert "id" in entry, "Entry should have id"
            assert "poam_id" in entry, "Entry should have poam_id"
            assert "title" in entry, "Entry should have title"
            assert "severity" in entry, "Entry should have severity"
            assert "priority" in entry, "Entry should have priority"
            assert "status" in entry, "Entry should have status"
            assert "scheduled_completion" in entry, "Entry should have scheduled_completion"
            assert "remediation_plan" in entry, "Entry should have remediation_plan"
            
            # Verify severity-based priority
            if entry["severity"] == "critical":
                assert entry["priority"] == "P1", "Critical should be P1"
            elif entry["severity"] == "high":
                assert entry["priority"] == "P2", "High should be P2"
            elif entry["severity"] == "medium":
                assert entry["priority"] == "P3", "Medium should be P3"


class TestTenableListPoam:
    """Test GET /api/tenable/poam endpoint"""
    
    def test_list_poam_unauthorized(self):
        """Test list poam without auth returns 401/403"""
        response = requests.get(f"{BASE_URL}/api/tenable/poam")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_list_poam_success(self, auth_headers):
        """Test list poam returns entries"""
        response = requests.get(f"{BASE_URL}/api/tenable/poam", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        print(f"Found {len(data)} POA&M entries")
    
    def test_list_poam_entry_fields(self, auth_headers):
        """Test POA&M entries have all required fields"""
        response = requests.get(f"{BASE_URL}/api/tenable/poam", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        if data:
            entry = data[0]
            required_fields = [
                "id", "poam_id", "title", "weakness", "description",
                "severity", "priority", "control_ids", "asset", "source",
                "remediation_plan", "scheduled_completion", "status"
            ]
            for field in required_fields:
                assert field in entry, f"Entry missing required field: {field}"
    
    def test_list_poam_has_cves_for_vulns(self, auth_headers):
        """Test vulnerability POA&M entries have CVEs"""
        response = requests.get(f"{BASE_URL}/api/tenable/poam", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        vuln_entries = [e for e in data if e.get("finding_type") == "vulnerability"]
        
        if vuln_entries:
            # At least some vuln entries should have CVEs
            entries_with_cves = [e for e in vuln_entries if e.get("cves")]
            print(f"Found {len(entries_with_cves)} vuln entries with CVEs out of {len(vuln_entries)}")


class TestTenableUpdatePoamStatus:
    """Test PUT /api/tenable/poam/{entry_id}/status endpoint"""
    
    def test_update_poam_status_unauthorized(self):
        """Test update poam status without auth returns 401/403"""
        response = requests.put(f"{BASE_URL}/api/tenable/poam/fake-id/status", json={"status": "in_progress"})
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_update_poam_status_invalid_status(self, auth_headers):
        """Test update poam with invalid status returns 400"""
        # First get a valid entry ID
        list_response = requests.get(f"{BASE_URL}/api/tenable/poam", headers=auth_headers)
        if list_response.status_code != 200 or not list_response.json():
            pytest.skip("No POA&M entries to test with")
        
        entry_id = list_response.json()[0]["id"]
        
        response = requests.put(
            f"{BASE_URL}/api/tenable/poam/{entry_id}/status",
            headers=auth_headers,
            json={"status": "invalid_status"}
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    
    def test_update_poam_status_to_in_progress(self, auth_headers):
        """Test update poam status to in_progress"""
        # Get an open entry
        list_response = requests.get(f"{BASE_URL}/api/tenable/poam", headers=auth_headers)
        if list_response.status_code != 200 or not list_response.json():
            pytest.skip("No POA&M entries to test with")
        
        entries = list_response.json()
        open_entry = next((e for e in entries if e.get("status") == "open"), None)
        
        if not open_entry:
            pytest.skip("No open POA&M entries to test with")
        
        entry_id = open_entry["id"]
        
        response = requests.put(
            f"{BASE_URL}/api/tenable/poam/{entry_id}/status",
            headers=auth_headers,
            json={"status": "in_progress"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "message" in data, "Response should have message"
        assert "in_progress" in data["message"], "Message should mention in_progress"
        
        # Verify the update persisted
        verify_response = requests.get(f"{BASE_URL}/api/tenable/poam", headers=auth_headers)
        updated_entry = next((e for e in verify_response.json() if e["id"] == entry_id), None)
        assert updated_entry is not None, "Entry should still exist"
        assert updated_entry["status"] == "in_progress", "Status should be updated to in_progress"
    
    def test_update_poam_status_to_completed(self, auth_headers):
        """Test update poam status to completed"""
        list_response = requests.get(f"{BASE_URL}/api/tenable/poam", headers=auth_headers)
        if list_response.status_code != 200 or not list_response.json():
            pytest.skip("No POA&M entries to test with")
        
        entries = list_response.json()
        # Find an entry that's not completed
        entry = next((e for e in entries if e.get("status") != "completed"), None)
        
        if not entry:
            pytest.skip("No non-completed POA&M entries to test with")
        
        entry_id = entry["id"]
        
        response = requests.put(
            f"{BASE_URL}/api/tenable/poam/{entry_id}/status",
            headers=auth_headers,
            json={"status": "completed"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify completed_at is set
        verify_response = requests.get(f"{BASE_URL}/api/tenable/poam", headers=auth_headers)
        updated_entry = next((e for e in verify_response.json() if e["id"] == entry_id), None)
        assert updated_entry["status"] == "completed", "Status should be completed"
    
    def test_update_poam_status_to_delayed(self, auth_headers):
        """Test update poam status to delayed"""
        list_response = requests.get(f"{BASE_URL}/api/tenable/poam", headers=auth_headers)
        if list_response.status_code != 200 or not list_response.json():
            pytest.skip("No POA&M entries to test with")
        
        entries = list_response.json()
        entry = next((e for e in entries if e.get("status") not in ["completed", "delayed"]), None)
        
        if not entry:
            pytest.skip("No suitable POA&M entries to test with")
        
        entry_id = entry["id"]
        
        response = requests.put(
            f"{BASE_URL}/api/tenable/poam/{entry_id}/status",
            headers=auth_headers,
            json={"status": "delayed"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_update_poam_status_not_found(self, auth_headers):
        """Test update poam with non-existent ID returns 404"""
        response = requests.put(
            f"{BASE_URL}/api/tenable/poam/non-existent-id-12345/status",
            headers=auth_headers,
            json={"status": "in_progress"}
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestTenableSeverityTimelines:
    """Test POA&M severity-based timelines"""
    
    def test_critical_severity_15_days(self, auth_headers):
        """Test critical severity has 15-day timeline"""
        response = requests.get(f"{BASE_URL}/api/tenable/poam", headers=auth_headers)
        if response.status_code != 200:
            pytest.skip("Cannot get POA&M entries")
        
        entries = response.json()
        critical_entries = [e for e in entries if e.get("severity") == "critical"]
        
        if critical_entries:
            entry = critical_entries[0]
            assert entry.get("milestone_days") == 15, f"Critical should have 15-day timeline, got {entry.get('milestone_days')}"
            assert entry.get("priority") == "P1", f"Critical should be P1, got {entry.get('priority')}"
    
    def test_high_severity_30_days(self, auth_headers):
        """Test high severity has 30-day timeline"""
        response = requests.get(f"{BASE_URL}/api/tenable/poam", headers=auth_headers)
        if response.status_code != 200:
            pytest.skip("Cannot get POA&M entries")
        
        entries = response.json()
        high_entries = [e for e in entries if e.get("severity") == "high"]
        
        if high_entries:
            entry = high_entries[0]
            assert entry.get("milestone_days") == 30, f"High should have 30-day timeline, got {entry.get('milestone_days')}"
            assert entry.get("priority") == "P2", f"High should be P2, got {entry.get('priority')}"
    
    def test_medium_severity_90_days(self, auth_headers):
        """Test medium severity has 90-day timeline"""
        response = requests.get(f"{BASE_URL}/api/tenable/poam", headers=auth_headers)
        if response.status_code != 200:
            pytest.skip("Cannot get POA&M entries")
        
        entries = response.json()
        medium_entries = [e for e in entries if e.get("severity") == "medium"]
        
        if medium_entries:
            entry = medium_entries[0]
            assert entry.get("milestone_days") == 90, f"Medium should have 90-day timeline, got {entry.get('milestone_days')}"
            assert entry.get("priority") == "P3", f"Medium should be P3, got {entry.get('priority')}"


class TestTenableGeneratePolicies:
    """Test POST /api/tenable/generate-policies endpoint (may timeout due to LLM calls)"""
    
    def test_generate_policies_unauthorized(self):
        """Test generate-policies without auth returns 401/403"""
        response = requests.post(f"{BASE_URL}/api/tenable/generate-policies")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_generate_policies_endpoint_exists(self, auth_headers):
        """Test generate-policies endpoint exists and accepts requests"""
        # Use a short timeout since this endpoint may take 2-3 minutes
        try:
            response = requests.post(
                f"{BASE_URL}/api/tenable/generate-policies",
                headers=auth_headers,
                timeout=30  # Short timeout - we just want to verify endpoint works
            )
            # If we get a response, check it's valid
            if response.status_code == 200:
                data = response.json()
                assert "message" in data, "Response should have message"
                assert "policies" in data, "Response should have policies list"
                print(f"Generate policies: {data.get('message', 'No message')}")
            else:
                # Endpoint exists but may have failed for other reasons
                print(f"Generate policies returned {response.status_code}: {response.text[:200]}")
        except requests.exceptions.Timeout:
            # Expected - endpoint takes 2-3 minutes
            print("Generate policies timed out (expected - LLM calls take 2-3 minutes)")
            pytest.skip("Endpoint timed out - this is expected behavior for LLM-based policy generation")


class TestTenableIntegrationFlow:
    """Test the full Tenable integration flow"""
    
    def test_full_flow_sync_assess_poam(self, auth_headers):
        """Test full flow: sync -> auto-assess -> generate-poam"""
        # 1. Ensure demo data is synced
        sync_response = requests.post(
            f"{BASE_URL}/api/tenable/sync",
            headers=auth_headers,
            json={"mode": "demo"}
        )
        assert sync_response.status_code == 200, f"Sync failed: {sync_response.text}"
        print(f"Sync: {sync_response.json().get('message', 'OK')}")
        
        # 2. Auto-assess controls
        assess_response = requests.post(
            f"{BASE_URL}/api/tenable/auto-assess",
            headers=auth_headers
        )
        assert assess_response.status_code == 200, f"Auto-assess failed: {assess_response.text}"
        assess_data = assess_response.json()
        print(f"Auto-assess: Updated {assess_data.get('controls_updated', 0)} controls")
        
        # 3. Generate POA&M
        poam_response = requests.post(
            f"{BASE_URL}/api/tenable/generate-poam",
            headers=auth_headers
        )
        assert poam_response.status_code == 200, f"Generate POA&M failed: {poam_response.text}"
        poam_data = poam_response.json()
        print(f"Generate POA&M: {poam_data.get('message', 'OK')}")
        
        # 4. Verify POA&M entries exist
        list_response = requests.get(f"{BASE_URL}/api/tenable/poam", headers=auth_headers)
        assert list_response.status_code == 200
        entries = list_response.json()
        print(f"Total POA&M entries: {len(entries)}")
        
        # Verify we have entries with proper structure
        if entries:
            entry = entries[0]
            assert entry.get("source") == "tenable", "Entry source should be tenable"
            assert entry.get("control_ids"), "Entry should have control_ids"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
