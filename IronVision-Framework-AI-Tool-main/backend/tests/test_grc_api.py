"""
GRC Platform API Tests
Tests for: Authentication, Tasks, Evidence, Activity, Executive Summary
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://grc-enterprise-3.preview.emergentagent.com')

# Demo credentials
DEMO_ADMIN = {"email": "demo-admin@grc.com", "password": "DemoAdmin123!"}
DEMO_USER = {"email": "demo-user@grc.com", "password": "DemoUser123!"}


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_ADMIN)
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def user_token():
    """Get viewer user authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_USER)
    assert response.status_code == 200, f"User login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture
def user_headers(user_token):
    return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}


class TestAuthentication:
    """Authentication endpoint tests"""

    def test_demo_admin_login(self):
        """Test demo admin login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_ADMIN)
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == "demo-admin@grc.com"
        assert data["user"]["roles"][0]["role"] == "admin"

    def test_demo_user_login(self):
        """Test demo user login works"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json=DEMO_USER)
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == "demo-user@grc.com"
        assert data["user"]["roles"][0]["role"] == "viewer"

    def test_invalid_credentials(self):
        """Test login with invalid credentials fails"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "invalid@test.com",
            "password": "wrongpassword"
        })
        assert response.status_code == 401

    def test_auth_me_endpoint(self, admin_headers):
        """Test /auth/me returns current user"""
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "demo-admin@grc.com"


class TestTasks:
    """Task management endpoint tests"""

    def test_get_tasks(self, admin_headers):
        """Test GET /tasks returns task list"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_task_stats(self, admin_headers):
        """Test GET /tasks/stats returns statistics"""
        response = requests.get(f"{BASE_URL}/api/tasks/stats", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "todo" in data
        assert "in_progress" in data
        assert "done" in data
        assert "overdue" in data

    def test_create_task(self, admin_headers):
        """Test POST /tasks creates a new task"""
        task_data = {
            "title": "TEST_API_Task_Creation",
            "description": "Testing task creation via API",
            "status": "todo",
            "priority": "high",
            "tags": ["test", "api"]
        }
        response = requests.post(f"{BASE_URL}/api/tasks", json=task_data, headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["title"] == "TEST_API_Task_Creation"
        assert data["priority"] == "high"
        assert "id" in data
        
        # Verify task was persisted
        task_id = data["id"]
        get_response = requests.get(f"{BASE_URL}/api/tasks", headers=admin_headers)
        tasks = get_response.json()
        assert any(t["id"] == task_id for t in tasks)

    def test_update_task(self, admin_headers):
        """Test PUT /tasks/{id} updates a task"""
        # First create a task
        task_data = {"title": "TEST_Task_To_Update", "status": "todo", "priority": "low"}
        create_response = requests.post(f"{BASE_URL}/api/tasks", json=task_data, headers=admin_headers)
        task_id = create_response.json()["id"]
        
        # Update the task
        update_data = {"title": "TEST_Task_Updated", "status": "in_progress", "priority": "high"}
        update_response = requests.put(f"{BASE_URL}/api/tasks/{task_id}", json=update_data, headers=admin_headers)
        assert update_response.status_code == 200

    def test_delete_task(self, admin_headers):
        """Test DELETE /tasks/{id} removes a task"""
        # First create a task
        task_data = {"title": "TEST_Task_To_Delete", "status": "todo", "priority": "low"}
        create_response = requests.post(f"{BASE_URL}/api/tasks", json=task_data, headers=admin_headers)
        task_id = create_response.json()["id"]
        
        # Delete the task
        delete_response = requests.delete(f"{BASE_URL}/api/tasks/{task_id}", headers=admin_headers)
        assert delete_response.status_code == 200


class TestEvidence:
    """Evidence library endpoint tests"""

    def test_get_evidence(self, admin_headers):
        """Test GET /evidence returns evidence list"""
        response = requests.get(f"{BASE_URL}/api/evidence", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_create_evidence(self, admin_headers):
        """Test POST /evidence creates new evidence"""
        evidence_data = {
            "description": "TEST_API_Evidence_Creation",
            "evidence_type": "document",
            "control_id": "CC1.1",
            "framework_name": "SOC 2",
            "tags": ["test", "api"]
        }
        response = requests.post(f"{BASE_URL}/api/evidence", json=evidence_data, headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == "TEST_API_Evidence_Creation"
        assert data["evidence_type"] == "document"
        assert "id" in data
        
        # Verify evidence was persisted
        evidence_id = data["id"]
        get_response = requests.get(f"{BASE_URL}/api/evidence", headers=admin_headers)
        evidence_list = get_response.json()
        assert any(e["id"] == evidence_id for e in evidence_list)

    def test_delete_evidence(self, admin_headers):
        """Test DELETE /evidence/{id} removes evidence"""
        # First create evidence
        evidence_data = {"description": "TEST_Evidence_To_Delete", "evidence_type": "screenshot"}
        create_response = requests.post(f"{BASE_URL}/api/evidence", json=evidence_data, headers=admin_headers)
        evidence_id = create_response.json()["id"]
        
        # Delete the evidence
        delete_response = requests.delete(f"{BASE_URL}/api/evidence/{evidence_id}", headers=admin_headers)
        assert delete_response.status_code == 200


class TestActivity:
    """Activity log endpoint tests"""

    def test_get_activity_log(self, admin_headers):
        """Test GET /activity returns activity log"""
        response = requests.get(f"{BASE_URL}/api/activity", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # Should have activity entries from task/evidence creation
        if len(data) > 0:
            assert "action" in data[0]
            assert "timestamp" in data[0]
            assert "user_name" in data[0]


class TestExecutiveSummary:
    """Executive summary and reports endpoint tests"""

    def test_get_executive_summary(self, admin_headers):
        """Test GET /reports/executive-summary returns summary data"""
        response = requests.get(f"{BASE_URL}/api/reports/executive-summary", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert "overall_compliance_score" in data
        assert "overall_grade" in data
        assert "framework_scores" in data
        assert "risk_summary" in data
        assert "task_summary" in data
        assert "vendor_summary" in data
        assert "policies_count" in data

    def test_get_dashboard_analytics(self, admin_headers):
        """Test GET /analytics/dashboard returns analytics"""
        response = requests.get(f"{BASE_URL}/api/analytics/dashboard", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "policies_count" in data
        assert "mappings_count" in data
        assert "risk_distribution" in data


class TestFrameworks:
    """Framework endpoint tests"""

    def test_get_frameworks(self, admin_headers):
        """Test GET /frameworks returns framework list"""
        response = requests.get(f"{BASE_URL}/api/frameworks", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0  # Should have seeded frameworks


class TestComplianceScores:
    """Compliance scoring endpoint tests"""

    def test_get_all_compliance_scores(self, admin_headers):
        """Test GET /compliance/scores/all returns all framework scores"""
        response = requests.get(f"{BASE_URL}/api/compliance/scores/all", headers=admin_headers)
        assert response.status_code == 200
        data = response.json()
        assert "overall_compliance_score" in data
        assert "frameworks" in data


class TestCleanup:
    """Cleanup test data"""

    def test_cleanup_test_tasks(self, admin_headers):
        """Clean up TEST_ prefixed tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=admin_headers)
        tasks = response.json()
        for task in tasks:
            if task.get("title", "").startswith("TEST_"):
                requests.delete(f"{BASE_URL}/api/tasks/{task['id']}", headers=admin_headers)

    def test_cleanup_test_evidence(self, admin_headers):
        """Clean up TEST_ prefixed evidence"""
        response = requests.get(f"{BASE_URL}/api/evidence", headers=admin_headers)
        evidence_list = response.json()
        for evidence in evidence_list:
            if evidence.get("description", "").startswith("TEST_"):
                requests.delete(f"{BASE_URL}/api/evidence/{evidence['id']}", headers=admin_headers)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
