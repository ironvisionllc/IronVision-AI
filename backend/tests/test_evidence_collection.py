"""
Test Automated Evidence Collection Feature
- POST /api/evidence-collection/collect - auto-collect evidence from SIEM, pipeline, policies, assessments, checklists
- GET /api/evidence-collection/artifacts - list all collected evidence artifacts
- GET /api/evidence-collection/artifacts/{id} - get artifact detail
- DELETE /api/evidence-collection/artifacts/{id} - delete artifact
- GET /api/evidence-collection/coverage - per-framework evidence coverage analysis
- GET /api/evidence-collection/stats - total artifacts, by type, freshness stats
- GET /api/evidence-collection/runs - collection run history
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestEvidenceCollectionAuth:
    """Test authentication for evidence collection endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo-admin@grc.com",
            "password": "DemoAdmin123!"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        token = response.json().get("token")
        assert token, "No token returned"
        return token
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get auth headers"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestEvidenceCollectionCollect(TestEvidenceCollectionAuth):
    """Test POST /api/evidence-collection/collect - run automated collection"""
    
    def test_run_collection(self, auth_headers):
        """Test running automated evidence collection"""
        response = requests.post(f"{BASE_URL}/api/evidence-collection/collect", headers=auth_headers)
        assert response.status_code == 200, f"Collection failed: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "message" in data, "Missing message in response"
        assert "total" in data, "Missing total in response"
        assert "by_type" in data, "Missing by_type in response"
        assert "run_id" in data, "Missing run_id in response"
        
        # Verify total is a number
        assert isinstance(data["total"], int), "total should be an integer"
        
        # Verify by_type is a dict
        assert isinstance(data["by_type"], dict), "by_type should be a dict"
        
        # Verify run_id is a string
        assert isinstance(data["run_id"], str), "run_id should be a string"
        assert len(data["run_id"]) > 0, "run_id should not be empty"
        
        print(f"Collection completed: {data['message']}")
        print(f"Total artifacts: {data['total']}")
        print(f"By type: {data['by_type']}")


class TestEvidenceCollectionArtifacts(TestEvidenceCollectionAuth):
    """Test GET /api/evidence-collection/artifacts - list artifacts"""
    
    def test_list_artifacts(self, auth_headers):
        """Test listing all evidence artifacts"""
        response = requests.get(f"{BASE_URL}/api/evidence-collection/artifacts", headers=auth_headers)
        assert response.status_code == 200, f"List artifacts failed: {response.text}"
        
        data = response.json()
        # Should be a list
        assert isinstance(data, list), "Response should be a list"
        
        # If artifacts exist, verify structure
        if len(data) > 0:
            artifact = data[0]
            assert "id" in artifact, "Artifact missing id"
            assert "evidence_type" in artifact, "Artifact missing evidence_type"
            assert "title" in artifact, "Artifact missing title"
            assert "collected_at" in artifact, "Artifact missing collected_at"
            
            # Verify evidence_type is one of expected types
            valid_types = ["siem_snapshot", "pipeline_report", "policy_document", "compliance_assessment", "checklist_mapping", "manual_upload"]
            assert artifact["evidence_type"] in valid_types, f"Invalid evidence_type: {artifact['evidence_type']}"
            
            print(f"Found {len(data)} artifacts")
            print(f"First artifact: {artifact['title']} ({artifact['evidence_type']})")
        else:
            print("No artifacts found - run collection first")


