"""
Tenable VM Integration Tests - Iteration 18
Tests for Tenable.io integration with IronVision GRC platform:
- Settings management (save, get, delete API credentials)
- Demo mode sync (simulated vulnerability and compliance data)
- Dashboard endpoint (stats, vuln breakdown, compliance, control impact, assets)
- Findings endpoint with filters (finding_type, severity, status)
- Control evidence endpoint (NIST control mapping)
- Sync history endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo-admin@grc.com"
TEST_PASSWORD = "DemoAdmin123!"


class TestTenableAuth:
    """Test authentication for Tenable endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["token"]
    
    def test_settings_unauthorized(self):
        """Test that settings endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/tenable/settings")
        assert response.status_code in [401, 403], "Should require authentication"
    
    def test_sync_unauthorized(self):
        """Test that sync endpoint requires auth"""
        response = requests.post(f"{BASE_URL}/api/tenable/sync", json={"mode": "demo"})
        assert response.status_code in [401, 403], "Should require authentication"
    
    def test_dashboard_unauthorized(self):
        """Test that dashboard endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/tenable/dashboard")
        assert response.status_code in [401, 403], "Should require authentication"
    
    def test_findings_unauthorized(self):
        """Test that findings endpoint requires auth"""
        response = requests.get(f"{BASE_URL}/api/tenable/findings")
        assert response.status_code in [401, 403], "Should require authentication"


