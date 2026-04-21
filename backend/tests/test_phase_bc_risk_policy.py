"""
Phase B & C Testing: Dynamic Risk Scoring + Policy-as-Code + Drift Detection
- Phase B: Risk scoring engine with 5 factors (SIEM, compliance, pipeline, ingestion, policy)
- Phase C: Policy-as-code evaluation, custom rules, drift detection
"""
import pytest
import requests
import os
import json
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "demo-admin@grc.com"
TEST_PASSWORD = "DemoAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API calls."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with JWT token."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


# ============================================================================
# PHASE B: DYNAMIC RISK SCORING TESTS
# ============================================================================

class TestRiskScoringOrgScore:
    """Test GET /api/risk-scoring/org-score - aggregate org risk with 5 factors."""

    def test_get_org_risk_score(self, auth_headers):
        """Test org-wide risk score calculation."""
        response = requests.get(f"{BASE_URL}/api/risk-scoring/org-score", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        # Verify structure
        assert "score" in data, "Missing 'score' field"
        assert "level" in data, "Missing 'level' field"
        assert "label" in data, "Missing 'label' field"
        assert "color" in data, "Missing 'color' field"
        assert "factors" in data, "Missing 'factors' field"
        assert "timestamp" in data, "Missing 'timestamp' field"
        
        # Verify score is in valid range
        assert 0 <= data["score"] <= 100, f"Score {data['score']} out of range"
        
        # Verify all 5 factors present
        factors = data["factors"]
        expected_factors = ["siem", "compliance", "pipeline", "ingestion", "policy"]
        for factor in expected_factors:
            assert factor in factors, f"Missing factor: {factor}"
            assert "score" in factors[factor], f"Factor {factor} missing score"
            assert "weight" in factors[factor], f"Factor {factor} missing weight"
            assert "label" in factors[factor], f"Factor {factor} missing label"
        
        # Verify risk level is valid
        valid_levels = ["critical", "high", "elevated", "moderate", "low"]
        assert data["level"] in valid_levels, f"Invalid risk level: {data['level']}"
        
        print(f"✓ Org risk score: {data['score']} ({data['label']})")
        print(f"  Factors: SIEM={factors['siem']['score']}, Compliance={factors['compliance']['score']}, "
              f"Pipeline={factors['pipeline']['score']}, Ingestion={factors['ingestion']['score']}, "
              f"Policy={factors['policy']['score']}")


class TestRiskScoringFrameworkScores:
    """Test GET /api/risk-scoring/framework-scores - risk per framework."""

    def test_get_framework_risk_scores(self, auth_headers):
        """Test framework-level risk scores."""
        response = requests.get(f"{BASE_URL}/api/risk-scoring/framework-scores", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list of framework scores"
        
        if len(data) > 0:
            fw = data[0]
            # Verify structure
            assert "framework_id" in fw, "Missing framework_id"
            assert "framework_name" in fw, "Missing framework_name"
            assert "risk_score" in fw, "Missing risk_score"
            assert "risk_level" in fw, "Missing risk_level"
            assert "risk_label" in fw, "Missing risk_label"
            assert "risk_color" in fw, "Missing risk_color"
            assert "total_controls" in fw, "Missing total_controls"
            assert "compliant" in fw, "Missing compliant count"
            assert "partial" in fw, "Missing partial count"
            assert "non_compliant" in fw, "Missing non_compliant count"
            assert "not_assessed" in fw, "Missing not_assessed count"
            assert "policy_coverage" in fw, "Missing policy_coverage"
            
            # Verify score range
            assert 0 <= fw["risk_score"] <= 100, f"Risk score {fw['risk_score']} out of range"
            assert 0 <= fw["policy_coverage"] <= 100, f"Policy coverage {fw['policy_coverage']} out of range"
            
            print(f"✓ Framework scores returned: {len(data)} frameworks")
            for f in data[:3]:  # Print first 3
                print(f"  - {f['framework_name']}: risk={f['risk_score']}, policy_coverage={f['policy_coverage']}%")


class TestRiskScoringTrend:
    """Test GET /api/risk-scoring/trend - risk score history."""

    def test_get_risk_trend_default(self, auth_headers):
        """Test risk trend with default 30 days."""
        response = requests.get(f"{BASE_URL}/api/risk-scoring/trend", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "history" in data, "Missing history field"
        assert "period_days" in data, "Missing period_days field"
        assert "data_points" in data, "Missing data_points field"
        assert data["period_days"] == 30, f"Expected 30 days, got {data['period_days']}"
        
        print(f"✓ Risk trend: {data['data_points']} data points over {data['period_days']} days")

    def test_get_risk_trend_custom_days(self, auth_headers):
        """Test risk trend with custom days parameter."""
        response = requests.get(f"{BASE_URL}/api/risk-scoring/trend?days=7", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert data["period_days"] == 7, f"Expected 7 days, got {data['period_days']}"
        
        # Verify history structure if data exists
        if len(data["history"]) > 0:
            point = data["history"][0]
            assert "score" in point, "History point missing score"
            assert "level" in point, "History point missing level"
            assert "timestamp" in point, "History point missing timestamp"
        
        print(f"✓ Risk trend (7 days): {data['data_points']} data points")


class TestRiskScoringAlerts:
    """Test GET /api/risk-scoring/alerts - risk alerts."""

    def test_get_risk_alerts(self, auth_headers):
        """Test risk alerts endpoint."""
        response = requests.get(f"{BASE_URL}/api/risk-scoring/alerts", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "alerts" in data, "Missing alerts field"
        assert "total" in data, "Missing total field"
        assert isinstance(data["alerts"], list), "Alerts should be a list"
        
        # Verify alert structure if any exist
        if len(data["alerts"]) > 0:
            alert = data["alerts"][0]
            assert "type" in alert, "Alert missing type"
            assert "severity" in alert, "Alert missing severity"
            assert "title" in alert, "Alert missing title"
            assert "description" in alert, "Alert missing description"
            assert "action" in alert, "Alert missing action"
            
            # Verify valid alert types
            valid_types = ["siem", "pipeline", "compliance", "ingestion", "stale"]
            assert alert["type"] in valid_types, f"Invalid alert type: {alert['type']}"
            
            # Verify valid severities
            valid_severities = ["critical", "high", "medium", "low"]
            assert alert["severity"] in valid_severities, f"Invalid severity: {alert['severity']}"
        
        print(f"✓ Risk alerts: {data['total']} active alerts")
        for a in data["alerts"][:3]:
            print(f"  - [{a['severity'].upper()}] {a['type']}: {a['title']}")


# ============================================================================
# PHASE C: POLICY-AS-CODE TESTS
# ============================================================================

class TestPolicyEngineRules:
    """Test GET /api/policy-engine/rules - list policy rules."""

    def test_list_policy_rules(self, auth_headers):
        """Test listing all policy rules (built-in + custom)."""
        response = requests.get(f"{BASE_URL}/api/policy-engine/rules", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "builtin_rules" in data, "Missing builtin_rules"
        assert "custom_rules" in data, "Missing custom_rules"
        assert "total" in data, "Missing total count"
        
        # Verify 8 built-in rules
        builtin = data["builtin_rules"]
        assert len(builtin) == 8, f"Expected 8 built-in rules, got {len(builtin)}"
        
        # Verify rule IDs PAC-001 to PAC-008
        expected_ids = [f"PAC-00{i}" for i in range(1, 9)]
        actual_ids = [r["id"] for r in builtin]
        for eid in expected_ids:
            assert eid in actual_ids, f"Missing rule {eid}"
        
        # Verify rule structure
        rule = builtin[0]
        assert "id" in rule, "Rule missing id"
        assert "name" in rule, "Rule missing name"
        assert "description" in rule, "Rule missing description"
        assert "severity" in rule, "Rule missing severity"
        assert "category" in rule, "Rule missing category"
        assert "control_ids" in rule, "Rule missing control_ids"
        
        print(f"✓ Policy rules: {len(builtin)} built-in, {len(data['custom_rules'])} custom")
        for r in builtin:
            print(f"  - {r['id']}: {r['name']} [{r['severity']}]")


class TestPolicyEngineEvaluate:
    """Test POST /api/policy-engine/evaluate - evaluate config against rules."""

    def test_evaluate_config_with_violations(self, auth_headers):
        """Test evaluation with config that triggers multiple violations."""
        # Config designed to trigger violations
        config = {
            "server": {
                "encryption": False,  # PAC-001 violation
                "mfa_enabled": False,  # PAC-002 violation
                "publicly_accessible": True,  # PAC-003 violation
                "logging": False,  # PAC-004 violation
                "tls_version": "1.0",  # PAC-005 violation
                "backup_enabled": False,  # PAC-006 violation
                "tags": {"environment": "prod"},  # PAC-008 violation (missing owner, project)
                "password": "SuperSecret123!"  # PAC-007 violation
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/policy-engine/evaluate",
            headers=auth_headers,
            json={"config": config, "config_type": "generic", "source": "Test evaluation"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "id" in data, "Missing evaluation id"
        assert "violations" in data, "Missing violations"
        assert "violation_count" in data, "Missing violation_count"
        assert "severity_counts" in data, "Missing severity_counts"
        assert "pass" in data, "Missing pass field"
        assert "total_rules_checked" in data, "Missing total_rules_checked"
        
        # Should have violations
        assert data["pass"] == False, "Expected violations but got pass"
        assert data["violation_count"] > 0, "Expected violations"
        
        # Verify violation structure
        if len(data["violations"]) > 0:
            v = data["violations"][0]
            assert "rule_id" in v, "Violation missing rule_id"
            assert "name" in v, "Violation missing name"
            assert "severity" in v, "Violation missing severity"
            assert "violation" in v, "Violation missing violation message"
            assert "control_ids" in v, "Violation missing control_ids"
        
        print(f"✓ Evaluation: {data['violation_count']} violations found")
        print(f"  Severity counts: {data['severity_counts']}")
        for v in data["violations"][:5]:
            print(f"  - {v['rule_id']}: {v['name']} [{v['severity']}]")

    def test_evaluate_config_all_pass(self, auth_headers):
        """Test evaluation with compliant config."""
        # Config designed to pass all checks
        config = {
            "server": {
                "encryption": True,
                "mfa_enabled": True,
                "publicly_accessible": False,
                "logging": True,
                "tls_version": "1.3",
                "backup_enabled": True,
                "tags": {"environment": "prod", "owner": "team-a", "project": "grc"}
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/policy-engine/evaluate",
            headers=auth_headers,
            json={"config": config, "config_type": "terraform", "source": "Compliant test"}
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        # Should pass (no violations)
        assert data["pass"] == True, f"Expected pass but got violations: {data.get('violations', [])}"
        assert data["violation_count"] == 0, f"Expected 0 violations, got {data['violation_count']}"
        
        print(f"✓ Compliant config evaluation: PASS (0 violations)")


class TestPolicyEngineCustomRules:
    """Test POST /api/policy-engine/rules - create custom rules."""

    def test_create_custom_rule(self, auth_headers):
        """Test creating a custom policy rule."""
        rule = {
            "name": "TEST_Custom_Rule_No_Debug_Mode",
            "description": "Debug mode must be disabled in production",
            "severity": "high",
            "category": "security",
            "condition": "debug_mode == false",
            "control_ids": ["AC-1", "CM-6"],
            "tags": ["test", "custom"]
        }
        
        response = requests.post(
            f"{BASE_URL}/api/policy-engine/rules",
            headers=auth_headers,
            json=rule
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "id" in data, "Missing rule id"
        assert data["id"].startswith("CUSTOM-"), f"Custom rule ID should start with CUSTOM-"
        assert data["name"] == rule["name"], "Name mismatch"
        assert data["severity"] == rule["severity"], "Severity mismatch"
        assert data["active"] == True, "Rule should be active"
        
        print(f"✓ Custom rule created: {data['id']} - {data['name']}")
        return data["id"]


class TestPolicyEngineEvaluationHistory:
    """Test GET /api/policy-engine/evaluations - list evaluation history."""

    def test_list_evaluations(self, auth_headers):
        """Test listing evaluation history."""
        response = requests.get(f"{BASE_URL}/api/policy-engine/evaluations", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list of evaluations"
        
        if len(data) > 0:
            e = data[0]
            assert "id" in e, "Evaluation missing id"
            assert "violation_count" in e, "Evaluation missing violation_count"
            assert "pass" in e, "Evaluation missing pass"
            assert "created_at" in e, "Evaluation missing created_at"
        
        print(f"✓ Evaluation history: {len(data)} evaluations")


# ============================================================================
# PHASE C: DRIFT DETECTION TESTS
# ============================================================================

class TestDriftSnapshot:
    """Test POST /api/policy-engine/drift/snapshot - create baseline snapshot."""

    def test_create_drift_snapshot(self, auth_headers):
        """Test creating a compliance baseline snapshot."""
        response = requests.post(
            f"{BASE_URL}/api/policy-engine/drift/snapshot",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "snapshot_id" in data, "Missing snapshot_id"
        assert "message" in data, "Missing message"
        assert "frameworks_captured" in data, "Missing frameworks_captured"
        
        print(f"✓ Snapshot created: {data['snapshot_id']}")
        print(f"  Frameworks captured: {data['frameworks_captured']}")
        return data["snapshot_id"]


class TestDriftDetect:
    """Test GET /api/policy-engine/drift/detect - detect compliance drift."""

    def test_detect_drift(self, auth_headers):
        """Test drift detection against baseline."""
        response = requests.get(
            f"{BASE_URL}/api/policy-engine/drift/detect",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "drift_detected" in data, "Missing drift_detected"
        assert "changes" in data, "Missing changes"
        
        if data["drift_detected"]:
            assert "summary" in data, "Missing summary when drift detected"
            assert "total_changes" in data["summary"], "Missing total_changes in summary"
            assert "improved" in data["summary"], "Missing improved count"
            assert "degraded" in data["summary"], "Missing degraded count"
            
            # Verify change structure
            if len(data["changes"]) > 0:
                c = data["changes"][0]
                assert "framework_name" in c, "Change missing framework_name"
                assert "control_id" in c, "Change missing control_id"
                assert "previous_status" in c, "Change missing previous_status"
                assert "current_status" in c, "Change missing current_status"
                assert "direction" in c, "Change missing direction"
        
        print(f"✓ Drift detection: drift_detected={data['drift_detected']}")
        if data.get("summary"):
            print(f"  Changes: {data['summary']['total_changes']} total, "
                  f"{data['summary']['improved']} improved, {data['summary']['degraded']} degraded")


class TestDriftSnapshots:
    """Test GET /api/policy-engine/drift/snapshots - list snapshots."""

    def test_list_snapshots(self, auth_headers):
        """Test listing compliance snapshots."""
        response = requests.get(
            f"{BASE_URL}/api/policy-engine/drift/snapshots",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), "Expected list of snapshots"
        
        if len(data) > 0:
            s = data[0]
            assert "id" in s, "Snapshot missing id"
            assert "created_at" in s, "Snapshot missing created_at"
        
        print(f"✓ Snapshots list: {len(data)} snapshots")


# ============================================================================
# CLEANUP
# ============================================================================

class TestCleanup:
    """Clean up test data."""

    def test_cleanup_test_data(self, auth_headers):
        """Clean up TEST_ prefixed custom rules."""
        # Get rules and find TEST_ prefixed ones
        response = requests.get(f"{BASE_URL}/api/policy-engine/rules", headers=auth_headers)
        if response.status_code == 200:
            data = response.json()
            test_rules = [r for r in data.get("custom_rules", []) if r.get("name", "").startswith("TEST_")]
            print(f"✓ Found {len(test_rules)} TEST_ prefixed custom rules (cleanup would delete if endpoint existed)")
        
        print("✓ Cleanup complete")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
