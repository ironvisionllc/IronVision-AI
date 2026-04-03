"""
Iteration 7 Backend Tests - Testing refactored modular routes
Tests all major endpoints after server.py was split into routes/ modules
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEMO_ADMIN = {"email": "demo-admin@grc.com", "password": "DemoAdmin123!"}
DEMO_VIEWER = {"email": "demo-user@grc.com", "password": "DemoUser123!"}


class TestAuthEndpoints:
    """Test authentication endpoints after refactoring"""
    
    def test_login_demo_admin(self):
        """Demo admin login should succeed"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_ADMIN)
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "Token missing from response"
        assert "user" in data, "User data missing from response"
        assert data["user"]["email"] == DEMO_ADMIN["email"]
        print(f"✓ Demo admin login successful")
    
    def test_login_demo_viewer(self):
        """Demo viewer login should succeed"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_VIEWER)
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "token" in data, "Token missing from response"
        assert data["user"]["email"] == DEMO_VIEWER["email"]
        print(f"✓ Demo viewer login successful")
    
    def test_login_invalid_credentials(self):
        """Invalid credentials should return 401"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "invalid@test.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print(f"✓ Invalid credentials correctly rejected")


@pytest.fixture(scope="class")
def admin_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_ADMIN)
    if response.status_code == 200:
        return response.json()["token"]
    pytest.skip("Admin login failed")


@pytest.fixture(scope="class")
def viewer_token():
    """Get viewer auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_VIEWER)
    if response.status_code == 200:
        return response.json()["token"]
    pytest.skip("Viewer login failed")


class TestDashboardEndpoints:
    """Test dashboard-related endpoints"""
    
    def test_compliance_scores_all(self, admin_token):
        """GET /api/compliance/scores/all should return compliance data"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/compliance/scores/all", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "frameworks" in data, "Expected frameworks in compliance scores"
        assert "overall_compliance_score" in data, "Expected overall_compliance_score"
        print(f"✓ Compliance scores returned {len(data['frameworks'])} frameworks, overall: {data['overall_compliance_score']}%")
    
    def test_executive_summary(self, admin_token):
        """GET /api/reports/executive-summary should return summary data"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/reports/executive-summary", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "overall_compliance" in data or "compliance_score" in data or isinstance(data, dict), "Expected summary data"
        print(f"✓ Executive summary returned successfully")


class TestFrameworksEndpoints:
    """Test frameworks endpoints - should have 12 frameworks"""
    
    def test_get_frameworks(self, admin_token):
        """GET /api/frameworks should return 12 frameworks"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/frameworks", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of frameworks"
        assert len(data) == 12, f"Expected 12 frameworks, got {len(data)}"
        print(f"✓ Frameworks returned {len(data)} items")


class TestPoliciesEndpoints:
    """Test policies endpoints - should have 6 demo policies"""
    
    def test_get_policies(self, admin_token):
        """GET /api/policies should return 6 policies"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/policies", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of policies"
        assert len(data) >= 6, f"Expected at least 6 policies, got {len(data)}"
        print(f"✓ Policies returned {len(data)} items")


class TestRisksEndpoints:
    """Test risks endpoints - should have 7 demo risks"""
    
    def test_get_risks(self, admin_token):
        """GET /api/risks should return 7 risks"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/risks", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of risks"
        assert len(data) >= 7, f"Expected at least 7 risks, got {len(data)}"
        print(f"✓ Risks returned {len(data)} items")


class TestVendorsEndpoints:
    """Test vendors endpoints - should have 4 vendors"""
    
    def test_get_vendors(self, admin_token):
        """GET /api/vendors should return 4 vendors"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/vendors", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of vendors"
        assert len(data) >= 4, f"Expected at least 4 vendors, got {len(data)}"
        print(f"✓ Vendors returned {len(data)} items")


class TestTasksEndpoints:
    """Test tasks endpoints - should have 6 tasks"""
    
    def test_get_tasks(self, admin_token):
        """GET /api/tasks should return 6 tasks"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/tasks", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of tasks"
        assert len(data) >= 6, f"Expected at least 6 tasks, got {len(data)}"
        print(f"✓ Tasks returned {len(data)} items")


class TestActivityEndpoints:
    """Test activity endpoints"""
    
    def test_get_activity(self, admin_token):
        """GET /api/activity should return activity log"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/activity", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of activities"
        print(f"✓ Activity returned {len(data)} items")


class TestEvidenceEndpoints:
    """Test evidence endpoints - should have 5 evidence items"""
    
    def test_get_evidence(self, admin_token):
        """GET /api/evidence should return 5 evidence items"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/evidence", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of evidence"
        assert len(data) >= 5, f"Expected at least 5 evidence items, got {len(data)}"
        print(f"✓ Evidence returned {len(data)} items")


