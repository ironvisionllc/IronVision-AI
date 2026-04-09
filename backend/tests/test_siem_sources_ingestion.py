"""
Test SIEM Source Management, Webhook Ingestion, and Live Simulator
Tests for iteration 5 features:
- Source CRUD (create, list, delete)
- Webhook ingestion with API key auth
- Multiple format support (Splunk, CloudTrail, QRadar, Generic)
- Live simulator start/stop/status
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestSIEMSourceManagement:
    """Tests for SIEM source CRUD operations"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo-admin@grc.com",
            "password": "DemoAdmin123!"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Headers with auth token"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    def test_list_sources(self, auth_headers):
        """GET /api/siem/sources - List all sources"""
        response = requests.get(f"{BASE_URL}/api/siem/sources", headers=auth_headers)
        assert response.status_code == 200, f"Failed to list sources: {response.text}"
        data = response.json()
        assert isinstance(data, list), "Response should be a list"
        # Each source should have required fields
        if len(data) > 0:
            src = data[0]
            assert "id" in src, "Source should have id"
            assert "name" in src, "Source should have name"
            assert "source_key" in src, "Source should have source_key"
            assert "source_type" in src, "Source should have source_type"
            assert "event_count" in src, "Source should have event_count"
        print(f"✓ Listed {len(data)} sources")
    
    def test_create_source_splunk(self, auth_headers):
        """POST /api/siem/sources - Create Splunk source"""
        payload = {
            "name": "TEST_Splunk_Source",
            "source_type": "splunk"
        }
        response = requests.post(f"{BASE_URL}/api/siem/sources", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Failed to create source: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "id" in data, "Response should have id"
        assert "source_key" in data, "Response should have source_key"
        assert "api_key" in data, "Response should have api_key"
        assert data["name"] == "TEST_Splunk_Source", "Name should match"
        assert data["source_type"] == "splunk", "Type should be splunk"
        assert data["source_key"].startswith("src_"), "source_key should start with src_"
        assert data["api_key"].startswith("iv_siem_"), "api_key should start with iv_siem_"
        
        print(f"✓ Created Splunk source: {data['source_key']}")
        return data
    
    def test_create_source_cloudtrail(self, auth_headers):
        """POST /api/siem/sources - Create CloudTrail source"""
        payload = {
            "name": "TEST_CloudTrail_Source",
            "source_type": "cloudtrail"
        }
        response = requests.post(f"{BASE_URL}/api/siem/sources", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Failed to create source: {response.text}"
        data = response.json()
        assert data["source_type"] == "cloudtrail"
        print(f"✓ Created CloudTrail source: {data['source_key']}")
        return data
    
    def test_create_source_generic(self, auth_headers):
        """POST /api/siem/sources - Create Generic JSON source"""
        payload = {
            "name": "TEST_Generic_Source",
            "source_type": "generic"
        }
        response = requests.post(f"{BASE_URL}/api/siem/sources", json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Failed to create source: {response.text}"
        data = response.json()
        assert data["source_type"] == "generic"
        print(f"✓ Created Generic source: {data['source_key']}")
        return data


class TestWebhookIngestion:
    """Tests for webhook event ingestion endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo-admin@grc.com",
            "password": "DemoAdmin123!"
        })
        assert response.status_code == 200
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    @pytest.fixture(scope="class")
    def test_source(self, auth_headers):
        """Create a test source for ingestion tests"""
        payload = {
            "name": "TEST_Ingestion_Source",
            "source_type": "splunk"
        }
        response = requests.post(f"{BASE_URL}/api/siem/sources", json=payload, headers=auth_headers)
        assert response.status_code == 200
        return response.json()
    
    def test_ingest_splunk_format(self, test_source):
        """POST /api/siem/ingest/{source_key} - Splunk HEC format"""
        source_key = test_source["source_key"]
        api_key = test_source["api_key"]
        
        # Splunk HEC format
        payload = {
            "event": {
                "event_type": "login_failed",
                "severity": "5",
                "message": "Failed login attempt from 192.168.1.100"
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/siem/ingest/{source_key}",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": api_key
            }
        )
        assert response.status_code == 200, f"Ingestion failed: {response.text}"
        data = response.json()
        assert data["status"] == "ingested", "Status should be ingested"
        assert data["events_created"] >= 1, "Should create at least 1 event"
        print(f"✓ Ingested Splunk event: {data['events_created']} events created")
    
    def test_ingest_generic_format(self, test_source):
        """POST /api/siem/ingest/{source_key} - Generic JSON format"""
        source_key = test_source["source_key"]
        api_key = test_source["api_key"]
        
        # Generic JSON format
        payload = {
            "event_type": "unauthorized_access",
            "severity": "high",
            "details": "User attempted to access restricted resource",
            "user_name": "test_user@example.com",
            "ip_address": "10.0.0.50"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/siem/ingest/{source_key}",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": api_key
            }
        )
        assert response.status_code == 200, f"Ingestion failed: {response.text}"
        data = response.json()
        assert data["status"] == "ingested"
        print(f"✓ Ingested Generic event: {data['events_created']} events created")
    
    def test_ingest_invalid_api_key(self, test_source):
        """POST /api/siem/ingest/{source_key} - Invalid API key returns 401"""
        source_key = test_source["source_key"]
        
        payload = {"event_type": "test", "severity": "info"}
        
        response = requests.post(
            f"{BASE_URL}/api/siem/ingest/{source_key}",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": "invalid_api_key_12345"
            }
        )
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✓ Invalid API key correctly returns 401")
    
    def test_ingest_invalid_source_key(self):
        """POST /api/siem/ingest/{source_key} - Invalid source_key returns 404"""
        payload = {"event_type": "test", "severity": "info"}
        
        response = requests.post(
            f"{BASE_URL}/api/siem/ingest/invalid_source_key_xyz",
            json=payload,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": "any_key"
            }
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Invalid source_key correctly returns 404")
    
    def test_ingest_cloudtrail_format(self, auth_headers):
        """POST /api/siem/ingest/{source_key} - AWS CloudTrail format"""
        # Create CloudTrail source
        payload = {
            "name": "TEST_CloudTrail_Ingest",
            "source_type": "cloudtrail"
        }
        response = requests.post(f"{BASE_URL}/api/siem/sources", json=payload, headers=auth_headers)
        assert response.status_code == 200
        source = response.json()
        
        # CloudTrail format
        cloudtrail_payload = {
            "Records": [
                {
                    "eventName": "ConsoleLogin",
                    "userIdentity": {"userName": "admin@company.com", "arn": "arn:aws:iam::123456789:user/admin"},
                    "sourceIPAddress": "203.0.113.50",
                    "awsRegion": "us-east-1"
                }
            ]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/siem/ingest/{source['source_key']}",
            json=cloudtrail_payload,
            headers={
                "Content-Type": "application/json",
                "X-API-Key": source["api_key"]
            }
        )
        assert response.status_code == 200, f"CloudTrail ingestion failed: {response.text}"
        data = response.json()
        assert data["events_created"] >= 1
        print(f"✓ Ingested CloudTrail event: {data['events_created']} events created")


class TestSimulator:
    """Tests for SIEM live simulator"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo-admin@grc.com",
            "password": "DemoAdmin123!"
        })
        assert response.status_code == 200
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    def test_simulator_status(self, auth_headers):
        """GET /api/siem/simulator/status - Check simulator status"""
        response = requests.get(f"{BASE_URL}/api/siem/simulator/status", headers=auth_headers)
        assert response.status_code == 200, f"Failed to get status: {response.text}"
        data = response.json()
        assert "active" in data, "Response should have 'active' field"
        assert isinstance(data["active"], bool), "'active' should be boolean"
        print(f"✓ Simulator status: active={data['active']}")
    
    def test_simulator_start(self, auth_headers):
        """POST /api/siem/simulator/start - Start simulator"""
        response = requests.post(f"{BASE_URL}/api/siem/simulator/start", headers=auth_headers)
        assert response.status_code == 200, f"Failed to start simulator: {response.text}"
        data = response.json()
        assert data["status"] in ["started", "already_running"], f"Unexpected status: {data['status']}"
        print(f"✓ Simulator start: {data['status']}")
        
        # Verify status is now active
        status_response = requests.get(f"{BASE_URL}/api/siem/simulator/status", headers=auth_headers)
        assert status_response.status_code == 200
        assert status_response.json()["active"] == True, "Simulator should be active after start"
        print("✓ Simulator confirmed active")
    
    def test_simulator_generates_events(self, auth_headers):
        """Verify simulator generates events"""
        # Get initial event count
        dashboard_response = requests.get(f"{BASE_URL}/api/siem/dashboard?days=1", headers=auth_headers)
        assert dashboard_response.status_code == 200
        initial_count = dashboard_response.json()["total_events"]
        
        # Wait for simulator to generate events (2-6 seconds per event)
        print("Waiting 10 seconds for simulator to generate events...")
        time.sleep(10)
        
        # Get new event count
        dashboard_response = requests.get(f"{BASE_URL}/api/siem/dashboard?days=1", headers=auth_headers)
        assert dashboard_response.status_code == 200
        new_count = dashboard_response.json()["total_events"]
        
        events_generated = new_count - initial_count
        print(f"✓ Simulator generated {events_generated} events (initial: {initial_count}, new: {new_count})")
        # Should generate at least 1 event in 10 seconds (2-6 sec interval)
        assert events_generated >= 1, f"Expected at least 1 new event, got {events_generated}"
    
    def test_simulator_stop(self, auth_headers):
        """POST /api/siem/simulator/stop - Stop simulator"""
        response = requests.post(f"{BASE_URL}/api/siem/simulator/stop", headers=auth_headers)
        assert response.status_code == 200, f"Failed to stop simulator: {response.text}"
        data = response.json()
        assert data["status"] == "stopped", f"Unexpected status: {data['status']}"
        print(f"✓ Simulator stopped")
        
        # Verify status is now inactive
        status_response = requests.get(f"{BASE_URL}/api/siem/simulator/status", headers=auth_headers)
        assert status_response.status_code == 200
        assert status_response.json()["active"] == False, "Simulator should be inactive after stop"
        print("✓ Simulator confirmed inactive")


class TestSourceDeletion:
    """Tests for source deletion - run last to clean up"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo-admin@grc.com",
            "password": "DemoAdmin123!"
        })
        assert response.status_code == 200
        return response.json()["token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    def test_delete_source(self, auth_headers):
        """DELETE /api/siem/sources/{source_id} - Delete a source"""
        # First create a source to delete
        payload = {
            "name": "TEST_Delete_Source",
            "source_type": "generic"
        }
        create_response = requests.post(f"{BASE_URL}/api/siem/sources", json=payload, headers=auth_headers)
        assert create_response.status_code == 200
        source = create_response.json()
        source_id = source["id"]
        
        # Delete the source
        delete_response = requests.delete(f"{BASE_URL}/api/siem/sources/{source_id}", headers=auth_headers)
        assert delete_response.status_code == 200, f"Failed to delete source: {delete_response.text}"
        data = delete_response.json()
        assert data["status"] == "deleted"
        print(f"✓ Deleted source: {source_id}")
        
        # Verify source is gone from list
        list_response = requests.get(f"{BASE_URL}/api/siem/sources", headers=auth_headers)
        assert list_response.status_code == 200
        sources = list_response.json()
        source_ids = [s["id"] for s in sources]
        assert source_id not in source_ids, "Deleted source should not appear in list"
        print("✓ Verified source removed from list")
    
    def test_delete_nonexistent_source(self, auth_headers):
        """DELETE /api/siem/sources/{source_id} - Delete non-existent source returns 404"""
        response = requests.delete(f"{BASE_URL}/api/siem/sources/nonexistent-id-12345", headers=auth_headers)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Delete non-existent source correctly returns 404")
    
    def test_cleanup_test_sources(self, auth_headers):
        """Clean up all TEST_ prefixed sources"""
        list_response = requests.get(f"{BASE_URL}/api/siem/sources", headers=auth_headers)
        assert list_response.status_code == 200
        sources = list_response.json()
        
        deleted_count = 0
        for src in sources:
            if src["name"].startswith("TEST_"):
                delete_response = requests.delete(f"{BASE_URL}/api/siem/sources/{src['id']}", headers=auth_headers)
                if delete_response.status_code == 200:
                    deleted_count += 1
        
        print(f"✓ Cleaned up {deleted_count} test sources")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