class TestTenableSettings:
    """Test Tenable settings management"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_get_settings_initial(self, auth_headers):
        """Test getting settings when not configured"""
        response = requests.get(f"{BASE_URL}/api/tenable/settings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "configured" in data
        # May or may not be configured from previous tests
    
    def test_save_settings(self, auth_headers):
        """Test saving Tenable API credentials"""
        response = requests.post(
            f"{BASE_URL}/api/tenable/settings",
            headers=auth_headers,
            json={
                "access_key": "test-access-key-12345678",
                "secret_key": "test-secret-key-abcdefgh"
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Tenable credentials saved"
        assert data["configured"] == True
    
    def test_get_settings_masked(self, auth_headers):
        """Test that settings returns masked keys"""
        response = requests.get(f"{BASE_URL}/api/tenable/settings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["configured"] == True
        assert "access_key_masked" in data
        # Key should be masked (first 8 chars...last 4 chars)
        assert "..." in data["access_key_masked"] or "****" in data["access_key_masked"]
    
    def test_delete_settings(self, auth_headers):
        """Test removing Tenable credentials"""
        response = requests.delete(f"{BASE_URL}/api/tenable/settings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Tenable credentials removed"
        
        # Verify deletion
        response = requests.get(f"{BASE_URL}/api/tenable/settings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["configured"] == False


class TestTenableDemoSync:
    """Test Tenable demo mode sync"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        token = response.json()["token"]
        return {"Authorization": f"Bearer {token}"}
    
    def test_sync_demo_mode(self, auth_headers):
        """Test demo mode sync loads simulated data"""
        response = requests.post(
            f"{BASE_URL}/api/tenable/sync",
            headers=auth_headers,
            json={"mode": "demo"}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify response structure
        assert data["mode"] == "demo"
        assert "message" in data
        assert "vulns_processed" in data
        assert "compliance_processed" in data
        assert "controls_updated" in data
        
        # Verify expected counts (10 vulns, 12 compliance checks)
        assert data["vulns_processed"] == 10, f"Expected 10 vulns, got {data['vulns_processed']}"
        assert data["compliance_processed"] == 12, f"Expected 12 compliance, got {data['compliance_processed']}"
        assert data["controls_updated"] > 0, "Should have mapped controls"
    
    def test_sync_auto_mode_no_keys(self, auth_headers):
        """Test auto mode uses demo when no keys configured"""
        # First ensure no keys are configured
        requests.delete(f"{BASE_URL}/api/tenable/settings", headers=auth_headers)
        
        response = requests.post(
            f"{BASE_URL}/api/tenable/sync",
            headers=auth_headers,
            json={"mode": "auto"}
        )
        assert response.status_code == 200
        data = response.json()
        # Should fall back to demo mode
        assert data["mode"] == "demo"
    
    def test_sync_live_mode_no_keys_fails(self, auth_headers):
        """Test live mode fails when no keys configured"""
        # Ensure no keys
        requests.delete(f"{BASE_URL}/api/tenable/settings", headers=auth_headers)
        
        response = requests.post(
            f"{BASE_URL}/api/tenable/sync",
            headers=auth_headers,
            json={"mode": "live"}
        )
        assert response.status_code == 400
        data = response.json()
        assert "not configured" in data["detail"].lower()


class TestTenableDashboard:
    """Test Tenable dashboard endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers and ensure demo data exists"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        token = response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Ensure demo data is loaded
        requests.post(f"{BASE_URL}/api/tenable/sync", headers=headers, json={"mode": "demo"})
        return headers
    
    def test_dashboard_structure(self, auth_headers):
        """Test dashboard returns expected structure"""
        response = requests.get(f"{BASE_URL}/api/tenable/dashboard", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify top-level fields
        assert "total_findings" in data
        assert "vulnerabilities" in data
        assert "compliance" in data
        assert "controls_impacted" in data
        assert "control_impact" in data
        assert "assets_scanned" in data
        assert "assets" in data
        assert "sync_history" in data
    
    def test_dashboard_vuln_stats(self, auth_headers):
        """Test vulnerability statistics"""
        response = requests.get(f"{BASE_URL}/api/tenable/dashboard", headers=auth_headers)
        data = response.json()
        
        vulns = data["vulnerabilities"]
        assert "total" in vulns
        assert "by_severity" in vulns
        assert "by_state" in vulns
        assert "open_critical" in vulns
        
        # Verify severity breakdown
        by_sev = vulns["by_severity"]
        assert "critical" in by_sev
        assert "high" in by_sev
        assert "medium" in by_sev
        
        # Verify state breakdown
        by_state = vulns["by_state"]
        assert "open" in by_state
        assert "reopened" in by_state
        assert "fixed" in by_state
    
    def test_dashboard_compliance_stats(self, auth_headers):
        """Test compliance statistics"""
        response = requests.get(f"{BASE_URL}/api/tenable/dashboard", headers=auth_headers)
        data = response.json()
        
        comp = data["compliance"]
        assert "total" in comp
        assert "passed" in comp
        assert "failed" in comp
        assert "pass_rate" in comp
        
        # Pass rate should be a percentage
        assert 0 <= comp["pass_rate"] <= 100
    
    def test_dashboard_control_impact(self, auth_headers):
        """Test control impact data"""
        response = requests.get(f"{BASE_URL}/api/tenable/dashboard", headers=auth_headers)
        data = response.json()
        
        assert data["controls_impacted"] > 0
        assert isinstance(data["control_impact"], dict)
        
        # Each control should have compliant/non_compliant/partial counts
        for ctrl_id, counts in data["control_impact"].items():
            assert "compliant" in counts
            assert "non_compliant" in counts
    
    def test_dashboard_assets(self, auth_headers):
        """Test assets data"""
        response = requests.get(f"{BASE_URL}/api/tenable/dashboard", headers=auth_headers)
        data = response.json()
        
        assert data["assets_scanned"] > 0
        assert isinstance(data["assets"], list)
        assert len(data["assets"]) > 0


class TestTenableFindings:
    """Test Tenable findings endpoint with filters"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers and ensure demo data exists"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        token = response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Ensure demo data is loaded
        requests.post(f"{BASE_URL}/api/tenable/sync", headers=headers, json={"mode": "demo"})
        return headers
    
    def test_list_all_findings(self, auth_headers):
        """Test listing all findings"""
        response = requests.get(f"{BASE_URL}/api/tenable/findings", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Verify finding structure
        finding = data[0]
        assert "id" in finding
        assert "finding_type" in finding
        assert "title" in finding
        assert "control_ids" in finding
        assert "compliance_status" in finding
    
    def test_filter_vulnerabilities(self, auth_headers):
        """Test filtering by finding_type=vulnerability"""
        response = requests.get(
            f"{BASE_URL}/api/tenable/findings?finding_type=vulnerability",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) == 10, f"Expected 10 vulns, got {len(data)}"
        
        # All should be vulnerabilities
        for finding in data:
            assert finding["finding_type"] == "vulnerability"
            assert "severity" in finding
            assert "state" in finding
            assert "tenable_plugin_id" in finding
    
    def test_filter_compliance(self, auth_headers):
        """Test filtering by finding_type=compliance"""
        response = requests.get(
            f"{BASE_URL}/api/tenable/findings?finding_type=compliance",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) == 12, f"Expected 12 compliance checks, got {len(data)}"
        
        # All should be compliance checks
        for finding in data:
            assert finding["finding_type"] == "compliance"
            assert "status" in finding
            assert "expected_value" in finding
            assert "actual_value" in finding
    
    def test_filter_by_severity(self, auth_headers):
        """Test filtering by severity"""
        response = requests.get(
            f"{BASE_URL}/api/tenable/findings?severity=critical",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # All should be critical severity
        for finding in data:
            assert finding.get("severity") == "critical"
    
    def test_vuln_has_cves(self, auth_headers):
        """Test that vulnerabilities have CVE references"""
        response = requests.get(
            f"{BASE_URL}/api/tenable/findings?finding_type=vulnerability",
            headers=auth_headers
        )
        data = response.json()
        
        # At least some vulns should have CVEs
        vulns_with_cves = [v for v in data if v.get("cves") and len(v["cves"]) > 0]
        assert len(vulns_with_cves) > 0, "Expected some vulns to have CVE references"
    
    def test_vuln_has_asset_info(self, auth_headers):
        """Test that vulnerabilities have asset information"""
        response = requests.get(
            f"{BASE_URL}/api/tenable/findings?finding_type=vulnerability",
            headers=auth_headers
        )
        data = response.json()
        
        for vuln in data:
            assert "asset_hostname" in vuln
            assert vuln["asset_hostname"], "Asset hostname should not be empty"


class TestTenableControlEvidence:
    """Test control evidence endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers and ensure demo data exists"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        token = response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Ensure demo data is loaded
        requests.post(f"{BASE_URL}/api/tenable/sync", headers=headers, json={"mode": "demo"})
        return headers
    
    def test_control_evidence_si2(self, auth_headers):
        """Test getting evidence for SI-2 (Flaw Remediation)"""
        response = requests.get(
            f"{BASE_URL}/api/tenable/control-evidence/SI-2",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["control_id"] == "SI-2"
        assert "total_evidence" in data
        assert "vulnerabilities" in data
        assert "compliance_checks" in data
        assert "summary" in data
        
        # SI-2 should have vulnerability evidence (critical/high vulns map to SI-2)
        assert data["total_evidence"] > 0
        assert len(data["vulnerabilities"]) > 0
    
    def test_control_evidence_ra5(self, auth_headers):
        """Test getting evidence for RA-5 (Vulnerability Scanning)"""
        response = requests.get(
            f"{BASE_URL}/api/tenable/control-evidence/RA-5",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["control_id"] == "RA-5"
        assert data["total_evidence"] > 0
    
    def test_control_evidence_ia5(self, auth_headers):
        """Test getting evidence for IA-5 (Authenticator Management)"""
        response = requests.get(
            f"{BASE_URL}/api/tenable/control-evidence/IA-5",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["control_id"] == "IA-5"
        # IA-5 maps to password-related compliance checks
        assert len(data["compliance_checks"]) > 0
    
    def test_control_evidence_summary(self, auth_headers):
        """Test control evidence summary structure"""
        response = requests.get(
            f"{BASE_URL}/api/tenable/control-evidence/SI-2",
            headers=auth_headers
        )
        data = response.json()
        
        summary = data["summary"]
        assert "vuln_open" in summary
        assert "vuln_fixed" in summary
        assert "compliance_passed" in summary
        assert "compliance_failed" in summary
    
    def test_control_evidence_empty(self, auth_headers):
        """Test control with no evidence returns empty"""
        response = requests.get(
            f"{BASE_URL}/api/tenable/control-evidence/XX-99",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        assert data["control_id"] == "XX-99"
        assert data["total_evidence"] == 0


class TestTenableSyncHistory:
    """Test sync history endpoint"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        token = response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Run a sync to ensure history exists
        requests.post(f"{BASE_URL}/api/tenable/sync", headers=headers, json={"mode": "demo"})
        return headers
    
    def test_sync_history(self, auth_headers):
        """Test getting sync history"""
        response = requests.get(f"{BASE_URL}/api/tenable/sync-history", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        
        assert isinstance(data, list)
        assert len(data) > 0
        
        # Verify run structure
        run = data[0]
        assert "id" in run
        assert "mode" in run
        assert "vulns_processed" in run
        assert "compliance_processed" in run
        assert "controls_updated" in run
        assert "created_at" in run
    
    def test_sync_history_unauthorized(self):
        """Test sync history requires auth"""
        response = requests.get(f"{BASE_URL}/api/tenable/sync-history")
        assert response.status_code in [401, 403]


class TestTenableNISTMappings:
    """Test NIST control mappings are correct"""
    
    @pytest.fixture(scope="class")
    def auth_headers(self):
        """Get auth headers and ensure demo data exists"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        token = response.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Ensure demo data is loaded
        requests.post(f"{BASE_URL}/api/tenable/sync", headers=headers, json={"mode": "demo"})
        return headers
    
    def test_critical_vuln_maps_to_si2_ra5_cm6(self, auth_headers):
        """Test critical vulns map to SI-2, RA-5, CM-6"""
        response = requests.get(
            f"{BASE_URL}/api/tenable/findings?finding_type=vulnerability&severity=critical",
            headers=auth_headers
        )
        data = response.json()
        
        for vuln in data:
            if vuln.get("state") in ("open", "reopened"):
                # Critical open vulns should map to SI-2, RA-5, CM-6
                assert "SI-2" in vuln["control_ids"], f"Critical vuln should map to SI-2: {vuln['title']}"
                assert "RA-5" in vuln["control_ids"], f"Critical vuln should map to RA-5: {vuln['title']}"
                assert "CM-6" in vuln["control_ids"], f"Critical vuln should map to CM-6: {vuln['title']}"
                assert vuln["compliance_status"] == "non_compliant"
    
    def test_fixed_vuln_is_compliant(self, auth_headers):
        """Test fixed vulns are marked compliant"""
        response = requests.get(
            f"{BASE_URL}/api/tenable/findings?finding_type=vulnerability",
            headers=auth_headers
        )
        data = response.json()
        
        fixed_vulns = [v for v in data if v.get("state") == "fixed"]
        assert len(fixed_vulns) > 0, "Should have some fixed vulns"
        
        for vuln in fixed_vulns:
            assert vuln["compliance_status"] == "compliant", f"Fixed vuln should be compliant: {vuln['title']}"
    
    def test_compliance_check_keyword_mapping(self, auth_headers):
        """Test compliance checks map based on keywords"""
        response = requests.get(
            f"{BASE_URL}/api/tenable/findings?finding_type=compliance",
            headers=auth_headers
        )
        data = response.json()
        
        for check in data:
            title_lower = check["title"].lower()
            control_ids = check["control_ids"]
            
            # Password checks should map to IA-5
            if "password" in title_lower:
                assert "IA-5" in control_ids, f"Password check should map to IA-5: {check['title']}"
            
            # MFA checks should map to IA-2
            if "mfa" in title_lower or "multi-factor" in title_lower:
                assert "IA-2" in control_ids, f"MFA check should map to IA-2: {check['title']}"
            
            # Audit/log checks should map to AU-2
            if "audit" in title_lower or "log" in title_lower:
                assert any(c.startswith("AU-") for c in control_ids), f"Audit check should map to AU-*: {check['title']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
