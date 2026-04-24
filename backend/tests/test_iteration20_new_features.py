"""
Iteration 20: Testing 6 New Features for IronVision AI
1. Auto-Remediation Code Generation
2. Expanded RBAC (5 roles)
3. OSCAL SSP Export
4. Natural Language Compliance Interrogation
5. Predictive Risk Forecasting
6. Third-Party Risk Management (TPRM)
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://compliance-ingestion.preview.emergentagent.com')

# Test credentials
ADMIN_EMAIL = "demo-admin@grc.com"
ADMIN_PASSWORD = "DemoAdmin123!"
USER_EMAIL = "demo-user@grc.com"
USER_PASSWORD = "DemoUser123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin authentication token."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def user_token():
    """Get regular user authentication token."""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": USER_EMAIL,
        "password": USER_PASSWORD
    })
    assert response.status_code == 200, f"User login failed: {response.text}"
    return response.json()["token"]


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    """Headers with admin auth."""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture(scope="module")
def user_headers(user_token):
    """Headers with user auth."""
    return {"Authorization": f"Bearer {user_token}", "Content-Type": "application/json"}


# ============================================================================
# 1. AUTO-REMEDIATION CODE GENERATION TESTS
# ============================================================================

class TestRemediationCodeGeneration:
    """Test auto-remediation code generation endpoints."""

    def test_remediation_generate_unauthorized(self):
        """Test remediation generate without auth returns 401/403."""
        response = requests.post(f"{BASE_URL}/api/remediation/generate", json={
            "title": "Test finding"
        })
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_remediation_generate_terraform(self, admin_headers):
        """Test generating Terraform remediation code for S3 encryption finding."""
        response = requests.post(f"{BASE_URL}/api/remediation/generate", json={
            "title": "Ensure S3 bucket encryption is enabled",
            "description": "S3 bucket lacks server-side encryption",
            "format": "terraform"
        }, headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert "remediation" in data
        assert data["remediation"]["format"] == "terraform"
        assert "template_key" in data
        assert data["template_key"] == "encryption_at_rest"
        assert "template_code" in data["remediation"] or "ai_code" in data["remediation"]
        print(f"Generated Terraform code for encryption finding, template: {data['template_key']}")

    def test_remediation_generate_cloudformation(self, admin_headers):
        """Test generating CloudFormation remediation code for MFA finding."""
        response = requests.post(f"{BASE_URL}/api/remediation/generate", json={
            "title": "Enforce MFA for all IAM users",
            "description": "Multi-factor authentication not enforced",
            "format": "cloudformation"
        }, headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["template_key"] == "mfa_enforcement"
        assert data["remediation"]["format"] == "cloudformation"
        print(f"Generated CloudFormation code for MFA finding")

    def test_remediation_generate_kubernetes(self, admin_headers):
        """Test generating Kubernetes YAML for TLS finding."""
        response = requests.post(f"{BASE_URL}/api/remediation/generate", json={
            "title": "Enable TLS for ingress",
            "description": "TLS not configured for ingress controller",
            "format": "kubernetes"
        }, headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["template_key"] == "tls_enforcement"
        assert data["remediation"]["format"] == "kubernetes"
        print(f"Generated Kubernetes YAML for TLS finding")

    def test_remediation_generate_requires_title(self, admin_headers):
        """Test that remediation requires title or finding_id."""
        response = requests.post(f"{BASE_URL}/api/remediation/generate", json={
            "format": "terraform"
        }, headers=admin_headers)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"

    def test_remediation_templates_list(self, admin_headers):
        """Test listing available remediation templates."""
        response = requests.get(f"{BASE_URL}/api/remediation/templates", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        templates = response.json()
        assert isinstance(templates, list)
        assert len(templates) >= 5  # At least 5 templates expected
        template_keys = [t["key"] for t in templates]
        assert "encryption_at_rest" in template_keys
        assert "mfa_enforcement" in template_keys
        print(f"Found {len(templates)} remediation templates: {template_keys}")

    def test_remediation_history(self, admin_headers):
        """Test listing remediation history."""
        response = requests.get(f"{BASE_URL}/api/remediation/history", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        history = response.json()
        assert isinstance(history, list)
        print(f"Remediation history has {len(history)} entries")


# ============================================================================
# 2. EXPANDED RBAC TESTS
# ============================================================================

class TestExpandedRBAC:
    """Test expanded RBAC with 5 roles."""

    def test_rbac_roles_list(self, admin_headers):
        """Test listing all 5 roles with permissions."""
        response = requests.get(f"{BASE_URL}/api/rbac/roles", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        roles = response.json()
        
        # Verify all 5 roles exist
        expected_roles = ["admin", "auditor", "system_owner", "remediation_engineer", "viewer"]
        for role in expected_roles:
            assert role in roles, f"Missing role: {role}"
            assert "label" in roles[role]
            assert "description" in roles[role]
            assert "permissions" in roles[role]
            assert "permission_count" in roles[role]
        
        # Admin should have most permissions
        assert roles["admin"]["permission_count"] > roles["viewer"]["permission_count"]
        print(f"Verified 5 roles: {list(roles.keys())}")
        print(f"Admin has {roles['admin']['permission_count']} permissions, Viewer has {roles['viewer']['permission_count']}")

    def test_rbac_users_list(self, admin_headers):
        """Test listing users with their roles."""
        response = requests.get(f"{BASE_URL}/api/rbac/users", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        users = response.json()
        assert isinstance(users, list)
        
        # Find demo admin and demo user
        admin_found = False
        user_found = False
        for u in users:
            assert "id" in u
            assert "email" in u
            assert "role" in u
            if u["email"] == ADMIN_EMAIL:
                admin_found = True
                assert u["role"] == "admin"
            if u["email"] == USER_EMAIL:
                user_found = True
        
        assert admin_found, "Demo admin not found in users list"
        print(f"Found {len(users)} users with roles")

    def test_rbac_my_permissions(self, admin_headers):
        """Test getting current user's permissions."""
        response = requests.get(f"{BASE_URL}/api/rbac/my-permissions", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "user_id" in data
        assert "role" in data
        assert "label" in data
        assert "permissions" in data
        assert data["role"] == "admin"
        assert "users.assign_roles" in data["permissions"]
        print(f"Admin has {len(data['permissions'])} permissions")

    def test_rbac_my_permissions_viewer(self, user_headers):
        """Test viewer user's permissions."""
        response = requests.get(f"{BASE_URL}/api/rbac/my-permissions", headers=user_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert data["role"] == "viewer"
        assert "users.assign_roles" not in data["permissions"]
        print(f"Viewer has {len(data['permissions'])} permissions")

    def test_rbac_assign_role_admin_only(self, user_headers, admin_headers):
        """Test that only admin can assign roles."""
        # Get a user to try to change
        users_response = requests.get(f"{BASE_URL}/api/rbac/users", headers=admin_headers)
        users = users_response.json()
        
        # Find demo user
        demo_user = next((u for u in users if u["email"] == USER_EMAIL), None)
        if demo_user:
            # Try to assign role as non-admin (should fail)
            response = requests.put(f"{BASE_URL}/api/rbac/assign", json={
                "user_id": demo_user["id"],
                "role": "auditor"
            }, headers=user_headers)
            assert response.status_code == 403, f"Expected 403, got {response.status_code}"
            print("Verified non-admin cannot assign roles")

    def test_rbac_assign_invalid_role(self, admin_headers):
        """Test assigning invalid role returns error."""
        response = requests.put(f"{BASE_URL}/api/rbac/assign", json={
            "user_id": "some-user-id",
            "role": "invalid_role"
        }, headers=admin_headers)
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"


# ============================================================================
# 3. OSCAL SSP EXPORT TESTS
# ============================================================================

class TestOSCALSSPExport:
    """Test OSCAL System Security Plan export."""

    def test_oscal_ssp_export_unauthorized(self):
        """Test SSP export without auth returns 401/403."""
        response = requests.get(f"{BASE_URL}/api/oscal/export/ssp")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_oscal_ssp_export_success(self, admin_headers):
        """Test full SSP export returns valid OSCAL structure."""
        response = requests.get(f"{BASE_URL}/api/oscal/export/ssp", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        ssp = response.json()
        
        # Verify main SSP structure
        assert "system-security-plan" in ssp
        ssp_data = ssp["system-security-plan"]
        
        # Verify metadata
        assert "metadata" in ssp_data
        assert "title" in ssp_data["metadata"]
        assert "oscal-version" in ssp_data["metadata"]
        assert ssp_data["metadata"]["oscal-version"] == "1.2.1"
        
        # Verify system-characteristics
        assert "system-characteristics" in ssp_data
        assert "system-name" in ssp_data["system-characteristics"]
        assert "description" in ssp_data["system-characteristics"]
        
        # Verify control-implementation
        assert "control-implementation" in ssp_data
        assert "implemented-requirements" in ssp_data["control-implementation"]
        
        # Verify back-matter
        assert "back-matter" in ssp_data
        
        print(f"SSP exported successfully with {len(ssp_data['control-implementation']['implemented-requirements'])} implemented requirements")

    def test_oscal_ssp_has_poam_section(self, admin_headers):
        """Test SSP includes POA&M section if entries exist."""
        response = requests.get(f"{BASE_URL}/api/oscal/export/ssp", headers=admin_headers)
        assert response.status_code == 200
        ssp = response.json()
        
        # POA&M section is optional but should be present if entries exist
        if "plan-of-action-and-milestones" in ssp:
            poam = ssp["plan-of-action-and-milestones"]
            assert "metadata" in poam
            assert "poam-items" in poam
            print(f"SSP includes POA&M section with {len(poam['poam-items'])} items")
        else:
            print("No POA&M section in SSP (no entries)")


# ============================================================================
# 4. NATURAL LANGUAGE COMPLIANCE INTERROGATION TESTS
# ============================================================================

class TestComplianceInterrogation:
    """Test natural language compliance interrogation."""

    def test_interrogation_unauthorized(self):
        """Test interrogation without auth returns 401/403."""
        response = requests.post(f"{BASE_URL}/api/interrogate/ask", json={
            "question": "What is our compliance status?"
        })
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_interrogation_ask_question(self, admin_headers):
        """Test asking a compliance question (uses GPT-5.2, may take 10-30s)."""
        response = requests.post(f"{BASE_URL}/api/interrogate/ask", json={
            "question": "How many controls are non-compliant?"
        }, headers=admin_headers, timeout=60)
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "question" in data
        assert "answer" in data
        assert "session_id" in data
        assert "data_timestamp" in data
        assert data["question"] == "How many controls are non-compliant?"
        assert len(data["answer"]) > 10  # Should have a meaningful answer
        print(f"Interrogation answer: {data['answer'][:200]}...")

    def test_interrogation_with_session(self, admin_headers):
        """Test interrogation with session ID for context."""
        session_id = "test-session-123"
        response = requests.post(f"{BASE_URL}/api/interrogate/ask", json={
            "question": "What frameworks are we tracking?",
            "session_id": session_id
        }, headers=admin_headers, timeout=60)
        
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        assert data["session_id"] == session_id
        print(f"Session-based interrogation successful")


# ============================================================================
# 5. PREDICTIVE RISK FORECASTING TESTS
# ============================================================================

class TestPredictiveRiskForecasting:
    """Test predictive risk forecasting."""

    def test_forecasting_unauthorized(self):
        """Test forecasting without auth returns 401/403."""
        response = requests.get(f"{BASE_URL}/api/forecasting/predict")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_forecasting_predict(self, admin_headers):
        """Test predictive risk forecast returns predictions and warnings."""
        response = requests.get(f"{BASE_URL}/api/forecasting/predict", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Verify structure
        assert "predictions" in data
        assert "warnings" in data
        assert "data_points" in data
        assert "generated_at" in data
        
        # Verify data_points structure
        dp = data["data_points"]
        assert "risk_history_points" in dp
        assert "pipeline_runs" in dp
        assert "poam_entries" in dp
        assert "siem_daily_points" in dp
        
        # Predictions and warnings should be lists
        assert isinstance(data["predictions"], list)
        assert isinstance(data["warnings"], list)
        
        print(f"Forecasting returned {len(data['predictions'])} predictions and {len(data['warnings'])} warnings")
        print(f"Data points: {dp}")

    def test_forecasting_warning_structure(self, admin_headers):
        """Test warning structure if any exist."""
        response = requests.get(f"{BASE_URL}/api/forecasting/predict", headers=admin_headers)
        data = response.json()
        
        for warning in data["warnings"]:
            assert "type" in warning
            assert "severity" in warning
            assert "title" in warning
            assert "detail" in warning
            assert "recommendation" in warning
            assert warning["severity"] in ["critical", "high", "medium", "low"]
        
        for prediction in data["predictions"]:
            assert "type" in prediction
            assert "confidence" in prediction
            assert "title" in prediction
            assert "detail" in prediction
        
        print("Warning and prediction structures validated")


# ============================================================================
# 6. THIRD-PARTY RISK MANAGEMENT (TPRM) TESTS
# ============================================================================

class TestTPRM:
    """Test Third-Party Risk Management endpoints."""

    @pytest.fixture(scope="class")
    def test_vendor_id(self, admin_headers):
        """Create a test vendor and return its ID."""
        response = requests.post(f"{BASE_URL}/api/tprm/vendors", json={
            "name": "TEST_Vendor_Pytest",
            "contact_email": "test@vendor.com",
            "website": "https://testvendor.com",
            "category": "technology",
            "data_access_level": "medium",
            "description": "Test vendor for pytest"
        }, headers=admin_headers)
        assert response.status_code == 200, f"Failed to create vendor: {response.text}"
        vendor_id = response.json()["id"]
        yield vendor_id
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tprm/vendors/{vendor_id}", headers=admin_headers)

    def test_tprm_create_vendor_unauthorized(self):
        """Test creating vendor without auth returns 401/403."""
        response = requests.post(f"{BASE_URL}/api/tprm/vendors", json={
            "name": "Test Vendor"
        })
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_tprm_create_vendor(self, admin_headers):
        """Test creating a new vendor."""
        response = requests.post(f"{BASE_URL}/api/tprm/vendors", json={
            "name": "TEST_Acme Corp",
            "contact_email": "security@acme.com",
            "website": "https://acme.com",
            "category": "cloud",
            "data_access_level": "high",
            "description": "Cloud infrastructure provider"
        }, headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        vendor = response.json()
        
        assert "id" in vendor
        assert vendor["name"] == "TEST_Acme Corp"
        assert vendor["category"] == "cloud"
        assert vendor["data_access_level"] == "high"
        assert vendor["status"] == "pending"
        assert vendor["risk_level"] == "not_assessed"
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/tprm/vendors/{vendor['id']}", headers=admin_headers)
        print(f"Created and cleaned up vendor: {vendor['id']}")

    def test_tprm_list_vendors(self, admin_headers):
        """Test listing all vendors."""
        response = requests.get(f"{BASE_URL}/api/tprm/vendors", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        vendors = response.json()
        assert isinstance(vendors, list)
        print(f"Found {len(vendors)} vendors")

    def test_tprm_get_vendor_detail(self, admin_headers, test_vendor_id):
        """Test getting vendor detail with assessments."""
        response = requests.get(f"{BASE_URL}/api/tprm/vendors/{test_vendor_id}", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "vendor" in data
        assert "assessments" in data
        assert data["vendor"]["id"] == test_vendor_id
        print(f"Vendor detail retrieved with {len(data['assessments'])} assessments")

    def test_tprm_get_vendor_not_found(self, admin_headers):
        """Test getting non-existent vendor returns 404."""
        response = requests.get(f"{BASE_URL}/api/tprm/vendors/non-existent-id", headers=admin_headers)
        assert response.status_code == 404

    def test_tprm_delete_vendor(self, admin_headers):
        """Test deleting a vendor."""
        # Create vendor to delete
        create_response = requests.post(f"{BASE_URL}/api/tprm/vendors", json={
            "name": "TEST_ToDelete"
        }, headers=admin_headers)
        vendor_id = create_response.json()["id"]
        
        # Delete
        response = requests.delete(f"{BASE_URL}/api/tprm/vendors/{vendor_id}", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        # Verify deleted
        get_response = requests.get(f"{BASE_URL}/api/tprm/vendors/{vendor_id}", headers=admin_headers)
        assert get_response.status_code == 404
        print("Vendor deleted successfully")

    def test_tprm_update_vendor_status(self, admin_headers, test_vendor_id):
        """Test updating vendor status."""
        response = requests.put(f"{BASE_URL}/api/tprm/vendors/{test_vendor_id}/status", json={
            "status": "approved"
        }, headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        # Verify status updated
        get_response = requests.get(f"{BASE_URL}/api/tprm/vendors/{test_vendor_id}", headers=admin_headers)
        assert get_response.json()["vendor"]["status"] == "approved"
        print("Vendor status updated to approved")

    def test_tprm_questionnaire(self, admin_headers):
        """Test getting the 15-question risk questionnaire."""
        response = requests.get(f"{BASE_URL}/api/tprm/questionnaire", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "questions" in data
        assert "answer_options" in data
        questions = data["questions"]
        
        # Should have 15 questions
        assert len(questions) == 15, f"Expected 15 questions, got {len(questions)}"
        
        # Verify question structure
        for q in questions:
            assert "id" in q
            assert "question" in q
            assert "category" in q
            assert "weight" in q
            assert "control_ids" in q
        
        # Verify answer options
        assert set(data["answer_options"]) == {"yes", "partial", "no", "n/a"}
        
        print(f"Questionnaire has {len(questions)} questions with categories: {set(q['category'] for q in questions)}")

    def test_tprm_submit_assessment(self, admin_headers, test_vendor_id):
        """Test submitting a vendor risk assessment."""
        # Get questionnaire
        q_response = requests.get(f"{BASE_URL}/api/tprm/questionnaire", headers=admin_headers)
        questions = q_response.json()["questions"]
        
        # Create responses (mix of yes/partial/no)
        responses = []
        for i, q in enumerate(questions):
            if i < 5:
                answer = "yes"
            elif i < 10:
                answer = "partial"
            else:
                answer = "no"
            responses.append({"question_id": q["id"], "answer": answer})
        
        # Submit assessment
        response = requests.post(f"{BASE_URL}/api/tprm/assess", json={
            "vendor_id": test_vendor_id,
            "responses": responses
        }, headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "assessment" in data
        assert "message" in data
        assessment = data["assessment"]
        
        assert "id" in assessment
        assert "vendor_id" in assessment
        assert "raw_score" in assessment
        assert "risk_score" in assessment
        assert "compliance_score" in assessment
        assert "risk_level" in assessment
        assert "control_impacts" in assessment
        assert "data_access_multiplier" in assessment
        
        # Risk level should be one of the valid values
        assert assessment["risk_level"] in ["critical", "high", "medium", "low"]
        
        print(f"Assessment submitted: risk_score={assessment['risk_score']}, risk_level={assessment['risk_level']}")

    def test_tprm_dashboard(self, admin_headers):
        """Test TPRM dashboard stats."""
        response = requests.get(f"{BASE_URL}/api/tprm/dashboard", headers=admin_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "total_vendors" in data
        assert "by_risk_level" in data
        assert "by_status" in data
        assert "by_category" in data
        assert "average_risk" in data
        
        # Verify risk level categories
        risk_levels = data["by_risk_level"]
        assert "critical" in risk_levels
        assert "high" in risk_levels
        assert "medium" in risk_levels
        assert "low" in risk_levels
        assert "not_assessed" in risk_levels
        
        print(f"TPRM Dashboard: {data['total_vendors']} vendors, avg risk: {data['average_risk']}")


# ============================================================================
# CLEANUP
# ============================================================================

class TestCleanup:
    """Cleanup test data."""

    def test_cleanup_test_vendors(self, admin_headers):
        """Clean up TEST_ prefixed vendors."""
        response = requests.get(f"{BASE_URL}/api/tprm/vendors", headers=admin_headers)
        if response.status_code == 200:
            vendors = response.json()
            for v in vendors:
                if v["name"].startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/tprm/vendors/{v['id']}", headers=admin_headers)
                    print(f"Cleaned up vendor: {v['name']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