class TestEvidenceCollectionArtifactDetail(TestEvidenceCollectionAuth):
    """Test GET /api/evidence-collection/artifacts/{id} - get artifact detail"""
    
    def test_get_artifact_detail(self, auth_headers):
        """Test getting artifact detail by ID"""
        # First get list of artifacts
        list_response = requests.get(f"{BASE_URL}/api/evidence-collection/artifacts", headers=auth_headers)
        assert list_response.status_code == 200
        artifacts = list_response.json()
        
        if len(artifacts) == 0:
            pytest.skip("No artifacts to test detail endpoint")
        
        artifact_id = artifacts[0]["id"]
        
        # Get detail
        response = requests.get(f"{BASE_URL}/api/evidence-collection/artifacts/{artifact_id}", headers=auth_headers)
        assert response.status_code == 200, f"Get artifact detail failed: {response.text}"
        
        data = response.json()
        assert data["id"] == artifact_id, "Artifact ID mismatch"
        assert "evidence_type" in data, "Missing evidence_type"
        assert "title" in data, "Missing title"
        assert "description" in data, "Missing description"
        assert "source" in data, "Missing source"
        assert "collected_at" in data, "Missing collected_at"
        
        print(f"Artifact detail: {data['title']}")
        print(f"Source: {data['source']}")
        print(f"Controls linked: {len(data.get('control_ids', []))}")
    
    def test_get_artifact_not_found(self, auth_headers):
        """Test getting non-existent artifact returns 404"""
        response = requests.get(f"{BASE_URL}/api/evidence-collection/artifacts/non-existent-id-12345", headers=auth_headers)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestEvidenceCollectionCoverage(TestEvidenceCollectionAuth):
    """Test GET /api/evidence-collection/coverage - coverage analysis"""
    
    def test_get_coverage(self, auth_headers):
        """Test getting evidence coverage analysis"""
        response = requests.get(f"{BASE_URL}/api/evidence-collection/coverage", headers=auth_headers)
        assert response.status_code == 200, f"Get coverage failed: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "frameworks" in data, "Missing frameworks in response"
        assert "summary" in data, "Missing summary in response"
        
        # Verify frameworks is a list
        assert isinstance(data["frameworks"], list), "frameworks should be a list"
        
        # Verify summary structure
        summary = data["summary"]
        assert "total_controls" in summary, "Missing total_controls in summary"
        assert "covered" in summary, "Missing covered in summary"
        assert "coverage_pct" in summary, "Missing coverage_pct in summary"
        assert "total_artifacts" in summary, "Missing total_artifacts in summary"
        
        # If frameworks exist, verify structure
        if len(data["frameworks"]) > 0:
            fw = data["frameworks"][0]
            assert "framework_id" in fw, "Missing framework_id"
            assert "framework_name" in fw, "Missing framework_name"
            assert "total_controls" in fw, "Missing total_controls"
            assert "covered" in fw, "Missing covered"
            assert "uncovered" in fw, "Missing uncovered"
            assert "coverage_pct" in fw, "Missing coverage_pct"
            
            print(f"Coverage summary: {summary['coverage_pct']}% ({summary['covered']}/{summary['total_controls']} controls)")
            print(f"Frameworks analyzed: {len(data['frameworks'])}")
        else:
            print("No frameworks found for coverage analysis")


class TestEvidenceCollectionStats(TestEvidenceCollectionAuth):
    """Test GET /api/evidence-collection/stats - statistics"""
    
    def test_get_stats(self, auth_headers):
        """Test getting evidence collection statistics"""
        response = requests.get(f"{BASE_URL}/api/evidence-collection/stats", headers=auth_headers)
        assert response.status_code == 200, f"Get stats failed: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert "total_artifacts" in data, "Missing total_artifacts"
        assert "by_type" in data, "Missing by_type"
        assert "fresh" in data, "Missing fresh"
        assert "stale" in data, "Missing stale"
        
        # Verify types
        assert isinstance(data["total_artifacts"], int), "total_artifacts should be int"
        assert isinstance(data["by_type"], dict), "by_type should be dict"
        assert isinstance(data["fresh"], int), "fresh should be int"
        assert isinstance(data["stale"], int), "stale should be int"
        
        # Verify fresh + stale = total
        assert data["fresh"] + data["stale"] == data["total_artifacts"], "fresh + stale should equal total"
        
        print(f"Stats: {data['total_artifacts']} total, {data['fresh']} fresh, {data['stale']} stale")
        print(f"By type: {data['by_type']}")


class TestEvidenceCollectionRuns(TestEvidenceCollectionAuth):
    """Test GET /api/evidence-collection/runs - run history"""
    
    def test_get_runs(self, auth_headers):
        """Test getting collection run history"""
        response = requests.get(f"{BASE_URL}/api/evidence-collection/runs", headers=auth_headers)
        assert response.status_code == 200, f"Get runs failed: {response.text}"
        
        data = response.json()
        # Should be a list
        assert isinstance(data, list), "Response should be a list"
        
        # If runs exist, verify structure
        if len(data) > 0:
            run = data[0]
            assert "id" in run, "Run missing id"
            assert "total_collected" in run, "Run missing total_collected"
            assert "by_type" in run, "Run missing by_type"
            assert "created_at" in run, "Run missing created_at"
            
            print(f"Found {len(data)} collection runs")
            print(f"Latest run: {run['total_collected']} artifacts at {run['created_at']}")
        else:
            print("No collection runs found")


