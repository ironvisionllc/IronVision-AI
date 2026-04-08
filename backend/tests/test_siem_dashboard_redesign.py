"""
Test suite for SIEM Integration and Dashboard Redesign features.
Tests SIEM endpoints: events, dashboard, control-mapping, export
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSIEMIntegration:
    """SIEM Integration endpoint tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup auth token for all tests"""
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo-admin@grc.com", "password": "DemoAdmin123!"}
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        self.token = login_response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_siem_dashboard_returns_200(self):
        """GET /api/siem/dashboard returns 200 with required fields"""
        response = requests.get(
            f"{BASE_URL}/api/siem/dashboard?days=7",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify required fields
        assert "threat_level" in data
        assert "total_events" in data
        assert "severity_distribution" in data
        assert "category_distribution" in data
        assert "critical_events" in data
        
        # Verify threat_level is 0-100
        assert 0 <= data["threat_level"] <= 100
        
        # Verify severity_distribution has all severities
        for sev in ["critical", "high", "medium", "low", "info"]:
            assert sev in data["severity_distribution"]
    
    def test_siem_dashboard_has_category_distribution(self):
        """Dashboard returns 7 category distributions"""
        response = requests.get(
            f"{BASE_URL}/api/siem/dashboard?days=7",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        expected_categories = ["authentication", "authorization", "data_access", 
                              "policy_change", "risk_management", "incident", "system"]
        for cat in expected_categories:
            assert cat in data["category_distribution"], f"Missing category: {cat}"
    
    def test_siem_events_returns_array(self):
        """GET /api/siem/events returns array of events"""
        response = requests.get(
            f"{BASE_URL}/api/siem/events?days=7&limit=10",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        if len(data) > 0:
            event = data[0]
            # Verify event structure
            assert "id" in event
            assert "event_type" in event
            assert "category" in event
            assert "severity" in event
            assert "details" in event
            assert "mapped_controls" in event
            assert "mapped_frameworks" in event
    
    def test_siem_events_have_control_mappings(self):
        """Events have mapped_controls and mapped_frameworks"""
        response = requests.get(
            f"{BASE_URL}/api/siem/events?days=7&limit=5",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        if len(data) > 0:
            event = data[0]
            assert isinstance(event["mapped_controls"], list)
            assert isinstance(event["mapped_frameworks"], list)
            # Should have at least one control mapped
            assert len(event["mapped_controls"]) > 0
    
    def test_siem_control_mapping_returns_7_categories(self):
        """GET /api/siem/control-mapping returns 7 category mappings"""
        response = requests.get(
            f"{BASE_URL}/api/siem/control-mapping",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) == 7, f"Expected 7 categories, got {len(data)}"
        
        # Verify each mapping has required fields
        for mapping in data:
            assert "category" in mapping
            assert "description" in mapping
            assert "controls" in mapping
            assert "frameworks" in mapping
            assert "event_count_30d" in mapping
            assert isinstance(mapping["controls"], list)
            assert isinstance(mapping["frameworks"], list)
    
    def test_siem_control_mapping_has_nist_controls(self):
        """Control mappings include NIST 800-53 and 800-171 controls"""
        response = requests.get(
            f"{BASE_URL}/api/siem/control-mapping",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Find authentication category
        auth_mapping = next((m for m in data if m["category"] == "authentication"), None)
        assert auth_mapping is not None
        
        # Should have AC-2, IA-2 controls
        assert "AC-2" in auth_mapping["controls"]
        assert "IA-2" in auth_mapping["controls"]
        
        # Should have NIST frameworks
        assert "nist-800-53" in auth_mapping["frameworks"]
    
    def test_siem_export_json_format(self):
        """GET /api/siem/export?format=json returns events"""
        response = requests.get(
            f"{BASE_URL}/api/siem/export?format=json&days=7",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "events" in data
        assert "count" in data
        assert "period_days" in data
        assert isinstance(data["events"], list)
    
    def test_siem_dashboard_critical_events_list(self):
        """Dashboard returns critical_events array"""
        response = requests.get(
            f"{BASE_URL}/api/siem/dashboard?days=7",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "critical_events" in data
        assert isinstance(data["critical_events"], list)
        
        # If there are critical events, verify structure
        if len(data["critical_events"]) > 0:
            event = data["critical_events"][0]
            assert event["severity"] in ["critical", "high"]
    
    def test_siem_events_filter_by_severity(self):
        """Events can be filtered by severity"""
        response = requests.get(
            f"{BASE_URL}/api/siem/events?days=7&severity=high&limit=10",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # All returned events should be high severity
        for event in data:
            assert event["severity"] == "high"
    
    def test_siem_events_filter_by_category(self):
        """Events can be filtered by category"""
        response = requests.get(
            f"{BASE_URL}/api/siem/events?days=7&category=authentication&limit=10",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # All returned events should be authentication category
        for event in data:
            assert event["category"] == "authentication"
    
    def test_siem_requires_auth(self):
        """SIEM endpoints require authentication"""
        response = requests.get(f"{BASE_URL}/api/siem/dashboard")
        assert response.status_code in [401, 403]
        
        response = requests.get(f"{BASE_URL}/api/siem/events")
        assert response.status_code in [401, 403]
        
        response = requests.get(f"{BASE_URL}/api/siem/control-mapping")
        assert response.status_code in [401, 403]


class TestDashboardAPIs:
    """Dashboard API tests for redesigned dashboard"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup auth token for all tests"""
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "demo-admin@grc.com", "password": "DemoAdmin123!"}
        )
        assert login_response.status_code == 200
        self.token = login_response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_analytics_dashboard_returns_200(self):
        """GET /api/analytics/dashboard returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/dashboard",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify key fields for dashboard
        assert "risk_heatmap" in data or "overdue_tasks" in data or "upcoming_deadlines" in data
    
    def test_executive_summary_returns_200(self):
        """GET /api/reports/executive-summary returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/reports/executive-summary",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify key fields
        assert "overall_compliance_score" in data
        assert "overall_grade" in data
        assert "framework_scores" in data
    
    def test_compliance_trends_returns_200(self):
        """GET /api/compliance-trends returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/compliance-trends",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
    
    def test_control_effectiveness_dashboard_returns_200(self):
        """GET /api/control-effectiveness/dashboard returns 200"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/dashboard",
            headers=self.headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "overall_score" in data
        assert "overall_grade" in data
        assert "total_frameworks" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