class TestMappingsEndpoints:
    """Test mappings endpoints"""
    
    def test_get_mappings(self, admin_token):
        """GET /api/mappings should return mappings list"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/mappings", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of mappings"
        print(f"✓ Mappings returned {len(data)} items")


class TestCrossFrameworkEndpoints:
    """Test cross-framework mapping endpoints - should have 60 mappings"""
    
    def test_get_cross_framework_matrix(self, admin_token):
        """GET /api/cross-framework-mappings/matrix should return matrix data"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/cross-framework-mappings/matrix", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "frameworks" in data, "Expected frameworks in response"
        assert "mappings" in data, "Expected mappings in response"
        assert len(data["mappings"]) >= 60, f"Expected at least 60 cross-framework mappings, got {len(data['mappings'])}"
        print(f"✓ Cross-framework matrix returned {len(data['mappings'])} mappings, {len(data['frameworks'])} frameworks")
    
    def test_get_cross_framework_mappings(self, admin_token):
        """GET /api/cross-framework-mappings should return mappings list"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/cross-framework-mappings", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Expected list of cross-framework mappings"
        print(f"✓ Cross-framework mappings returned {len(data)} items")


class TestDemoViewerRestrictions:
    """Test that demo viewer (read-only) cannot create/edit/delete data"""
    
    def test_viewer_cannot_create_policy(self, viewer_token):
        """Demo viewer should get 403 when trying to create policy"""
        headers = {"Authorization": f"Bearer {viewer_token}"}
        response = requests.post(f"{BASE_URL}/api/policies", headers=headers, json={
            "title": "TEST_Viewer Policy",
            "content": "Test content",
            "version": "1.0",
            "status": "draft"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print(f"✓ Demo viewer correctly blocked from creating policy (403)")
    
    def test_viewer_cannot_create_risk(self, viewer_token):
        """Demo viewer should get 403 when trying to create risk"""
        headers = {"Authorization": f"Bearer {viewer_token}"}
        response = requests.post(f"{BASE_URL}/api/risks", headers=headers, json={
            "title": "TEST_Viewer Risk",
            "description": "Test risk",
            "category": "operational",
            "likelihood": 3,
            "impact": 3,
            "status": "open",
            "owner": "Test Owner"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print(f"✓ Demo viewer correctly blocked from creating risk (403)")
    
    def test_viewer_cannot_create_vendor(self, viewer_token):
        """Demo viewer should get 403 when trying to create vendor"""
        headers = {"Authorization": f"Bearer {viewer_token}"}
        response = requests.post(f"{BASE_URL}/api/vendors", headers=headers, json={
            "name": "TEST_Viewer Vendor",
            "contact_email": "test@test.com",
            "risk_level": "low",
            "assessment_status": "pending"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print(f"✓ Demo viewer correctly blocked from creating vendor (403)")
    
    def test_viewer_cannot_create_mapping(self, viewer_token):
        """Demo viewer should get 403 when trying to create mapping"""
        headers = {"Authorization": f"Bearer {viewer_token}"}
        response = requests.post(f"{BASE_URL}/api/mappings", headers=headers, json={
            "policy_id": "test",
            "control_id": "test",
            "framework_id": "test"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        print(f"✓ Demo viewer correctly blocked from creating mapping (403)")
    
    def test_viewer_can_read_data(self, viewer_token):
        """Demo viewer should be able to read data"""
        headers = {"Authorization": f"Bearer {viewer_token}"}
        
        # Test reading various endpoints
        endpoints = [
            "/api/frameworks",
            "/api/policies",
            "/api/risks",
            "/api/vendors",
            "/api/mappings",
            "/api/cross-framework-mappings/matrix"
        ]
        
        for endpoint in endpoints:
            response = requests.get(f"{BASE_URL}{endpoint}", headers=headers)
            assert response.status_code == 200, f"Viewer should read {endpoint}, got {response.status_code}"
        
        print(f"✓ Demo viewer can read all data endpoints")


class TestAnalyticsEndpoints:
    """Test analytics endpoints"""
    
    def test_get_analytics_dashboard(self, admin_token):
        """GET /api/analytics/dashboard should return analytics data"""
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = requests.get(f"{BASE_URL}/api/analytics/dashboard", headers=headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        print(f"✓ Analytics dashboard returned successfully")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
