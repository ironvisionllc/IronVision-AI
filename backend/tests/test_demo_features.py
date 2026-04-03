"""
Test Demo Features for GRC Platform
Tests: Pre-seeded data, Read-only mode, Demo account restrictions
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Demo credentials
DEMO_ADMIN_EMAIL = "demo-admin@grc.com"
DEMO_ADMIN_PASSWORD = "DemoAdmin123!"
DEMO_USER_EMAIL = "demo-user@grc.com"
DEMO_USER_PASSWORD = "DemoUser123!"


class TestDemoLogin:
    """Test demo account login functionality"""
    
    def test_demo_admin_login(self):
        """Demo Admin can login successfully"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_ADMIN_EMAIL,
            "password": DEMO_ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["email"] == DEMO_ADMIN_EMAIL
        assert data["user"]["is_demo"] == True
        assert data["user"]["roles"][0]["role"] == "admin"
        print("✓ Demo Admin login successful")
    
    def test_demo_user_login(self):
        """Demo User (viewer) can login successfully"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_USER_EMAIL,
            "password": DEMO_USER_PASSWORD
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["email"] == DEMO_USER_EMAIL
        assert data["user"]["is_demo"] == True
        assert data["user"]["roles"][0]["role"] == "viewer"
        print("✓ Demo User login successful")


class TestPreSeededData:
    """Test that demo accounts have pre-seeded data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get demo admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_ADMIN_EMAIL,
            "password": DEMO_ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}
    
    def test_preseeded_policies(self):
        """Dashboard should show 6 pre-seeded policies"""
        response = requests.get(f"{BASE_URL}/api/policies", headers=self.headers)
        assert response.status_code == 200
        policies = response.json()
        assert len(policies) >= 6, f"Expected at least 6 policies, got {len(policies)}"
        print(f"✓ Found {len(policies)} pre-seeded policies")
    
    def test_preseeded_tasks(self):
        """Should have 6 pre-seeded tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=self.headers)
        assert response.status_code == 200
        tasks = response.json()
        assert len(tasks) >= 6, f"Expected at least 6 tasks, got {len(tasks)}"
        print(f"✓ Found {len(tasks)} pre-seeded tasks")
    
    def test_preseeded_risks(self):
        """Should have open risks"""
        response = requests.get(f"{BASE_URL}/api/risks", headers=self.headers)
        assert response.status_code == 200
        risks = response.json()
        open_risks = [r for r in risks if r.get("status") == "open"]
        assert len(open_risks) >= 5, f"Expected at least 5 open risks, got {len(open_risks)}"
        print(f"✓ Found {len(open_risks)} open risks")
    
    def test_preseeded_vendors(self):
        """Should have 4 pre-seeded vendors"""
        response = requests.get(f"{BASE_URL}/api/vendors", headers=self.headers)
        assert response.status_code == 200
        vendors = response.json()
        assert len(vendors) >= 4, f"Expected at least 4 vendors, got {len(vendors)}"
        print(f"✓ Found {len(vendors)} pre-seeded vendors")
    
    def test_preseeded_audits(self):
        """Should have 2 pre-seeded audits"""
        response = requests.get(f"{BASE_URL}/api/audits", headers=self.headers)
        assert response.status_code == 200
        audits = response.json()
        assert len(audits) >= 2, f"Expected at least 2 audits, got {len(audits)}"
        print(f"✓ Found {len(audits)} pre-seeded audits")
    
    def test_preseeded_evidence(self):
        """Should have pre-seeded evidence items"""
        response = requests.get(f"{BASE_URL}/api/evidence", headers=self.headers)
        assert response.status_code == 200
        evidence = response.json()
        assert len(evidence) >= 5, f"Expected at least 5 evidence items, got {len(evidence)}"
        print(f"✓ Found {len(evidence)} pre-seeded evidence items")
    
    def test_preseeded_activity(self):
        """Should have pre-seeded activity log entries"""
        response = requests.get(f"{BASE_URL}/api/activity", headers=self.headers)
        assert response.status_code == 200
        activities = response.json()
        assert len(activities) >= 6, f"Expected at least 6 activity entries, got {len(activities)}"
        print(f"✓ Found {len(activities)} pre-seeded activity entries")
    
    def test_preseeded_mappings(self):
        """Should have control mappings for compliance score"""
        response = requests.get(f"{BASE_URL}/api/mappings", headers=self.headers)
        assert response.status_code == 200
        mappings = response.json()
        assert len(mappings) >= 32, f"Expected at least 32 mappings, got {len(mappings)}"
        print(f"✓ Found {len(mappings)} pre-seeded control mappings")
    
    def test_dashboard_analytics(self):
        """Dashboard analytics should show pre-seeded data counts"""
        response = requests.get(f"{BASE_URL}/api/analytics/dashboard", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert data["policies_count"] >= 6, f"Expected at least 6 policies, got {data['policies_count']}"
        assert data["mappings_count"] >= 32, f"Expected at least 32 mappings, got {data['mappings_count']}"
        print(f"✓ Dashboard analytics: {data['policies_count']} policies, {data['mappings_count']} mappings")
    
    def test_executive_summary(self):
        """Executive summary should show compliance data"""
        response = requests.get(f"{BASE_URL}/api/reports/executive-summary", headers=self.headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("policies_count", 0) >= 6
        assert data.get("total_mapped", 0) >= 32
        print(f"✓ Executive summary: {data.get('overall_compliance_score', 0)}% compliance score")


class TestReadOnlyDemoMode:
    """Test that demo accounts cannot modify data (403 responses)"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Get demo admin token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_ADMIN_EMAIL,
            "password": DEMO_ADMIN_PASSWORD
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
    
    def test_demo_cannot_create_task(self):
        """POST /api/tasks should return 403 for demo account"""
        response = requests.post(f"{BASE_URL}/api/tasks", headers=self.headers, json={
            "title": "TEST_Demo Task",
            "description": "This should fail",
            "status": "todo",
            "priority": "medium"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        assert "Demo mode" in response.json().get("detail", "")
        print("✓ POST /api/tasks correctly returns 403 for demo account")
    
    def test_demo_cannot_create_policy(self):
        """POST /api/policies should return 403 for demo account"""
        response = requests.post(f"{BASE_URL}/api/policies", headers=self.headers, json={
            "title": "TEST_Demo Policy",
            "content": "This should fail",
            "version": "1.0",
            "status": "draft"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        assert "Demo mode" in response.json().get("detail", "")
        print("✓ POST /api/policies correctly returns 403 for demo account")
    
    def test_demo_cannot_create_evidence(self):
        """POST /api/evidence should return 403 for demo account"""
        response = requests.post(f"{BASE_URL}/api/evidence", headers=self.headers, json={
            "description": "TEST_Demo Evidence",
            "evidence_type": "document"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        assert "Demo mode" in response.json().get("detail", "")
        print("✓ POST /api/evidence correctly returns 403 for demo account")
    
    def test_demo_cannot_update_risk(self):
        """PUT /api/risks/{id} should return 403 for demo account"""
        # First get a risk ID
        risks_response = requests.get(f"{BASE_URL}/api/risks", headers=self.headers)
        risks = risks_response.json()
        if risks:
            risk_id = risks[0]["id"]
            response = requests.put(f"{BASE_URL}/api/risks/{risk_id}", headers=self.headers, json={
                "id": risk_id,
                "organization_id": "demo-org-001",
                "title": "Modified Risk",
                "description": "This should fail",
                "category": "security",
                "likelihood": 3,
                "impact": 3,
                "risk_score": 9,
                "status": "open",
                "owner": "Test"
            })
            assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
            assert "Demo mode" in response.json().get("detail", "")
            print("✓ PUT /api/risks/{id} correctly returns 403 for demo account")
        else:
            pytest.skip("No risks found to test update")
    
    def test_demo_cannot_create_admin_user(self):
        """POST /api/admin/users should return 403 for demo account"""
        response = requests.post(f"{BASE_URL}/api/admin/users", headers=self.headers, json={
            "email": "test@test.com",
            "name": "Test User",
            "password": "test123",
            "role": "viewer"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        assert "Demo mode" in response.json().get("detail", "")
        print("✓ POST /api/admin/users correctly returns 403 for demo account")
    
    def test_demo_cannot_update_task(self):
        """PUT /api/tasks/{id} should return 403 for demo account"""
        tasks_response = requests.get(f"{BASE_URL}/api/tasks", headers=self.headers)
        tasks = tasks_response.json()
        if tasks:
            task_id = tasks[0]["id"]
            response = requests.put(f"{BASE_URL}/api/tasks/{task_id}", headers=self.headers, json={
                "title": "Modified Task",
                "status": "done"
            })
            assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
            assert "Demo mode" in response.json().get("detail", "")
            print("✓ PUT /api/tasks/{id} correctly returns 403 for demo account")
        else:
            pytest.skip("No tasks found to test update")
    
    def test_demo_cannot_delete_task(self):
        """DELETE /api/tasks/{id} should return 403 for demo account"""
        tasks_response = requests.get(f"{BASE_URL}/api/tasks", headers=self.headers)
        tasks = tasks_response.json()
        if tasks:
            task_id = tasks[0]["id"]
            response = requests.delete(f"{BASE_URL}/api/tasks/{task_id}", headers=self.headers)
            assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
            assert "Demo mode" in response.json().get("detail", "")
            print("✓ DELETE /api/tasks/{id} correctly returns 403 for demo account")
        else:
            pytest.skip("No tasks found to test delete")
    
    def test_demo_cannot_create_vendor(self):
        """POST /api/vendors should return 403 for demo account"""
        response = requests.post(f"{BASE_URL}/api/vendors", headers=self.headers, json={
            "name": "TEST_Demo Vendor",
            "contact_email": "test@vendor.com",
            "risk_level": "low",
            "assessment_status": "pending"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        assert "Demo mode" in response.json().get("detail", "")
        print("✓ POST /api/vendors correctly returns 403 for demo account")
    
    def test_demo_cannot_create_audit(self):
        """POST /api/audits should return 403 for demo account"""
        response = requests.post(f"{BASE_URL}/api/audits", headers=self.headers, json={
            "title": "TEST_Demo Audit",
            "framework_ids": [],
            "audit_type": "internal",
            "status": "scheduled",
            "scheduled_date": "2026-02-01T00:00:00Z",
            "auditor": "Test"
        })
        assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
        assert "Demo mode" in response.json().get("detail", "")
        print("✓ POST /api/audits correctly returns 403 for demo account")


class TestRegularUserCanModify:
    """Test that regular (non-demo) accounts CAN modify data"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Register a new test user"""
        import uuid
        self.test_email = f"test_{uuid.uuid4().hex[:8]}@test.com"
        
        # Register new user
        response = requests.post(f"{BASE_URL}/api/auth/register", json={
            "email": self.test_email,
            "password": "TestPass123!",
            "name": "Test User",
            "organization_name": "Test Org"
        })
        if response.status_code == 200:
            self.token = response.json()["token"]
            self.headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        else:
            pytest.skip(f"Could not register test user: {response.text}")
    
    def test_regular_user_can_create_task(self):
        """Regular user should be able to create tasks"""
        response = requests.post(f"{BASE_URL}/api/tasks", headers=self.headers, json={
            "title": "TEST_Regular User Task",
            "description": "This should succeed",
            "status": "todo",
            "priority": "medium"
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["title"] == "TEST_Regular User Task"
        print("✓ Regular user can create tasks")
        
        # Cleanup - delete the task
        task_id = data["id"]
        requests.delete(f"{BASE_URL}/api/tasks/{task_id}", headers=self.headers)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
