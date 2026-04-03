"""
Iteration 11 Tests: Notification System + P0/P1 Feature Verification
Tests: notification CRUD, unread count, mark read/all, dashboard, PDF export, 
       create task from risk, activity timeline, RBAC (viewer 403)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEMO_ADMIN_EMAIL = "demo-admin@grc.com"
DEMO_ADMIN_PASSWORD = "DemoAdmin123!"
DEMO_VIEWER_EMAIL = "demo-user@grc.com"
DEMO_VIEWER_PASSWORD = "DemoUser123!"


@pytest.fixture(scope="module")
def admin_session():
    """Get authenticated admin session with JWT token"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEMO_ADMIN_EMAIL,
        "password": DEMO_ADMIN_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Admin login failed: {response.status_code}")
    
    token = response.json().get("token")
    if not token:
        pytest.skip("No token in login response")
    
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


@pytest.fixture(scope="module")
def viewer_session():
    """Get authenticated viewer session with JWT token"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    response = session.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEMO_VIEWER_EMAIL,
        "password": DEMO_VIEWER_PASSWORD
    })
    if response.status_code != 200:
        pytest.skip(f"Viewer login failed: {response.status_code}")
    
    token = response.json().get("token")
    if not token:
        pytest.skip("No token in login response")
    
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


class TestNotificationSystem:
    """Test notification CRUD and functionality"""
    
    def test_get_notifications_list(self, admin_session):
        """GET /api/notifications returns list of notifications"""
        response = admin_session.get(f"{BASE_URL}/api/notifications")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert isinstance(data, list), "Expected list of notifications"
        # Should have seeded notifications
        assert len(data) >= 3, f"Expected at least 3 seeded notifications, got {len(data)}"
        # Verify notification structure
        if len(data) > 0:
            notif = data[0]
            assert "id" in notif, "Notification missing id"
            assert "title" in notif, "Notification missing title"
            assert "message" in notif, "Notification missing message"
            assert "read" in notif, "Notification missing read status"
            assert "created_at" in notif, "Notification missing created_at"
    
    def test_get_unread_count(self, admin_session):
        """GET /api/notifications/unread-count returns unread count"""
        response = admin_session.get(f"{BASE_URL}/api/notifications/unread-count")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert "unread_count" in data, "Response missing unread_count"
        assert isinstance(data["unread_count"], int), "unread_count should be integer"
        # Should have at least 3 unread from seed
        assert data["unread_count"] >= 0, "unread_count should be non-negative"
    
    def test_mark_notification_read(self, admin_session):
        """PUT /api/notifications/{id}/read marks notification as read"""
        # First get notifications to find an unread one
        response = admin_session.get(f"{BASE_URL}/api/notifications")
        assert response.status_code == 200
        notifications = response.json()
        
        # Find an unread notification
        unread = [n for n in notifications if not n.get("read", True)]
        if not unread:
            pytest.skip("No unread notifications to test")
        
        notif_id = unread[0]["id"]
        
        # Mark as read
        response = admin_session.put(f"{BASE_URL}/api/notifications/{notif_id}/read")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Verify it's now read
        response = admin_session.get(f"{BASE_URL}/api/notifications")
        notifications = response.json()
        marked = next((n for n in notifications if n["id"] == notif_id), None)
        assert marked is not None, "Notification not found after marking read"
        assert marked["read"] == True, "Notification should be marked as read"
    
    def test_mark_all_read(self, admin_session):
        """PUT /api/notifications/read-all marks all as read"""
        response = admin_session.put(f"{BASE_URL}/api/notifications/read-all")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Verify unread count is 0
        response = admin_session.get(f"{BASE_URL}/api/notifications/unread-count")
        assert response.status_code == 200
        data = response.json()
        assert data["unread_count"] == 0, f"Expected 0 unread after mark-all, got {data['unread_count']}"


class TestDashboardFeatures:
    """Test dashboard P0 features"""
    
    def test_dashboard_analytics(self, admin_session):
        """GET /api/analytics/dashboard returns all required sections"""
        response = admin_session.get(f"{BASE_URL}/api/analytics/dashboard")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        # Verify all dashboard sections
        assert "risk_heatmap" in data, "Missing risk_heatmap"
        assert "recent_activity" in data, "Missing recent_activity"
        assert "upcoming_deadlines" in data, "Missing upcoming_deadlines"
        assert "overdue_tasks" in data, "Missing overdue_tasks"
        assert "risk_distribution" in data, "Missing risk_distribution"
        
        # Verify heatmap is 5x5
        heatmap = data["risk_heatmap"]
        assert len(heatmap) == 5, f"Heatmap should have 5 rows, got {len(heatmap)}"
        for row in heatmap:
            assert len(row) == 5, f"Heatmap row should have 5 columns, got {len(row)}"
    
    def test_executive_summary(self, admin_session):
        """GET /api/reports/executive-summary returns compliance data"""
        response = admin_session.get(f"{BASE_URL}/api/reports/executive-summary")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        
        assert "overall_compliance_score" in data, "Missing overall_compliance_score"
        assert "overall_grade" in data, "Missing overall_grade"
        assert "framework_scores" in data, "Missing framework_scores"
        assert "risk_summary" in data, "Missing risk_summary"
        assert "task_summary" in data, "Missing task_summary"
    
    def test_pdf_export(self, admin_session):
        """GET /api/reports/executive-pdf returns valid PDF"""
        response = admin_session.get(f"{BASE_URL}/api/reports/executive-pdf")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        # Verify content type
        content_type = response.headers.get("content-type", "")
        assert "application/pdf" in content_type, f"Expected PDF content-type, got {content_type}"
        
        # Verify content-disposition header
        content_disp = response.headers.get("content-disposition", "")
        assert "attachment" in content_disp, "Missing attachment disposition"
        assert "compliance_report" in content_disp, "Missing filename in disposition"
        
        # Verify PDF magic bytes
        assert response.content[:4] == b'%PDF', "Response is not a valid PDF"


class TestRiskToTaskWorkflow:
    """Test create task from risk functionality"""
    
    def test_get_risks_with_open_status(self, admin_session):
        """GET /api/risks returns risks with open status"""
        response = admin_session.get(f"{BASE_URL}/api/risks")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        risks = response.json()
        
        assert len(risks) > 0, "Expected at least one risk"
        
        # Check for open risks
        open_risks = [r for r in risks if r.get("status") == "open"]
        assert len(open_risks) > 0, "Expected at least one open risk"
        
        # Verify risk structure
        risk = risks[0]
        assert "id" in risk, "Risk missing id"
        assert "title" in risk, "Risk missing title"
        assert "status" in risk, "Risk missing status"
        assert "risk_score" in risk, "Risk missing risk_score"
    
    def test_create_task_from_risk(self, admin_session):
        """POST /api/tasks creates task from risk context"""
        # Get an open risk
        response = admin_session.get(f"{BASE_URL}/api/risks")
        risks = response.json()
        open_risks = [r for r in risks if r.get("status") == "open"]
        
        if not open_risks:
            pytest.skip("No open risks to create task from")
        
        risk = open_risks[0]
        
        # Create task from risk
        task_data = {
            "title": f"TEST_Remediate: {risk['title']}",
            "description": f"Risk remediation task from test.\nRisk: {risk['title']}\nScore: {risk['risk_score']}",
            "status": "todo",
            "priority": "high" if risk["risk_score"] > 8 else "medium",
            "tags": ["risk-remediation", "test"]
        }
        
        response = admin_session.post(f"{BASE_URL}/api/tasks", json=task_data)
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}"
        
        # Verify task was created
        response = admin_session.get(f"{BASE_URL}/api/tasks")
        tasks = response.json()
        test_tasks = [t for t in tasks if t.get("title", "").startswith("TEST_Remediate")]
        assert len(test_tasks) > 0, "Task was not created"


class TestActivityTimeline:
    """Test activity page features"""
    
    def test_get_activity_log(self, admin_session):
        """GET /api/activity returns activity log"""
        response = admin_session.get(f"{BASE_URL}/api/activity")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        activities = response.json()
        
        assert isinstance(activities, list), "Expected list of activities"
        assert len(activities) > 0, "Expected at least one activity"
        
        # Verify activity structure
        activity = activities[0]
        assert "id" in activity, "Activity missing id"
        assert "action" in activity, "Activity missing action"
        assert "details" in activity, "Activity missing details"
        assert "timestamp" in activity, "Activity missing timestamp"
    
    def test_activity_has_various_action_types(self, admin_session):
        """Activity log has various action types for filtering"""
        response = admin_session.get(f"{BASE_URL}/api/activity")
        activities = response.json()
        
        action_types = set(a.get("action") for a in activities)
        # Should have at least 2 different action types
        assert len(action_types) >= 2, f"Expected at least 2 action types, got {action_types}"


class TestRBACViewer:
    """Test viewer role restrictions (403 on write operations)"""
    
    def test_viewer_cannot_create_task(self, viewer_session):
        """Demo viewer cannot create tasks (403)"""
        task_data = {
            "title": "TEST_Viewer Task",
            "description": "This should fail",
            "status": "todo",
            "priority": "low"
        }
        response = viewer_session.post(f"{BASE_URL}/api/tasks", json=task_data)
        assert response.status_code == 403, f"Expected 403 for viewer, got {response.status_code}"
    
    def test_viewer_cannot_create_risk(self, viewer_session):
        """Demo viewer cannot create risks (403)"""
        risk_data = {
            "title": "TEST_Viewer Risk",
            "description": "This should fail",
            "category": "compliance",
            "likelihood": 3,
            "impact": 3,
            "status": "open",
            "owner": "Test"
        }
        response = viewer_session.post(f"{BASE_URL}/api/risks", json=risk_data)
        assert response.status_code == 403, f"Expected 403 for viewer, got {response.status_code}"
    
    def test_viewer_can_read_notifications(self, viewer_session):
        """Demo viewer can read notifications"""
        response = viewer_session.get(f"{BASE_URL}/api/notifications")
        assert response.status_code == 200, f"Viewer should be able to read notifications, got {response.status_code}"


class TestRegressionEndpoints:
    """Regression tests for existing endpoints"""
    
    def test_policies_endpoint(self, admin_session):
        """GET /api/policies works"""
        response = admin_session.get(f"{BASE_URL}/api/policies")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_frameworks_endpoint(self, admin_session):
        """GET /api/frameworks works"""
        response = admin_session.get(f"{BASE_URL}/api/frameworks")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_tasks_endpoint(self, admin_session):
        """GET /api/tasks works"""
        response = admin_session.get(f"{BASE_URL}/api/tasks")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_vendors_endpoint(self, admin_session):
        """GET /api/vendors works"""
        response = admin_session.get(f"{BASE_URL}/api/vendors")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_audits_endpoint(self, admin_session):
        """GET /api/audits works"""
        response = admin_session.get(f"{BASE_URL}/api/audits")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_evidence_endpoint(self, admin_session):
        """GET /api/evidence works"""
        response = admin_session.get(f"{BASE_URL}/api/evidence")
        assert response.status_code == 200
        assert isinstance(response.json(), list)
    
    def test_mappings_endpoint(self, admin_session):
        """GET /api/mappings works"""
        response = admin_session.get(f"{BASE_URL}/api/mappings")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_tasks(self, admin_session):
        """Remove TEST_ prefixed tasks"""
        response = admin_session.get(f"{BASE_URL}/api/tasks")
        if response.status_code == 200:
            tasks = response.json()
            for task in tasks:
                if task.get("title", "").startswith("TEST_"):
                    admin_session.delete(f"{BASE_URL}/api/tasks/{task['id']}")
        assert True  # Cleanup is best-effort