class TestEvidenceCollectionDelete(TestEvidenceCollectionAuth):
    """Test DELETE /api/evidence-collection/artifacts/{id} - delete artifact"""
    
    def test_delete_artifact(self, auth_headers):
        """Test deleting an artifact"""
        # First run collection to ensure we have artifacts
        collect_response = requests.post(f"{BASE_URL}/api/evidence-collection/collect", headers=auth_headers)
        assert collect_response.status_code == 200
        
        # Get list of artifacts
        list_response = requests.get(f"{BASE_URL}/api/evidence-collection/artifacts", headers=auth_headers)
        assert list_response.status_code == 200
        artifacts = list_response.json()
        
        if len(artifacts) == 0:
            pytest.skip("No artifacts to delete")
        
        # Find a test artifact to delete (prefer one with TEST_ prefix or just use first)
        artifact_to_delete = artifacts[0]
        artifact_id = artifact_to_delete["id"]
        
        # Delete the artifact
        delete_response = requests.delete(f"{BASE_URL}/api/evidence-collection/artifacts/{artifact_id}", headers=auth_headers)
        assert delete_response.status_code == 200, f"Delete failed: {delete_response.text}"
        
        data = delete_response.json()
        assert "message" in data, "Missing message in delete response"
        
        # Verify artifact is deleted
        get_response = requests.get(f"{BASE_URL}/api/evidence-collection/artifacts/{artifact_id}", headers=auth_headers)
        assert get_response.status_code == 404, "Artifact should be deleted"
        
        print(f"Successfully deleted artifact: {artifact_to_delete['title']}")
    
    def test_delete_artifact_not_found(self, auth_headers):
        """Test deleting non-existent artifact returns 404"""
        response = requests.delete(f"{BASE_URL}/api/evidence-collection/artifacts/non-existent-id-12345", headers=auth_headers)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"


class TestDocumentationPages:
    """Test documentation HTML pages are accessible"""
    
    def test_marketing_page(self):
        """Test /docs/marketing.html is accessible"""
        response = requests.get(f"{BASE_URL}/docs/marketing.html")
        assert response.status_code == 200, f"Marketing page failed: {response.status_code}"
        assert "text/html" in response.headers.get("Content-Type", ""), "Should return HTML"
        print("Marketing page accessible: 200 OK")
    
    def test_security_architecture_page(self):
        """Test /docs/security-architecture.html is accessible"""
        response = requests.get(f"{BASE_URL}/docs/security-architecture.html")
        assert response.status_code == 200, f"Security architecture page failed: {response.status_code}"
        assert "text/html" in response.headers.get("Content-Type", ""), "Should return HTML"
        print("Security architecture page accessible: 200 OK")
    
    def test_ui_walkthrough_page(self):
        """Test /docs/ui-walkthrough.html is accessible"""
        response = requests.get(f"{BASE_URL}/docs/ui-walkthrough.html")
        assert response.status_code == 200, f"UI walkthrough page failed: {response.status_code}"
        assert "text/html" in response.headers.get("Content-Type", ""), "Should return HTML"
        print("UI walkthrough page accessible: 200 OK")
    
    def test_pitch_deck_page(self):
        """Test /docs/pitch-deck.html is accessible"""
        response = requests.get(f"{BASE_URL}/docs/pitch-deck.html")
        assert response.status_code == 200, f"Pitch deck page failed: {response.status_code}"
        assert "text/html" in response.headers.get("Content-Type", ""), "Should return HTML"
        print("Pitch deck page accessible: 200 OK")
    
    def test_brochure_page(self):
        """Test /docs/brochure.html is accessible"""
        response = requests.get(f"{BASE_URL}/docs/brochure.html")
        assert response.status_code == 200, f"Brochure page failed: {response.status_code}"
        assert "text/html" in response.headers.get("Content-Type", ""), "Should return HTML"
        print("Brochure page accessible: 200 OK")


class TestEvidenceCollectionUnauthorized:
    """Test endpoints require authentication"""
    
    def test_collect_unauthorized(self):
        """Test collect endpoint requires auth"""
        response = requests.post(f"{BASE_URL}/api/evidence-collection/collect")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_artifacts_unauthorized(self):
        """Test artifacts endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/evidence-collection/artifacts")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_coverage_unauthorized(self):
        """Test coverage endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/evidence-collection/coverage")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_stats_unauthorized(self):
        """Test stats endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/evidence-collection/stats")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_runs_unauthorized(self):
        """Test runs endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/evidence-collection/runs")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
