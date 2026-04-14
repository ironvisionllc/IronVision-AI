"""
Iteration 12 Tests: IronVision AI Branding + Atlas Integration
Tests the IronVision rebrand and Atlas connectivity for the GRC app.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://compliance-ingestion.preview.emergentagent.com')

# Test credentials
DEMO_ADMIN = {"email": "demo-admin@grc.com", "password": "DemoAdmin123!"}
DEMO_USER = {"email": "demo-user@grc.com", "password": "DemoUser123!"}


class TestAuthentication:
    """Test demo account authentication"""
    
    def test_demo_admin_login(self):
        """Demo Admin login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_ADMIN)
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["email"] == "demo-admin@grc.com"
        assert data["user"]["is_demo"] == True
        print("PASSED: Demo Admin login successful")
    
    def test_demo_user_login(self):
        """Demo User login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_USER)
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert data["user"]["email"] == "demo-user@grc.com"
        assert data["user"]["is_demo"] == True
        print("PASSED: Demo User login successful")


class TestIronVisionAtlas:
    """Test IronVision Atlas integration endpoints"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_ADMIN)
        return response.json()["token"]
    
    def test_ironvision_dashboard_stats(self, admin_token):
        """IronVision Atlas dashboard-stats endpoint returns data"""
        response = requests.get(
            f"{BASE_URL}/api/ironvision/dashboard-stats",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "stats" in data
        assert "recentDocuments" in data
        assert "totalPolicies" in data["stats"]
        assert "totalReports" in data["stats"]
        assert "activeAnalyses" in data["stats"]
        assert "drafts" in data["stats"]
        print(f"PASSED: IronVision dashboard-stats returns: {data['stats']}")


class TestExistingGRCAPIs:
    """Test all existing GRC APIs still work after rebrand"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_ADMIN)
        return response.json()["token"]
    
    def test_frameworks_api(self, admin_token):
        """GET /api/frameworks returns frameworks"""
        response = requests.get(
            f"{BASE_URL}/api/frameworks",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 10  # Should have 10+ frameworks
        print(f"PASSED: Frameworks API returns {len(data)} frameworks")
    
    def test_risks_api(self, admin_token):
        """GET /api/risks returns risks"""
        response = requests.get(
            f"{BASE_URL}/api/risks",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 7  # Should have 7 demo risks
        # Check for open risks (should have Create Remediation Task button)
        open_risks = [r for r in data if r["status"] == "open"]
        assert len(open_risks) >= 5
        print(f"PASSED: Risks API returns {len(data)} risks ({len(open_risks)} open)")
    
    def test_tasks_api(self, admin_token):
        """GET /api/tasks returns tasks"""
        response = requests.get(
            f"{BASE_URL}/api/tasks",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 6  # Should have 6 demo tasks
        print(f"PASSED: Tasks API returns {len(data)} tasks")
    
    def test_vendors_api(self, admin_token):
        """GET /api/vendors returns vendors"""
        response = requests.get(
            f"{BASE_URL}/api/vendors",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 4  # Should have 4 demo vendors
        print(f"PASSED: Vendors API returns {len(data)} vendors")
    
    def test_audits_api(self, admin_token):
        """GET /api/audits returns audits"""
        response = requests.get(
            f"{BASE_URL}/api/audits",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 2  # Should have 2 demo audits
        print(f"PASSED: Audits API returns {len(data)} audits")
    
    def test_policies_api(self, admin_token):
        """GET /api/policies returns policies"""
        response = requests.get(
            f"{BASE_URL}/api/policies",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 6  # Should have 6 demo policies
        print(f"PASSED: Policies API returns {len(data)} policies")
    
    def test_evidence_api(self, admin_token):
        """GET /api/evidence returns evidence"""
        response = requests.get(
            f"{BASE_URL}/api/evidence",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 5  # Should have 5 demo evidence items
        print(f"PASSED: Evidence API returns {len(data)} evidence items")
    
    def test_activity_api(self, admin_token):
        """GET /api/activity returns activity log"""
        response = requests.get(
            f"{BASE_URL}/api/activity",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 6  # Should have 6+ activity items
        # Check for various action types
        actions = set(a["action"] for a in data)
        assert "task_updated" in actions or "task_created" in actions
        print(f"PASSED: Activity API returns {len(data)} items with actions: {actions}")
    
    def test_notifications_api(self, admin_token):
        """GET /api/notifications returns notifications"""
        response = requests.get(
            f"{BASE_URL}/api/notifications",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 5  # Should have 5 demo notifications
        print(f"PASSED: Notifications API returns {len(data)} notifications")


class TestDashboardAnalytics:
    """Test dashboard analytics endpoints"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_ADMIN)
        return response.json()["token"]
    
    def test_analytics_dashboard(self, admin_token):
        """GET /api/analytics/dashboard returns all sections"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/dashboard",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check all required sections
        assert "policies_count" in data
        assert "mappings_count" in data
        assert "open_risks_count" in data
        assert "audits_count" in data
        assert "risk_distribution" in data
        assert "risk_heatmap" in data
        assert "recent_activity" in data
        assert "upcoming_deadlines" in data
        
        # Verify risk heatmap is 5x5
        assert len(data["risk_heatmap"]) == 5
        for row in data["risk_heatmap"]:
            assert len(row) == 5
        
        print(f"PASSED: Dashboard analytics returns all sections")
        print(f"  - Policies: {data['policies_count']}")
        print(f"  - Mappings: {data['mappings_count']}")
        print(f"  - Open Risks: {data['open_risks_count']}")
        print(f"  - Audits: {data['audits_count']}")
    
    def test_executive_summary(self, admin_token):
        """GET /api/reports/executive-summary returns compliance data"""
        response = requests.get(
            f"{BASE_URL}/api/reports/executive-summary",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "overall_compliance_score" in data
        assert "overall_grade" in data
        assert "framework_scores" in data
        
        print(f"PASSED: Executive summary returns score: {data['overall_compliance_score']}% (Grade {data['overall_grade']})")
    
    def test_pdf_export(self, admin_token):
        """GET /api/reports/executive-pdf returns valid PDF"""
        response = requests.get(
            f"{BASE_URL}/api/reports/executive-pdf",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/pdf"
        # Check PDF magic bytes
        assert response.content[:4] == b'%PDF'
        print(f"PASSED: PDF export returns valid PDF ({len(response.content)} bytes)")


class TestNotificationSystem:
    """Test notification system"""
    
    @pytest.fixture
    def admin_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_ADMIN)
        return response.json()["token"]
    
    def test_unread_count(self, admin_token):
        """GET /api/notifications/unread-count returns count"""
        response = requests.get(
            f"{BASE_URL}/api/notifications/unread-count",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        assert "unread_count" in data
        print(f"PASSED: Unread count: {data['unread_count']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
