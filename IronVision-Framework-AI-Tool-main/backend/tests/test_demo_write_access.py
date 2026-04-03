"""
Test Demo Admin Write Access and Demo Viewer Restrictions
Tests the 3 new features:
1. Demo admin (demo-admin@grc.com) CAN create tasks, policies, risks
2. Demo viewer (demo-user@grc.com) CANNOT create (403)
3. Demo data auto-reset - 6 seeded policies for demo org
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


class TestDemoAdminWriteAccess:
    """Demo admin should have full write access"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get demo admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_ADMIN_EMAIL,
            "password": DEMO_ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Demo admin login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["is_demo"] == True
        return data["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    def test_demo_admin_can_create_task(self, admin_headers):
        """Demo admin should be able to create tasks (200 response)"""
        response = requests.post(f"{BASE_URL}/api/tasks", json={
            "title": "TEST_Demo Admin Task",
            "description": "Task created by demo admin",
            "status": "todo",
            "priority": "medium"
        }, headers=admin_headers)
        
        assert response.status_code == 200, f"Demo admin should create task, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["title"] == "TEST_Demo Admin Task"
        print(f"SUCCESS: Demo admin created task with id: {data['id']}")
    
    def test_demo_admin_can_create_policy(self, admin_headers):
        """Demo admin should be able to create policies (200 response)"""
        response = requests.post(f"{BASE_URL}/api/policies", json={
            "title": "TEST_Demo Admin Policy",
            "content": "Policy content created by demo admin",
            "version": "1.0",
            "status": "draft"
        }, headers=admin_headers)
        
        assert response.status_code == 200, f"Demo admin should create policy, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["title"] == "TEST_Demo Admin Policy"
        print(f"SUCCESS: Demo admin created policy with id: {data['id']}")
    
    def test_demo_admin_can_create_risk(self, admin_headers):
        """Demo admin should be able to create risks (200 response)"""
        response = requests.post(f"{BASE_URL}/api/risks", json={
            "title": "TEST_Demo Admin Risk",
            "description": "Risk created by demo admin",
            "category": "security",
            "likelihood": 3,
            "impact": 4,
            "status": "open",
            "owner": "Demo Admin"
        }, headers=admin_headers)
        
        assert response.status_code == 200, f"Demo admin should create risk, got {response.status_code}: {response.text}"
        data = response.json()
        assert data["title"] == "TEST_Demo Admin Risk"
        assert data["risk_score"] == 12  # 3 * 4
        print(f"SUCCESS: Demo admin created risk with id: {data['id']}")


class TestDemoViewerRestrictions:
    """Demo viewer should be blocked from write operations"""
    
    @pytest.fixture(scope="class")
    def viewer_token(self):
        """Get demo viewer auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_VIEWER_EMAIL,
            "password": DEMO_VIEWER_PASSWORD
        })
        assert response.status_code == 200, f"Demo viewer login failed: {response.text}"
        data = response.json()
        assert "token" in data
        assert data["user"]["is_demo"] == True
        return data["token"]
    
    @pytest.fixture(scope="class")
    def viewer_headers(self, viewer_token):
        return {"Authorization": f"Bearer {viewer_token}", "Content-Type": "application/json"}
    
    def test_demo_viewer_cannot_create_task(self, viewer_headers):
        """Demo viewer should get 403 when trying to create tasks"""
        response = requests.post(f"{BASE_URL}/api/tasks", json={
            "title": "TEST_Viewer Task Should Fail",
            "description": "This should be blocked",
            "status": "todo",
            "priority": "medium"
        }, headers=viewer_headers)
        
        assert response.status_code == 403, f"Demo viewer should get 403, got {response.status_code}: {response.text}"
        data = response.json()
        assert "demo" in data.get("detail", "").lower() or "viewer" in data.get("detail", "").lower()
        print(f"SUCCESS: Demo viewer blocked from creating task (403)")
    
    def test_demo_viewer_cannot_create_policy(self, viewer_headers):
        """Demo viewer should get 403 when trying to create policies"""
        response = requests.post(f"{BASE_URL}/api/policies", json={
            "title": "TEST_Viewer Policy Should Fail",
            "content": "This should be blocked",
            "version": "1.0",
            "status": "draft"
        }, headers=viewer_headers)
        
        assert response.status_code == 403, f"Demo viewer should get 403, got {response.status_code}: {response.text}"
        print(f"SUCCESS: Demo viewer blocked from creating policy (403)")
    
    def test_demo_viewer_cannot_create_risk(self, viewer_headers):
        """Demo viewer should get 403 when trying to create risks"""
        response = requests.post(f"{BASE_URL}/api/risks", json={
            "title": "TEST_Viewer Risk Should Fail",
            "description": "This should be blocked",
            "category": "security",
            "likelihood": 2,
            "impact": 3,
            "status": "open",
            "owner": "Viewer"
        }, headers=viewer_headers)
        
        assert response.status_code == 403, f"Demo viewer should get 403, got {response.status_code}: {response.text}"
        print(f"SUCCESS: Demo viewer blocked from creating risk (403)")
    
    def test_demo_viewer_can_read_tasks(self, viewer_headers):
        """Demo viewer should still be able to read tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=viewer_headers)
        assert response.status_code == 200, f"Demo viewer should read tasks, got {response.status_code}"
        print(f"SUCCESS: Demo viewer can read tasks")
    
    def test_demo_viewer_can_read_policies(self, viewer_headers):
        """Demo viewer should still be able to read policies"""
        response = requests.get(f"{BASE_URL}/api/policies", headers=viewer_headers)
        assert response.status_code == 200, f"Demo viewer should read policies, got {response.status_code}"
        print(f"SUCCESS: Demo viewer can read policies")


