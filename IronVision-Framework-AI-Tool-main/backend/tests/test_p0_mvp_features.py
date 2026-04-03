"""
P0 MVP Features Backend Tests - Iteration 10
Tests for:
1. Dashboard API enhancements (risk_heatmap, recent_activity, upcoming_deadlines, overdue_tasks)
2. PDF executive report generation
3. Executive summary API
4. Create task from risk workflow
5. Activity/audit trail API
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token for demo admin"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo-admin@grc.com",
            "password": "DemoAdmin123!"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["token"]
    
    def test_login_success(self):
        """Test demo admin login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo-admin@grc.com",
            "password": "DemoAdmin123!"
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data
        assert "user" in data
        assert data["user"]["email"] == "demo-admin@grc.com"


class TestDashboardAnalytics:
    """Dashboard API enhancement tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo-admin@grc.com",
            "password": "DemoAdmin123!"
        })
        return response.json()["token"]
    
    def test_dashboard_returns_risk_heatmap(self, auth_token):
        """Test /api/analytics/dashboard returns risk_heatmap as 5x5 grid"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/dashboard",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify risk_heatmap exists and is 5x5 grid
        assert "risk_heatmap" in data
        heatmap = data["risk_heatmap"]
        assert len(heatmap) == 5, f"Heatmap should have 5 rows, got {len(heatmap)}"
        for row in heatmap:
            assert len(row) == 5, f"Each row should have 5 columns, got {len(row)}"
            for cell in row:
                assert isinstance(cell, int), f"Cell value should be int, got {type(cell)}"
    
    def test_dashboard_returns_recent_activity(self, auth_token):
        """Test /api/analytics/dashboard returns recent_activity"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/dashboard",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "recent_activity" in data
        activities = data["recent_activity"]
        assert isinstance(activities, list)
        
        # Verify activity structure if any exist
        if len(activities) > 0:
            activity = activities[0]
            assert "id" in activity
            assert "action" in activity
            assert "details" in activity
            assert "timestamp" in activity
            assert "user_name" in activity
    
    def test_dashboard_returns_upcoming_deadlines(self, auth_token):
        """Test /api/analytics/dashboard returns upcoming_deadlines"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/dashboard",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "upcoming_deadlines" in data
        deadlines = data["upcoming_deadlines"]
        assert isinstance(deadlines, list)
        
        # Verify deadline structure if any exist
        if len(deadlines) > 0:
            deadline = deadlines[0]
            assert "id" in deadline
            assert "title" in deadline
            assert "due_date" in deadline
            assert "priority" in deadline
    
    def test_dashboard_returns_overdue_tasks(self, auth_token):
        """Test /api/analytics/dashboard returns overdue_tasks"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/dashboard",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "overdue_tasks" in data
        overdue = data["overdue_tasks"]
        assert isinstance(overdue, list)
    
    def test_dashboard_returns_risk_distribution(self, auth_token):
        """Test /api/analytics/dashboard returns risk_distribution"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/dashboard",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "risk_distribution" in data
        dist = data["risk_distribution"]
        assert "low" in dist
        assert "medium" in dist
        assert "high" in dist
        assert "critical" in dist
    
    def test_dashboard_returns_counts(self, auth_token):
        """Test /api/analytics/dashboard returns policy/mapping/risk/audit counts"""
        response = requests.get(
            f"{BASE_URL}/api/analytics/dashboard",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "policies_count" in data
        assert "mappings_count" in data
        assert "open_risks_count" in data
        assert "audits_count" in data


class TestExecutiveSummary:
    """Executive summary API tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo-admin@grc.com",
            "password": "DemoAdmin123!"
        })
        return response.json()["token"]
    
    def test_executive_summary_returns_compliance_score(self, auth_token):
        """Test /api/reports/executive-summary returns overall compliance score"""
        response = requests.get(
            f"{BASE_URL}/api/reports/executive-summary",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "overall_compliance_score" in data
        assert "overall_grade" in data
        assert isinstance(data["overall_compliance_score"], int)
        assert data["overall_grade"] in ["A", "B", "C", "D", "F"]
    
    def test_executive_summary_returns_framework_scores(self, auth_token):
        """Test /api/reports/executive-summary returns framework scores"""
        response = requests.get(
            f"{BASE_URL}/api/reports/executive-summary",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "framework_scores" in data
        assert "total_frameworks" in data
        assert "total_controls" in data
        assert "total_mapped" in data
        
        scores = data["framework_scores"]
        assert isinstance(scores, list)
        assert len(scores) > 0
        
        # Verify framework score structure
        fw = scores[0]
        assert "framework_id" in fw
        assert "framework_name" in fw
        assert "total_controls" in fw
        assert "mapped_controls" in fw
        assert "score" in fw
        assert "grade" in fw
    
    def test_executive_summary_returns_risk_summary(self, auth_token):
        """Test /api/reports/executive-summary returns risk summary"""
        response = requests.get(
            f"{BASE_URL}/api/reports/executive-summary",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "risk_summary" in data
        risk = data["risk_summary"]
        assert "total" in risk
        assert "open" in risk
        assert "critical_high" in risk
    
    def test_executive_summary_returns_task_summary(self, auth_token):
        """Test /api/reports/executive-summary returns task summary"""
        response = requests.get(
            f"{BASE_URL}/api/reports/executive-summary",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "task_summary" in data
        task = data["task_summary"]
        assert "total" in task
        assert "done" in task
        assert "overdue" in task
    
    def test_executive_summary_returns_vendor_summary(self, auth_token):
        """Test /api/reports/executive-summary returns vendor summary"""
        response = requests.get(
            f"{BASE_URL}/api/reports/executive-summary",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        data = response.json()
        
        assert "vendor_summary" in data
        vendor = data["vendor_summary"]
        assert "total" in vendor
        assert "high_risk" in vendor


class TestPDFReport:
    """PDF executive report generation tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo-admin@grc.com",
            "password": "DemoAdmin123!"
        })
        return response.json()["token"]
    
    def test_pdf_endpoint_returns_pdf(self, auth_token):
        """Test /api/reports/executive-pdf returns valid PDF"""
        response = requests.get(
            f"{BASE_URL}/api/reports/executive-pdf",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        assert response.headers.get("content-type") == "application/pdf"
        
        # Verify PDF content starts with PDF magic bytes
        content = response.content
        assert len(content) > 0, "PDF content should not be empty"
        assert content[:4] == b'%PDF', "Content should start with PDF magic bytes"
    
    def test_pdf_has_content_disposition(self, auth_token):
        """Test /api/reports/executive-pdf has proper content-disposition header"""
        response = requests.get(
            f"{BASE_URL}/api/reports/executive-pdf",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp
        assert "compliance_report" in content_disp
        assert ".pdf" in content_disp


class TestCreateTaskFromRisk:
    """Create task from risk workflow tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo-admin@grc.com",
            "password": "DemoAdmin123!"
        })
        return response.json()["token"]
    
    def test_get_risks_returns_open_risks(self, auth_token):
        """Test /api/risks returns risks with open status"""
        response = requests.get(
            f"{BASE_URL}/api/risks",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        risks = response.json()
        assert isinstance(risks, list)
        
        # Verify risk structure
        if len(risks) > 0:
            risk = risks[0]
            assert "id" in risk
            assert "title" in risk
            assert "status" in risk
            assert "risk_score" in risk
            assert "likelihood" in risk
            assert "impact" in risk
            assert "category" in risk
    
    def test_create_task_from_risk_workflow(self, auth_token):
        """Test creating a task from a risk (remediation workflow)"""
        # First get a risk
        risks_response = requests.get(
            f"{BASE_URL}/api/risks",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert risks_response.status_code == 200
        risks = risks_response.json()
        assert len(risks) > 0, "Need at least one risk to test"
        
        risk = risks[0]
        
        # Create task from risk
        priority = "critical" if risk["risk_score"] > 12 else "high" if risk["risk_score"] > 8 else "medium"
        task_data = {
            "title": f"TEST_Remediate: {risk['title']}",
            "description": f"Risk remediation task.\nRisk: {risk['title']}\nCategory: {risk['category']}\nScore: {risk['risk_score']}",
            "status": "todo",
            "priority": priority,
            "tags": ["risk-remediation", risk["category"]]
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/tasks",
            headers={"Authorization": f"Bearer {auth_token}"},
            json=task_data
        )
        assert create_response.status_code == 200, f"Failed to create task: {create_response.text}"
        
        created_task = create_response.json()
        assert "id" in created_task
        assert created_task["title"] == task_data["title"]
        assert created_task["priority"] == priority
        assert "risk-remediation" in created_task["tags"]
        
        # Verify task was persisted
        tasks_response = requests.get(
            f"{BASE_URL}/api/tasks",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert tasks_response.status_code == 200
        tasks = tasks_response.json()
        task_ids = [t["id"] for t in tasks]
        assert created_task["id"] in task_ids
        
        # Cleanup - delete test task
        delete_response = requests.delete(
            f"{BASE_URL}/api/tasks/{created_task['id']}",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert delete_response.status_code == 200


class TestActivityAuditTrail:
    """Activity/audit trail API tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo-admin@grc.com",
            "password": "DemoAdmin123!"
        })
        return response.json()["token"]
    
    def test_activity_endpoint_returns_activities(self, auth_token):
        """Test /api/activity returns activity log"""
        response = requests.get(
            f"{BASE_URL}/api/activity",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        activities = response.json()
        assert isinstance(activities, list)
    
    def test_activity_has_required_fields(self, auth_token):
        """Test activity items have required fields for timeline view"""
        response = requests.get(
            f"{BASE_URL}/api/activity",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        activities = response.json()
        
        if len(activities) > 0:
            activity = activities[0]
            assert "id" in activity
            assert "action" in activity
            assert "details" in activity
            assert "timestamp" in activity
            assert "user_name" in activity
    
    def test_activity_action_types(self, auth_token):
        """Test activity has various action types for filtering"""
        response = requests.get(
            f"{BASE_URL}/api/activity",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        activities = response.json()
        
        if len(activities) > 0:
            action_types = set(a["action"] for a in activities)
            # Should have at least some action types
            valid_actions = {"task_created", "task_updated", "policy_created", "risk_created", 
                          "vendor_created", "evidence_added", "mapping_created", "audit_created"}
            # At least one action type should be valid
            assert len(action_types & valid_actions) > 0, f"No valid action types found: {action_types}"


class TestTasksAPI:
    """Tasks API tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo-admin@grc.com",
            "password": "DemoAdmin123!"
        })
        return response.json()["token"]
    
    def test_get_tasks(self, auth_token):
        """Test /api/tasks returns tasks list"""
        response = requests.get(
            f"{BASE_URL}/api/tasks",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        tasks = response.json()
        assert isinstance(tasks, list)
    
    def test_task_stats(self, auth_token):
        """Test /api/tasks/stats returns task statistics"""
        response = requests.get(
            f"{BASE_URL}/api/tasks/stats",
            headers={"Authorization": f"Bearer {auth_token}"}
        )
        assert response.status_code == 200
        stats = response.json()
        
        assert "total" in stats
        assert "todo" in stats
        assert "in_progress" in stats
        assert "done" in stats
        assert "overdue" in stats


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
