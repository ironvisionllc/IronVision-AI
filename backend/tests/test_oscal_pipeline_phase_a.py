"""
Phase A Testing: OSCAL Support & CI/CD Pipeline Integration
- OSCAL import/export endpoints
- Pipeline webhook, gate, API keys, runs, stats
"""
import pytest
import requests
import os
import json
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# ─── Fixtures ─────────────────────────────────────────────

@pytest.fixture(scope="module")
def auth_token():
    """Get JWT token for authenticated requests."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo-admin@grc.com",
        "password": "DemoAdmin123!"
    })
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with JWT auth."""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def sample_oscal_catalog():
    """Load sample OSCAL catalog JSON."""
    path = "/app/backend/sample_checklists/sample_oscal_catalog.json"
    with open(path, "r") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def sample_oscal_component():
    """Load sample OSCAL component-definition JSON."""
    path = "/app/backend/sample_checklists/sample_oscal_component.json"
    with open(path, "r") as f:
        return json.load(f)


# ─── OSCAL Import Tests ───────────────────────────────────

class TestOSCALImport:
    """Test OSCAL import endpoint."""
    
    created_checklist_ids = []
    
    def test_import_oscal_catalog(self, auth_headers, sample_oscal_catalog):
        """POST /api/oscal/import with OSCAL catalog JSON - should parse controls from groups."""
        files = {
            "file": ("sample_oscal_catalog.json", json.dumps(sample_oscal_catalog), "application/json")
        }
        response = requests.post(
            f"{BASE_URL}/api/oscal/import",
            headers={"Authorization": auth_headers["Authorization"]},
            files=files
        )
        assert response.status_code == 200, f"OSCAL catalog import failed: {response.text}"
        
        data = response.json()
        assert "checklist" in data
        assert data["oscal_type"] == "catalog"
        assert data["controls_parsed"] > 0
        assert "message" in data
        
        # Verify controls were parsed from groups
        # Sample catalog has 3 groups (ac, au, cm) with multiple controls
        assert data["controls_parsed"] >= 8, f"Expected at least 8 controls, got {data['controls_parsed']}"
        
        # Store for cleanup
        self.created_checklist_ids.append(data["checklist"]["id"])
        print(f"PASS: Imported OSCAL catalog with {data['controls_parsed']} controls")
    
    def test_import_oscal_component_definition(self, auth_headers, sample_oscal_component):
        """POST /api/oscal/import with OSCAL component-definition JSON - should parse control implementations."""
        files = {
            "file": ("sample_oscal_component.json", json.dumps(sample_oscal_component), "application/json")
        }
        response = requests.post(
            f"{BASE_URL}/api/oscal/import",
            headers={"Authorization": auth_headers["Authorization"]},
            files=files
        )
        assert response.status_code == 200, f"OSCAL component import failed: {response.text}"
        
        data = response.json()
        assert "checklist" in data
        assert data["oscal_type"] == "component-definition"
        assert data["controls_parsed"] > 0
        
        # Sample component has 2 components with 5 total implemented-requirements
        assert data["controls_parsed"] >= 5, f"Expected at least 5 controls, got {data['controls_parsed']}"
        
        self.created_checklist_ids.append(data["checklist"]["id"])
        print(f"PASS: Imported OSCAL component-definition with {data['controls_parsed']} controls")
    
    def test_import_invalid_oscal_returns_400(self, auth_headers):
        """POST /api/oscal/import with invalid JSON should return 400."""
        files = {
            "file": ("invalid.json", json.dumps({"invalid": "data"}), "application/json")
        }
        response = requests.post(
            f"{BASE_URL}/api/oscal/import",
            headers={"Authorization": auth_headers["Authorization"]},
            files=files
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("PASS: Invalid OSCAL returns 400")
    
    def test_oscal_import_appears_in_checklists(self, auth_headers):
        """Verify OSCAL imports appear in ingestion checklists list."""
        response = requests.get(
            f"{BASE_URL}/api/ingestion/checklists",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        checklists = response.json()
        oscal_checklists = [c for c in checklists if c.get("source_type", "").startswith("oscal-")]
        assert len(oscal_checklists) >= 2, f"Expected at least 2 OSCAL checklists, found {len(oscal_checklists)}"
        
        # Verify source types
        source_types = [c["source_type"] for c in oscal_checklists]
        assert "oscal-catalog" in source_types, "Missing oscal-catalog in checklists"
        assert "oscal-component-definition" in source_types, "Missing oscal-component-definition in checklists"
        print(f"PASS: Found {len(oscal_checklists)} OSCAL checklists in ingestion list")


# ─── OSCAL Export Tests ───────────────────────────────────

class TestOSCALExport:
    """Test OSCAL export endpoints."""
    
    def test_export_framework_as_oscal_catalog(self, auth_headers):
        """GET /api/oscal/export/catalog/{framework_id} - should export framework as OSCAL catalog JSON."""
        # First get a framework ID
        fw_response = requests.get(f"{BASE_URL}/api/frameworks", headers=auth_headers)
        assert fw_response.status_code == 200
        frameworks = fw_response.json()
        assert len(frameworks) > 0, "No frameworks found"
        
        framework_id = frameworks[0]["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/oscal/export/catalog/{framework_id}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"OSCAL catalog export failed: {response.text}"
        
        data = response.json()
        assert "catalog" in data
        assert "uuid" in data["catalog"]
        assert "metadata" in data["catalog"]
        assert "groups" in data["catalog"]
        
        # Verify OSCAL structure
        metadata = data["catalog"]["metadata"]
        assert "title" in metadata
        assert "oscal-version" in metadata
        assert metadata["oscal-version"] == "1.2.1"
        
        print(f"PASS: Exported framework '{frameworks[0]['name']}' as OSCAL catalog with {len(data['catalog']['groups'])} groups")
    
    def test_export_assessment_as_oscal(self, auth_headers):
        """GET /api/oscal/export/assessment/{framework_id} - should export compliance results as OSCAL assessment-results JSON."""
        # Get a framework ID
        fw_response = requests.get(f"{BASE_URL}/api/frameworks", headers=auth_headers)
        frameworks = fw_response.json()
        framework_id = frameworks[0]["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/oscal/export/assessment/{framework_id}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"OSCAL assessment export failed: {response.text}"
        
        data = response.json()
        assert "assessment-results" in data
        assert "uuid" in data["assessment-results"]
        assert "metadata" in data["assessment-results"]
        assert "results" in data["assessment-results"]
        
        # Verify OSCAL assessment structure
        metadata = data["assessment-results"]["metadata"]
        assert "title" in metadata
        assert "oscal-version" in metadata
        
        print(f"PASS: Exported assessment results as OSCAL assessment-results")
    
    def test_export_nonexistent_framework_returns_404(self, auth_headers):
        """GET /api/oscal/export/catalog/{invalid_id} should return 404."""
        response = requests.get(
            f"{BASE_URL}/api/oscal/export/catalog/nonexistent-framework-id",
            headers=auth_headers
        )
        assert response.status_code == 404
        print("PASS: Nonexistent framework returns 404 for OSCAL export")


# ─── Pipeline API Key Tests ───────────────────────────────

class TestPipelineAPIKeys:
    """Test pipeline API key management endpoints."""
    
    created_key_id = None
    created_key_value = None
    
    def test_create_api_key(self, auth_headers):
        """POST /api/pipeline/api-keys - create pipeline API key (JWT auth)."""
        response = requests.post(
            f"{BASE_URL}/api/pipeline/api-keys",
            headers=auth_headers,
            json={"name": "TEST_GitHub_Actions_CI", "description": "Test key for CI/CD"}
        )
        assert response.status_code == 200, f"API key creation failed: {response.text}"
        
        data = response.json()
        assert "key" in data
        assert "key_id" in data
        assert "name" in data
        assert data["name"] == "TEST_GitHub_Actions_CI"
        assert data["key"].startswith("iv-pipe-")
        
        TestPipelineAPIKeys.created_key_id = data["key_id"]
        TestPipelineAPIKeys.created_key_value = data["key"]
        print(f"PASS: Created API key with prefix {data['key'][:12]}...")
    
    def test_list_api_keys(self, auth_headers):
        """GET /api/pipeline/api-keys - list API keys (JWT auth)."""
        response = requests.get(
            f"{BASE_URL}/api/pipeline/api-keys",
            headers=auth_headers
        )
        assert response.status_code == 200, f"List API keys failed: {response.text}"
        
        keys = response.json()
        assert isinstance(keys, list)
        
        # Find our test key
        test_keys = [k for k in keys if k.get("name") == "TEST_GitHub_Actions_CI"]
        assert len(test_keys) >= 1, "Test API key not found in list"
        
        # Verify key structure (should not include actual key hash)
        key = test_keys[0]
        assert "id" in key
        assert "name" in key
        assert "key_prefix" in key
        assert "active" in key
        assert "key_hash" not in key  # Should be excluded
        
        print(f"PASS: Listed {len(keys)} API keys")
    
    def test_revoke_api_key(self, auth_headers):
        """DELETE /api/pipeline/api-keys/{key_id} - revoke API key (JWT auth)."""
        # Create a key to revoke
        create_response = requests.post(
            f"{BASE_URL}/api/pipeline/api-keys",
            headers=auth_headers,
            json={"name": "TEST_Key_To_Revoke"}
        )
        key_id = create_response.json()["key_id"]
        
        response = requests.delete(
            f"{BASE_URL}/api/pipeline/api-keys/{key_id}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Revoke API key failed: {response.text}"
        
        # Verify key is now inactive
        list_response = requests.get(f"{BASE_URL}/api/pipeline/api-keys", headers=auth_headers)
        keys = list_response.json()
        revoked_key = next((k for k in keys if k["id"] == key_id), None)
        assert revoked_key is not None
        assert revoked_key["active"] == False
        
        print("PASS: Revoked API key successfully")
    
    def test_revoke_nonexistent_key_returns_404(self, auth_headers):
        """DELETE /api/pipeline/api-keys/{invalid_id} should return 404."""
        response = requests.delete(
            f"{BASE_URL}/api/pipeline/api-keys/nonexistent-key-id",
            headers=auth_headers
        )
        assert response.status_code == 404
        print("PASS: Nonexistent key returns 404")


# ─── Pipeline Webhook Tests ───────────────────────────────

class TestPipelineWebhook:
    """Test pipeline webhook endpoint (X-Pipeline-Key auth)."""
    
    created_run_id = None
    
    def test_webhook_receive_scan_results(self, auth_headers):
        """POST /api/pipeline/webhook - receive scan findings (X-Pipeline-Key auth)."""
        # First create an API key
        key_response = requests.post(
            f"{BASE_URL}/api/pipeline/api-keys",
            headers=auth_headers,
            json={"name": "TEST_Webhook_Key"}
        )
        api_key = key_response.json()["key"]
        
        # Send webhook with scan results
        webhook_payload = {
            "pipeline_name": "TEST_my-app-ci",
            "repo": "org/my-app",
            "branch": "main",
            "commit_sha": "abc123def456",
            "scan_type": "sast",
            "tool_name": "semgrep",
            "findings": [
                {
                    "title": "SQL Injection in login.py",
                    "description": "User input directly concatenated into SQL query",
                    "severity": "critical",
                    "category": "sast",
                    "file_path": "src/login.py",
                    "line_number": 42,
                    "cwe_id": "CWE-89"
                },
                {
                    "title": "Hardcoded Password",
                    "description": "Password found in source code",
                    "severity": "high",
                    "category": "secret",
                    "file_path": "config/settings.py",
                    "line_number": 15
                },
                {
                    "title": "Missing Input Validation",
                    "severity": "medium",
                    "category": "sast",
                    "file_path": "src/api.py",
                    "line_number": 100
                }
            ]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/pipeline/webhook",
            headers={"X-Pipeline-Key": api_key, "Content-Type": "application/json"},
            json=webhook_payload
        )
        assert response.status_code == 200, f"Webhook failed: {response.text}"
        
        data = response.json()
        assert "run_id" in data
        assert data["status"] == "received"
        assert data["total_findings"] == 3
        assert "severity_counts" in data
        assert data["severity_counts"]["critical"] == 1
        assert data["severity_counts"]["high"] == 1
        assert data["severity_counts"]["medium"] == 1
        assert "risk_score" in data
        
        TestPipelineWebhook.created_run_id = data["run_id"]
        print(f"PASS: Webhook received {data['total_findings']} findings, risk score: {data['risk_score']}")
    
    def test_webhook_without_api_key_returns_401(self):
        """POST /api/pipeline/webhook without X-Pipeline-Key should return 401."""
        response = requests.post(
            f"{BASE_URL}/api/pipeline/webhook",
            headers={"Content-Type": "application/json"},
            json={"pipeline_name": "test", "scan_type": "sast", "findings": []}
        )
        assert response.status_code == 401
        print("PASS: Webhook without API key returns 401")
    
    def test_webhook_with_invalid_key_returns_401(self):
        """POST /api/pipeline/webhook with invalid key should return 401."""
        response = requests.post(
            f"{BASE_URL}/api/pipeline/webhook",
            headers={"X-Pipeline-Key": "invalid-key", "Content-Type": "application/json"},
            json={"pipeline_name": "test", "scan_type": "sast", "findings": []}
        )
        assert response.status_code == 401
        print("PASS: Webhook with invalid key returns 401")


# ─── Pipeline Gate Tests ──────────────────────────────────

class TestPipelineGate:
    """Test pipeline compliance gate endpoint (X-Pipeline-Key auth)."""
    
    def test_gate_evaluation_pass(self, auth_headers):
        """POST /api/pipeline/gate - evaluate compliance gate with passing results."""
        # Create API key
        key_response = requests.post(
            f"{BASE_URL}/api/pipeline/api-keys",
            headers=auth_headers,
            json={"name": "TEST_Gate_Key"}
        )
        api_key = key_response.json()["key"]
        
        # Create a run with low severity findings
        webhook_payload = {
            "pipeline_name": "TEST_passing-pipeline",
            "scan_type": "sast",
            "findings": [
                {"title": "Minor issue", "severity": "low", "category": "sast"},
                {"title": "Info finding", "severity": "info", "category": "sast"}
            ]
        }
        webhook_response = requests.post(
            f"{BASE_URL}/api/pipeline/webhook",
            headers={"X-Pipeline-Key": api_key, "Content-Type": "application/json"},
            json=webhook_payload
        )
        run_id = webhook_response.json()["run_id"]
        
        # Evaluate gate
        response = requests.post(
            f"{BASE_URL}/api/pipeline/gate",
            headers={"X-Pipeline-Key": api_key, "Content-Type": "application/json"},
            json={"run_id": run_id, "policy": "default"}
        )
        assert response.status_code == 200, f"Gate evaluation failed: {response.text}"
        
        data = response.json()
        assert data["run_id"] == run_id
        assert data["gate_result"] == "pass"
        assert "violations" in data
        assert len(data["violations"]) == 0
        
        print(f"PASS: Gate evaluation returned 'pass' for low-severity findings")
    
    def test_gate_evaluation_fail(self, auth_headers):
        """POST /api/pipeline/gate - evaluate compliance gate with failing results."""
        # Create API key
        key_response = requests.post(
            f"{BASE_URL}/api/pipeline/api-keys",
            headers=auth_headers,
            json={"name": "TEST_Gate_Fail_Key"}
        )
        api_key = key_response.json()["key"]
        
        # Create a run with critical findings
        webhook_payload = {
            "pipeline_name": "TEST_failing-pipeline",
            "scan_type": "sast",
            "findings": [
                {"title": "Critical vuln 1", "severity": "critical", "category": "sast"},
                {"title": "Critical vuln 2", "severity": "critical", "category": "sast"},
                {"title": "High vuln", "severity": "high", "category": "sast"}
            ]
        }
        webhook_response = requests.post(
            f"{BASE_URL}/api/pipeline/webhook",
            headers={"X-Pipeline-Key": api_key, "Content-Type": "application/json"},
            json=webhook_payload
        )
        run_id = webhook_response.json()["run_id"]
        
        # Evaluate gate with strict policy
        response = requests.post(
            f"{BASE_URL}/api/pipeline/gate",
            headers={"X-Pipeline-Key": api_key, "Content-Type": "application/json"},
            json={"run_id": run_id, "policy": "strict"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["gate_result"] == "fail"
        assert len(data["violations"]) > 0
        
        print(f"PASS: Gate evaluation returned 'fail' with {len(data['violations'])} violations")
    
    def test_gate_nonexistent_run_returns_404(self, auth_headers):
        """POST /api/pipeline/gate with nonexistent run_id should return 404."""
        key_response = requests.post(
            f"{BASE_URL}/api/pipeline/api-keys",
            headers=auth_headers,
            json={"name": "TEST_Gate_404_Key"}
        )
        api_key = key_response.json()["key"]
        
        response = requests.post(
            f"{BASE_URL}/api/pipeline/gate",
            headers={"X-Pipeline-Key": api_key, "Content-Type": "application/json"},
            json={"run_id": "nonexistent-run-id", "policy": "default"}
        )
        assert response.status_code == 404
        print("PASS: Gate with nonexistent run returns 404")


# ─── Pipeline Runs Tests ──────────────────────────────────

class TestPipelineRuns:
    """Test pipeline runs endpoints (JWT auth)."""
    
    def test_list_pipeline_runs(self, auth_headers):
        """GET /api/pipeline/runs - list pipeline runs (JWT auth)."""
        response = requests.get(
            f"{BASE_URL}/api/pipeline/runs",
            headers=auth_headers
        )
        assert response.status_code == 200, f"List runs failed: {response.text}"
        
        runs = response.json()
        assert isinstance(runs, list)
        
        # Should have runs from previous tests
        test_runs = [r for r in runs if r.get("pipeline_name", "").startswith("TEST_")]
        assert len(test_runs) >= 1, "No test pipeline runs found"
        
        # Verify run structure
        run = test_runs[0]
        assert "id" in run
        assert "pipeline_name" in run
        assert "scan_type" in run
        assert "total_findings" in run
        assert "severity_counts" in run
        assert "risk_score" in run
        
        print(f"PASS: Listed {len(runs)} pipeline runs")
    
    def test_get_pipeline_run_detail(self, auth_headers):
        """GET /api/pipeline/runs/{run_id} - get run detail with findings (JWT auth)."""
        # Get a run ID
        list_response = requests.get(f"{BASE_URL}/api/pipeline/runs", headers=auth_headers)
        runs = list_response.json()
        test_runs = [r for r in runs if r.get("pipeline_name", "").startswith("TEST_")]
        assert len(test_runs) > 0
        
        run_id = test_runs[0]["id"]
        
        response = requests.get(
            f"{BASE_URL}/api/pipeline/runs/{run_id}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Get run detail failed: {response.text}"
        
        data = response.json()
        assert "run" in data
        assert "findings" in data
        assert "findings_by_category" in data
        
        # Verify findings structure
        if len(data["findings"]) > 0:
            finding = data["findings"][0]
            assert "id" in finding
            assert "title" in finding
            assert "severity" in finding
        
        print(f"PASS: Got run detail with {len(data['findings'])} findings")
    
    def test_get_nonexistent_run_returns_404(self, auth_headers):
        """GET /api/pipeline/runs/{invalid_id} should return 404."""
        response = requests.get(
            f"{BASE_URL}/api/pipeline/runs/nonexistent-run-id",
            headers=auth_headers
        )
        assert response.status_code == 404
        print("PASS: Nonexistent run returns 404")
    
    def test_delete_pipeline_run(self, auth_headers):
        """DELETE /api/pipeline/runs/{run_id} - delete run (JWT auth)."""
        # Create a run to delete
        key_response = requests.post(
            f"{BASE_URL}/api/pipeline/api-keys",
            headers=auth_headers,
            json={"name": "TEST_Delete_Run_Key"}
        )
        api_key = key_response.json()["key"]
        
        webhook_response = requests.post(
            f"{BASE_URL}/api/pipeline/webhook",
            headers={"X-Pipeline-Key": api_key, "Content-Type": "application/json"},
            json={"pipeline_name": "TEST_to-delete", "scan_type": "sast", "findings": []}
        )
        run_id = webhook_response.json()["run_id"]
        
        # Delete the run
        response = requests.delete(
            f"{BASE_URL}/api/pipeline/runs/{run_id}",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Delete run failed: {response.text}"
        
        # Verify it's deleted
        get_response = requests.get(f"{BASE_URL}/api/pipeline/runs/{run_id}", headers=auth_headers)
        assert get_response.status_code == 404
        
        print("PASS: Deleted pipeline run successfully")
    
    def test_delete_nonexistent_run_returns_404(self, auth_headers):
        """DELETE /api/pipeline/runs/{invalid_id} should return 404."""
        response = requests.delete(
            f"{BASE_URL}/api/pipeline/runs/nonexistent-run-id",
            headers=auth_headers
        )
        assert response.status_code == 404
        print("PASS: Delete nonexistent run returns 404")


# ─── Pipeline Stats Tests ─────────────────────────────────

class TestPipelineStats:
    """Test pipeline statistics endpoint (JWT auth)."""
    
    def test_get_pipeline_stats(self, auth_headers):
        """GET /api/pipeline/stats - aggregate statistics (JWT auth)."""
        response = requests.get(
            f"{BASE_URL}/api/pipeline/stats",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Get stats failed: {response.text}"
        
        data = response.json()
        assert "total_runs" in data
        assert "total_findings" in data
        assert "gate_results" in data
        assert "scan_types" in data
        assert "average_risk_score" in data
        assert "pass_rate" in data
        
        # Verify gate_results structure
        gate_results = data["gate_results"]
        assert "pass" in gate_results
        assert "fail" in gate_results
        assert "warn" in gate_results
        
        print(f"PASS: Got pipeline stats - {data['total_runs']} runs, {data['total_findings']} findings, {data['pass_rate']}% pass rate")


# ─── Cleanup Tests ────────────────────────────────────────

class TestCleanup:
    """Clean up test data."""
    
    def test_cleanup_test_data(self, auth_headers):
        """Clean up all TEST_ prefixed data."""
        # Clean up test pipeline runs
        runs_response = requests.get(f"{BASE_URL}/api/pipeline/runs", headers=auth_headers)
        if runs_response.status_code == 200:
            runs = runs_response.json()
            for run in runs:
                if run.get("pipeline_name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/pipeline/runs/{run['id']}", headers=auth_headers)
        
        # Clean up test API keys (revoke them)
        keys_response = requests.get(f"{BASE_URL}/api/pipeline/api-keys", headers=auth_headers)
        if keys_response.status_code == 200:
            keys = keys_response.json()
            for key in keys:
                if key.get("name", "").startswith("TEST_") and key.get("active"):
                    requests.delete(f"{BASE_URL}/api/pipeline/api-keys/{key['id']}", headers=auth_headers)
        
        # Clean up test OSCAL checklists
        checklists_response = requests.get(f"{BASE_URL}/api/ingestion/checklists", headers=auth_headers)
        if checklists_response.status_code == 200:
            checklists = checklists_response.json()
            for cl in checklists:
                if cl.get("source_type", "").startswith("oscal-") and "Sample OSCAL" in cl.get("name", ""):
                    requests.delete(f"{BASE_URL}/api/ingestion/checklists/{cl['id']}", headers=auth_headers)
        
        print("PASS: Cleaned up test data")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
