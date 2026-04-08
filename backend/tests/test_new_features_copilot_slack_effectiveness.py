"""
Test suite for 3 new features:
1. Compliance Copilot - LLM-powered Q&A chat
2. Slack Integration - Webhook-based notifications
3. Control Effectiveness Score - Auto-calculated with manual override
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "demo-admin@grc.com"
ADMIN_PASSWORD = "DemoAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    assert "token" in data, "No token in login response"
    return data["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


# ============== COMPLIANCE COPILOT TESTS ==============

class TestComplianceCopilot:
    """Tests for Compliance Copilot LLM-powered Q&A feature"""
    
    created_session_id = None
    
    def test_copilot_sessions_list_empty_or_existing(self, auth_headers):
        """GET /api/copilot/sessions - should return list (empty or with sessions)"""
        response = requests.get(f"{BASE_URL}/api/copilot/sessions", headers=auth_headers)
        assert response.status_code == 200, f"Failed to get sessions: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Sessions should be a list"
        print(f"Found {len(data)} existing copilot sessions")
    
    def test_copilot_chat_sends_message_and_gets_response(self, auth_headers):
        """POST /api/copilot/chat - send message and get AI response with session_id"""
        payload = {
            "message": "What is NIST 800-53?",
            "session_id": None  # New session
        }
        response = requests.post(
            f"{BASE_URL}/api/copilot/chat",
            json=payload,
            headers=auth_headers,
            timeout=60  # LLM may take time
        )
        assert response.status_code == 200, f"Chat failed: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "session_id" in data, "Response should have session_id"
        assert "message_id" in data, "Response should have message_id"
        assert "response" in data, "Response should have AI response"
        assert "created_at" in data, "Response should have created_at"
        
        # Validate response content
        assert len(data["session_id"]) > 0, "session_id should not be empty"
        assert len(data["response"]) > 0, "AI response should not be empty"
        
        TestComplianceCopilot.created_session_id = data["session_id"]
        print(f"Created session: {data['session_id']}")
        print(f"AI Response preview: {data['response'][:100]}...")
    
    def test_copilot_chat_empty_message_rejected(self, auth_headers):
        """POST /api/copilot/chat - empty message should return 400"""
        payload = {"message": "   ", "session_id": None}
        response = requests.post(
            f"{BASE_URL}/api/copilot/chat",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 400, f"Empty message should be rejected: {response.text}"
    
    def test_copilot_session_messages_retrieval(self, auth_headers):
        """GET /api/copilot/sessions/{session_id}/messages - returns chat history"""
        if not TestComplianceCopilot.created_session_id:
            pytest.skip("No session created in previous test")
        
        session_id = TestComplianceCopilot.created_session_id
        response = requests.get(
            f"{BASE_URL}/api/copilot/sessions/{session_id}/messages",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed to get messages: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "Messages should be a list"
        assert len(data) >= 2, "Should have at least user message and AI response"
        
        # Verify message structure
        for msg in data:
            assert "role" in msg, "Message should have role"
            assert "content" in msg, "Message should have content"
            assert msg["role"] in ["user", "assistant"], f"Invalid role: {msg['role']}"
        
        print(f"Retrieved {len(data)} messages from session")
    
    def test_copilot_sessions_list_after_chat(self, auth_headers):
        """GET /api/copilot/sessions - should now include the created session"""
        response = requests.get(f"{BASE_URL}/api/copilot/sessions", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        if TestComplianceCopilot.created_session_id:
            session_ids = [s["session_id"] for s in data]
            assert TestComplianceCopilot.created_session_id in session_ids, "Created session should be in list"
    
    def test_copilot_delete_session(self, auth_headers):
        """DELETE /api/copilot/sessions/{session_id} - deletes session"""
        if not TestComplianceCopilot.created_session_id:
            pytest.skip("No session to delete")
        
        session_id = TestComplianceCopilot.created_session_id
        response = requests.delete(
            f"{BASE_URL}/api/copilot/sessions/{session_id}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed to delete session: {response.text}"
        data = response.json()
        assert data.get("status") == "deleted", "Should return deleted status"
        
        # Verify deletion
        response = requests.get(
            f"{BASE_URL}/api/copilot/sessions/{session_id}/messages",
            headers=auth_headers
        )
        assert response.status_code == 200
        assert len(response.json()) == 0, "Messages should be deleted"
        print(f"Session {session_id} deleted successfully")


# ============== SLACK INTEGRATION TESTS ==============

class TestSlackIntegration:
    """Tests for Slack webhook-based notifications"""
    
    def test_slack_config_not_configured(self, auth_headers):
        """GET /api/slack/config - returns {configured: false} when not set up"""
        response = requests.get(f"{BASE_URL}/api/slack/config", headers=auth_headers)
        assert response.status_code == 200, f"Failed to get slack config: {response.text}"
        data = response.json()
        
        # Should have configured field
        assert "configured" in data, "Response should have 'configured' field"
        print(f"Slack configured: {data.get('configured')}")
    
    def test_slack_config_invalid_webhook_rejected(self, auth_headers):
        """POST /api/slack/config - invalid webhook URL should return 400"""
        payload = {
            "webhook_url": "https://invalid-url.com/webhook",
            "channel_name": "#test",
            "notify_risks": True,
            "notify_tasks": True,
            "notify_policies": True,
            "notify_audits": True
        }
        response = requests.post(
            f"{BASE_URL}/api/slack/config",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 400, f"Invalid webhook should be rejected: {response.text}"
        data = response.json()
        assert "hooks.slack.com" in data.get("detail", "").lower(), "Error should mention valid webhook format"
        print(f"Invalid webhook correctly rejected: {data.get('detail')}")
    
    def test_slack_config_valid_webhook_format_validation(self, auth_headers):
        """POST /api/slack/config - validates webhook must start with https://hooks.slack.com/"""
        # Test various invalid formats
        invalid_urls = [
            "http://hooks.slack.com/services/T123/B456/abc",  # http not https
            "https://slack.com/api/webhook",  # wrong domain
            "https://hooks.slack.com",  # missing path
        ]
        
        for url in invalid_urls:
            payload = {"webhook_url": url}
            response = requests.post(
                f"{BASE_URL}/api/slack/config",
                json=payload,
                headers=auth_headers
            )
            # Should reject invalid URLs
            if not url.startswith("https://hooks.slack.com/"):
                assert response.status_code == 400, f"Should reject: {url}"
    
    def test_slack_history_returns_list(self, auth_headers):
        """GET /api/slack/history - returns notification history"""
        response = requests.get(f"{BASE_URL}/api/slack/history", headers=auth_headers)
        assert response.status_code == 200, f"Failed to get slack history: {response.text}"
        data = response.json()
        
        assert isinstance(data, list), "History should be a list"
        print(f"Slack notification history: {len(data)} items")
        
        # If there are items, verify structure
        if len(data) > 0:
            item = data[0]
            assert "event_type" in item or "title" in item, "History item should have event info"