class TestDemoDataAutoReset:
    """Demo data should be auto-reset with fresh seeded data"""
    
    @pytest.fixture(scope="class")
    def admin_token(self):
        """Get demo admin auth token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": DEMO_ADMIN_EMAIL,
            "password": DEMO_ADMIN_PASSWORD
        })
        assert response.status_code == 200
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def admin_headers(self, admin_token):
        return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}
    
    def test_demo_org_has_seeded_policies(self, admin_headers):
        """Demo org should have 6 seeded policies"""
        response = requests.get(f"{BASE_URL}/api/policies", headers=admin_headers)
        assert response.status_code == 200
        policies = response.json()
        
        # Filter out TEST_ prefixed policies (created by tests)
        seeded_policies = [p for p in policies if not p.get("title", "").startswith("TEST_")]
        
        # Should have at least 6 seeded policies
        assert len(seeded_policies) >= 6, f"Expected at least 6 seeded policies, got {len(seeded_policies)}"
        
        # Verify some expected policy titles
        titles = [p["title"] for p in seeded_policies]
        expected_titles = ["Information Security Policy", "Data Protection & Privacy Policy", "Incident Response Plan"]
        for expected in expected_titles:
            assert expected in titles, f"Missing expected policy: {expected}"
        
        print(f"SUCCESS: Demo org has {len(seeded_policies)} seeded policies")
    
    def test_demo_org_has_seeded_risks(self, admin_headers):
        """Demo org should have seeded risks"""
        response = requests.get(f"{BASE_URL}/api/risks", headers=admin_headers)
        assert response.status_code == 200
        risks = response.json()
        
        # Filter out TEST_ prefixed risks
        seeded_risks = [r for r in risks if not r.get("title", "").startswith("TEST_")]
        
        # Should have at least 7 seeded risks
        assert len(seeded_risks) >= 7, f"Expected at least 7 seeded risks, got {len(seeded_risks)}"
        print(f"SUCCESS: Demo org has {len(seeded_risks)} seeded risks")
    
    def test_demo_org_has_seeded_tasks(self, admin_headers):
        """Demo org should have seeded tasks"""
        response = requests.get(f"{BASE_URL}/api/tasks", headers=admin_headers)
        assert response.status_code == 200
        tasks = response.json()
        
        # Filter out TEST_ prefixed tasks
        seeded_tasks = [t for t in tasks if not t.get("title", "").startswith("TEST_")]
        
        # Should have at least 6 seeded tasks
        assert len(seeded_tasks) >= 6, f"Expected at least 6 seeded tasks, got {len(seeded_tasks)}"
        print(f"SUCCESS: Demo org has {len(seeded_tasks)} seeded tasks")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
