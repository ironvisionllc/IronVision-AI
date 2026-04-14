"""
Test suite for Control Compliance API endpoints (Phase A - IronVision GRC)
Tests: GET overview, PUT status, PUT notes, GET siem-evidence, POST ai-assess, POST suggest-policy
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://compliance-ingestion.preview.emergentagent.com')

# Test credentials
TEST_EMAIL = "demo-admin@grc.com"
TEST_PASSWORD = "DemoAdmin123!"

# NIST SP 800-53 framework ID
NIST_800_53_FW_ID = "394b18c4-f22e-4b9a-984b-b5e2ec8143cb"


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


class TestControlComplianceOverview:
    """Tests for GET /api/control-compliance/{framework_id}"""
    
    def test_get_compliance_overview_success(self, api_client):
        """Test fetching compliance overview for a framework"""
        response = api_client.get(f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert "framework_id" in data
        assert data["framework_id"] == NIST_800_53_FW_ID
        assert "controls" in data
        assert "summary" in data
        assert "total" in data
        assert data["total"] > 0
        
        # Verify summary structure
        summary = data["summary"]
        assert "compliant" in summary
        assert "partial" in summary
        assert "non_compliant" in summary
        assert "not_assessed" in summary
        
    def test_compliance_overview_control_structure(self, api_client):
        """Test that controls have required fields"""
        response = api_client.get(f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["controls"]) > 0
        
        ctrl = data["controls"][0]
        required_fields = [
            "control_id", "title", "description", "category", "status",
            "is_user_override", "notes", "ai_assessment", "policy_suggestion",
            "is_technical", "siem_categories", "siem_events_count",
            "policy_mappings", "policy_count"
        ]
        for field in required_fields:
            assert field in ctrl, f"Missing field: {field}"
            
    def test_compliance_overview_technical_controls(self, api_client):
        """Test that technical controls have SIEM mappings"""
        response = api_client.get(f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}")
        assert response.status_code == 200
        
        data = response.json()
        # Find a technical control (AC-2 should be technical)
        ac2 = next((c for c in data["controls"] if c["control_id"] == "AC-2"), None)
        assert ac2 is not None
        assert ac2["is_technical"] == True
        assert len(ac2["siem_categories"]) > 0
        assert "authentication" in ac2["siem_categories"]


class TestControlComplianceStatus:
    """Tests for PUT /api/control-compliance/{framework_id}/{control_id}/status"""
    
    def test_update_status_compliant(self, api_client):
        """Test updating control status to compliant"""
        response = api_client.put(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/AC-3/status",
            json={"status": "compliant", "reason": "Test - marking compliant"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "compliant"
        assert data["message"] == "Status updated"
        
    def test_update_status_partial(self, api_client):
        """Test updating control status to partial"""
        response = api_client.put(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/AC-4/status",
            json={"status": "partial"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "partial"
        
    def test_update_status_non_compliant(self, api_client):
        """Test updating control status to non_compliant"""
        response = api_client.put(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/AC-5/status",
            json={"status": "non_compliant", "reason": "Missing implementation"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "non_compliant"
        
    def test_update_status_invalid(self, api_client):
        """Test updating with invalid status returns 400"""
        response = api_client.put(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/AC-6/status",
            json={"status": "invalid_status"}
        )
        assert response.status_code == 400
        
    def test_status_persists(self, api_client):
        """Test that status update persists and is_user_override is set"""
        # Update status
        api_client.put(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/AC-7/status",
            json={"status": "compliant"}
        )
        
        # Verify persistence
        response = api_client.get(f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}")
        assert response.status_code == 200
        
        data = response.json()
        ac7 = next((c for c in data["controls"] if c["control_id"] == "AC-7"), None)
        assert ac7 is not None
        assert ac7["status"] == "compliant"
        assert ac7["is_user_override"] == True


class TestControlComplianceNotes:
    """Tests for PUT /api/control-compliance/{framework_id}/{control_id}/notes"""
    
    def test_save_notes(self, api_client):
        """Test saving notes for a control"""
        test_notes = "Test notes for IA-2 control - implementation details"
        response = api_client.put(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/IA-2/notes",
            json={"notes": test_notes}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Notes saved"
        
    def test_notes_persist(self, api_client):
        """Test that notes persist after saving"""
        test_notes = "Persistent notes test for IA-5"
        
        # Save notes
        api_client.put(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/IA-5/notes",
            json={"notes": test_notes}
        )
        
        # Verify persistence
        response = api_client.get(f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}")
        assert response.status_code == 200
        
        data = response.json()
        ia5 = next((c for c in data["controls"] if c["control_id"] == "IA-5"), None)
        assert ia5 is not None
        assert ia5["notes"] == test_notes


class TestSIEMEvidence:
    """Tests for GET /api/control-compliance/{framework_id}/{control_id}/siem-evidence"""
    
    def test_get_siem_evidence_technical_control(self, api_client):
        """Test getting SIEM evidence for a technical control"""
        response = api_client.get(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/AC-2/siem-evidence"
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "events" in data
        assert "categories" in data
        assert "count" in data
        assert "authentication" in data["categories"]
        
    def test_get_siem_evidence_non_technical_control(self, api_client):
        """Test getting SIEM evidence for a non-technical control"""
        response = api_client.get(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/AC-1/siem-evidence"
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["events"] == []
        assert data["categories"] == []
        assert "message" in data
        
    def test_siem_evidence_event_structure(self, api_client):
        """Test SIEM event structure"""
        response = api_client.get(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/AC-2/siem-evidence"
        )
        assert response.status_code == 200
        
        data = response.json()
        if len(data["events"]) > 0:
            event = data["events"][0]
            assert "event_type" in event
            assert "category" in event
            assert "severity" in event
            assert "timestamp" in event


class TestAIAssessment:
    """Tests for POST /api/control-compliance/{framework_id}/ai-assess"""
    
    def test_ai_bulk_assess(self, api_client):
        """Test AI bulk assessment endpoint (may take time due to LLM call)"""
        response = api_client.post(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/ai-assess",
            json={},
            timeout=60  # LLM calls can take time
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "assessed" in data
        assert "results" in data
        assert data["assessed"] > 0
        
    def test_ai_assess_result_structure(self, api_client):
        """Test AI assessment result structure"""
        response = api_client.post(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/ai-assess",
            json={},
            timeout=60
        )
        assert response.status_code == 200
        
        data = response.json()
        if len(data["results"]) > 0:
            result = data["results"][0]
            assert "control_id" in result
            assert "status" in result
            # Status should be valid
            assert result["status"] in ["compliant", "partial", "non_compliant", "not_assessed"] or result.get("skipped")


class TestPolicySuggestion:
    """Tests for POST /api/control-compliance/{framework_id}/{control_id}/suggest-policy"""
    
    def test_suggest_policy(self, api_client):
        """Test AI policy suggestion endpoint"""
        response = api_client.post(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/AC-1/suggest-policy",
            json={},
            timeout=60
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "title" in data
        assert "statements" in data
        assert isinstance(data["statements"], list)
        
    def test_suggest_policy_for_nonexistent_control(self, api_client):
        """Test policy suggestion for non-existent control returns 404"""
        response = api_client.post(
            f"{BASE_URL}/api/control-compliance/{NIST_800_53_FW_ID}/INVALID-CTRL/suggest-policy",
            json={},
            timeout=30
        )
        assert response.status_code == 404


class TestPolicyHubTabs:
    """Tests for Policy Hub tab navigation (Mappings and Cross-Framework moved here)"""
    
    def test_mappings_endpoint(self, api_client):
        """Test that mappings endpoint still works"""
        response = api_client.get(f"{BASE_URL}/api/mappings")
        assert response.status_code == 200
        
    def test_frameworks_endpoint(self, api_client):
        """Test frameworks endpoint for cross-framework data"""
        response = api_client.get(f"{BASE_URL}/api/frameworks")
        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