# ============== CONTROL EFFECTIVENESS TESTS ==============

class TestControlEffectiveness:
    """Tests for Control Effectiveness Score feature"""
    
    # Test with NIST 800-53 framework (using actual UUID from database)
    # The framework_id is a UUID, not a slug
    FRAMEWORK_ID = "394b18c4-f22e-4b9a-984b-b5e2ec8143cb"  # NIST SP 800-53
    CONTROL_ID = "AC-1"
    
    def test_effectiveness_score_retrieval(self, auth_headers):
        """GET /api/control-effectiveness/{framework_id}/{control_id} - returns score with factors"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/{self.FRAMEWORK_ID}/{self.CONTROL_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed to get effectiveness: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "framework_id" in data, "Should have framework_id"
        assert "control_id" in data, "Should have control_id"
        assert "auto_score" in data, "Should have auto_score"
        assert "final_score" in data, "Should have final_score"
        assert "grade" in data, "Should have grade"
        assert "factors" in data, "Should have factors breakdown"
        assert "last_updated" in data, "Should have last_updated"
        
        # Validate score range
        assert 0 <= data["auto_score"] <= 100, "auto_score should be 0-100"
        assert 0 <= data["final_score"] <= 100, "final_score should be 0-100"
        
        # Validate grade
        valid_grades = ["Excellent", "Good", "Fair", "Needs Improvement", "Critical"]
        assert data["grade"] in valid_grades, f"Invalid grade: {data['grade']}"
        
        # Validate factors
        factors = data["factors"]
        expected_factors = ["policy_mapping", "evidence_coverage", "cci_completion", "risk_exposure", "recency"]
        for factor in expected_factors:
            assert factor in factors, f"Missing factor: {factor}"
            assert isinstance(factors[factor], int), f"Factor {factor} should be int"
        
        print(f"Control {self.CONTROL_ID} effectiveness: {data['final_score']} ({data['grade']})")
        print(f"Factors: {factors}")
    
    def test_effectiveness_framework_summary(self, auth_headers):
        """GET /api/control-effectiveness/summary/{framework_id} - returns framework-level summary"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/summary/{self.FRAMEWORK_ID}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed to get summary: {response.text}"
        data = response.json()
        
        # Validate response structure
        assert "framework_id" in data, "Should have framework_id"
        assert "average_score" in data, "Should have average_score"
        assert "average_grade" in data, "Should have average_grade"
        assert "total_controls" in data, "Should have total_controls"
        assert "controls" in data, "Should have controls list"
        assert "distribution" in data, "Should have distribution"
        
        # Validate distribution
        dist = data["distribution"]
        assert "excellent" in dist, "Distribution should have excellent"
        assert "good" in dist, "Distribution should have good"
        assert "fair" in dist, "Distribution should have fair"
        assert "needs_improvement" in dist, "Distribution should have needs_improvement"
        assert "critical" in dist, "Distribution should have critical"
        
        print(f"Framework {self.FRAMEWORK_ID} average: {data['average_score']} ({data['average_grade']})")
        print(f"Total controls: {data['total_controls']}")
        print(f"Distribution: {dist}")
    
    def test_effectiveness_override_invalid_score_rejected(self, auth_headers):
        """PUT /api/control-effectiveness/{framework_id}/{control_id}/override - rejects invalid score"""
        # Test score > 100
        payload = {"score": 150, "reason": "Test override"}
        response = requests.put(
            f"{BASE_URL}/api/control-effectiveness/{self.FRAMEWORK_ID}/{self.CONTROL_ID}/override",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 400, f"Score > 100 should be rejected: {response.text}"
        
        # Test score < 0
        payload = {"score": -10, "reason": "Test override"}
        response = requests.put(
            f"{BASE_URL}/api/control-effectiveness/{self.FRAMEWORK_ID}/{self.CONTROL_ID}/override",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 400, f"Score < 0 should be rejected: {response.text}"
    
    def test_effectiveness_override_and_clear(self, auth_headers):
        """PUT and DELETE /api/control-effectiveness/{framework_id}/{control_id}/override"""
        # First get current score
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/{self.FRAMEWORK_ID}/{self.CONTROL_ID}",
            headers=auth_headers
        )
        original_data = response.json()
        original_auto_score = original_data["auto_score"]
        
        # Set override
        override_score = 85
        override_reason = "Manual assessment completed - compensating controls verified"
        payload = {"score": override_score, "reason": override_reason}
        
        response = requests.put(
            f"{BASE_URL}/api/control-effectiveness/{self.FRAMEWORK_ID}/{self.CONTROL_ID}/override",
            json=payload,
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed to set override: {response.text}"
        data = response.json()
        assert data.get("status") == "saved", "Should return saved status"
        assert data.get("score") == override_score, "Should return the override score"
        print(f"Override set: {override_score}")
        
        # Verify override is applied
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/{self.FRAMEWORK_ID}/{self.CONTROL_ID}",
            headers=auth_headers
        )
        data = response.json()
        assert data["manual_override"] == override_score, "manual_override should be set"
        assert data["override_reason"] == override_reason, "override_reason should be set"
        assert data["final_score"] == override_score, "final_score should use override"
        print(f"Override verified: final_score={data['final_score']}, auto_score={data['auto_score']}")
        
        # Clear override
        response = requests.delete(
            f"{BASE_URL}/api/control-effectiveness/{self.FRAMEWORK_ID}/{self.CONTROL_ID}/override",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed to clear override: {response.text}"
        data = response.json()
        assert data.get("status") == "cleared", "Should return cleared status"
        
        # Verify override is cleared
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/{self.FRAMEWORK_ID}/{self.CONTROL_ID}",
            headers=auth_headers
        )
        data = response.json()
        assert data["manual_override"] is None, "manual_override should be None after clear"
        assert data["final_score"] == data["auto_score"], "final_score should revert to auto_score"
        print(f"Override cleared: final_score reverted to {data['final_score']}")


# ============== AUTHENTICATION TESTS ==============

class TestAuthentication:
    """Basic auth tests to ensure endpoints require authentication"""
    
    def test_copilot_requires_auth(self):
        """Copilot endpoints should require authentication"""
        response = requests.get(f"{BASE_URL}/api/copilot/sessions")
        assert response.status_code in [401, 403], "Should require auth"
    
    def test_slack_requires_auth(self):
        """Slack endpoints should require authentication"""
        response = requests.get(f"{BASE_URL}/api/slack/config")
        assert response.status_code in [401, 403], "Should require auth"
    
    def test_effectiveness_requires_auth(self):
        """Effectiveness endpoints should require authentication"""
        response = requests.get(f"{BASE_URL}/api/control-effectiveness/nist-800-53/AC-1")
        assert response.status_code in [401, 403], "Should require auth"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
