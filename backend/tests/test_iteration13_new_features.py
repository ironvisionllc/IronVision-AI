"""
Iteration 13 - New Features Testing
Tests for:
1. Create Document - POST /api/documents/create
2. Document Review & Approval - PUT /api/documents/{id}/status, PUT /api/documents/{id}/content
3. Framework Workspace Link Document - POST /api/control-compliance/{fw}/{ctrl}/link-document
4. Unlink Document - DELETE /api/control-compliance/{fw}/{ctrl}/unlink-document/{id}
5. AI Coverage Analysis - POST /api/control-compliance/{fw}/{ctrl}/analyze-coverage
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for demo admin"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo-admin@grc.com",
        "password": "DemoAdmin123!"
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping authenticated tests")

@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestCreateDocument:
    """Test POST /api/documents/create - Create document from text editor"""
    
    def test_create_document_basic(self, auth_headers):
        """Create a basic document with title and content"""
        response = requests.post(f"{BASE_URL}/api/documents/create", json={
            "title": "TEST_Access Control Policy",
            "content": "This is a test access control policy document.\n\n1. Purpose\nDefine access control requirements.\n\n2. Scope\nApplies to all systems.",
            "category": "policy"
        }, headers=auth_headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "id" in data, "Response should contain 'id'"
        assert "job_id" in data, "Response should contain 'job_id'"
        assert data.get("file_type") == "created", "file_type should be 'created'"
        assert data.get("status") == "draft", "Initial status should be 'draft'"
        assert data.get("content") == "This is a test access control policy document.\n\n1. Purpose\nDefine access control requirements.\n\n2. Scope\nApplies to all systems."
        assert data.get("original_name") == "TEST_Access Control Policy"
        assert data.get("filename") == "TEST_Access Control Policy"
        assert data.get("category") == "policy"
        
        # Store for later tests
        TestCreateDocument.created_doc_id = data.get("id")
    
    def test_create_document_with_tags(self, auth_headers):
        """Create document with custom tags"""
        response = requests.post(f"{BASE_URL}/api/documents/create", json={
            "title": "TEST_Security Procedure",
            "content": "Security procedure content here.",
            "category": "procedure",
            "custom_tags": ["Annual Review", "Security"]
        }, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("custom_tags") == ["Annual Review", "Security"]
        assert data.get("category") == "procedure"
    
    def test_create_document_with_framework(self, auth_headers):
        """Create document linked to a framework"""
        response = requests.post(f"{BASE_URL}/api/documents/create", json={
            "title": "TEST_NIST Policy",
            "content": "NIST compliance policy content.",
            "category": "policy",
            "framework": "nist-800-53"
        }, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("framework") == "nist-800-53"
    
    def test_create_document_empty_title_uses_default(self, auth_headers):
        """Create document without title uses default"""
        response = requests.post(f"{BASE_URL}/api/documents/create", json={
            "content": "Some content without title"
        }, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("original_name") == "Untitled Document"


class TestDocumentApprovalWorkflow:
    """Test document status transitions: draft -> under_review -> approved"""
    
    def test_get_created_document(self, auth_headers):
        """Verify we can retrieve the created document"""
        doc_id = getattr(TestCreateDocument, 'created_doc_id', None)
        if not doc_id:
            pytest.skip("No created document ID available")
        
        response = requests.get(f"{BASE_URL}/api/documents/{doc_id}", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "draft"
        assert data.get("file_type") == "created"
    
    def test_submit_for_review(self, auth_headers):
        """Transition from draft to under_review"""
        doc_id = getattr(TestCreateDocument, 'created_doc_id', None)
        if not doc_id:
            pytest.skip("No created document ID available")
        
        response = requests.put(f"{BASE_URL}/api/documents/{doc_id}/status", json={
            "status": "under_review"
        }, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "under_review"
    
    def test_approve_document(self, auth_headers):
        """Transition from under_review to approved"""
        doc_id = getattr(TestCreateDocument, 'created_doc_id', None)
        if not doc_id:
            pytest.skip("No created document ID available")
        
        response = requests.put(f"{BASE_URL}/api/documents/{doc_id}/status", json={
            "status": "approved"
        }, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "approved"
    
    def test_reopen_as_draft(self, auth_headers):
        """Transition from approved back to draft"""
        doc_id = getattr(TestCreateDocument, 'created_doc_id', None)
        if not doc_id:
            pytest.skip("No created document ID available")
        
        response = requests.put(f"{BASE_URL}/api/documents/{doc_id}/status", json={
            "status": "draft"
        }, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("status") == "draft"
    
    def test_invalid_status_transition(self, auth_headers):
        """Cannot transition directly from draft to approved"""
        doc_id = getattr(TestCreateDocument, 'created_doc_id', None)
        if not doc_id:
            pytest.skip("No created document ID available")
        
        # First ensure it's in draft
        requests.put(f"{BASE_URL}/api/documents/{doc_id}/status", json={"status": "draft"}, headers=auth_headers)
        
        # Try to go directly to approved (should fail)
        response = requests.put(f"{BASE_URL}/api/documents/{doc_id}/status", json={
            "status": "approved"
        }, headers=auth_headers)
        
        assert response.status_code == 400, "Should not allow direct draft->approved transition"
    
    def test_invalid_status_value(self, auth_headers):
        """Invalid status value should return 400"""
        doc_id = getattr(TestCreateDocument, 'created_doc_id', None)
        if not doc_id:
            pytest.skip("No created document ID available")
        
        response = requests.put(f"{BASE_URL}/api/documents/{doc_id}/status", json={
            "status": "invalid_status"
        }, headers=auth_headers)
        
        assert response.status_code == 400


class TestDocumentContentUpdate:
    """Test PUT /api/documents/{id}/content - Update document content"""
    
    def test_update_content(self, auth_headers):
        """Update document content"""
        doc_id = getattr(TestCreateDocument, 'created_doc_id', None)
        if not doc_id:
            pytest.skip("No created document ID available")
        
        new_content = "Updated policy content.\n\n1. New Purpose\n2. New Scope\n3. New Requirements"
        response = requests.put(f"{BASE_URL}/api/documents/{doc_id}/content", json={
            "content": new_content
        }, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("content") == new_content
    
    def test_update_title_via_content_endpoint(self, auth_headers):
        """Update document title via content endpoint"""
        doc_id = getattr(TestCreateDocument, 'created_doc_id', None)
        if not doc_id:
            pytest.skip("No created document ID available")
        
        response = requests.put(f"{BASE_URL}/api/documents/{doc_id}/content", json={
            "title": "TEST_Updated Policy Title"
        }, headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("original_name") == "TEST_Updated Policy Title"
        assert data.get("filename") == "TEST_Updated Policy Title"


class TestLinkDocumentToControl:
    """Test POST /api/control-compliance/{fw}/{ctrl}/link-document"""
    
    @pytest.fixture(scope="class")
    def framework_id(self):
        # NIST SP 800-53 framework UUID
        return "394b18c4-f22e-4b9a-984b-b5e2ec8143cb"
    
    @pytest.fixture(scope="class")
    def control_id(self):
        return "AC-2"
    
    def test_link_document_to_control(self, auth_headers, framework_id, control_id):
        """Link a document to a control"""
        doc_id = getattr(TestCreateDocument, 'created_doc_id', None)
        if not doc_id:
            pytest.skip("No created document ID available")
        
        response = requests.post(
            f"{BASE_URL}/api/control-compliance/{framework_id}/{control_id}/link-document",
            json={
                "document_id": doc_id,
                "document_name": "TEST_Updated Policy Title",
                "document_type": "uploaded"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "id" in data, "Response should contain mapping 'id'"
        assert data.get("control_id") == control_id
        assert data.get("framework_id") == framework_id
        assert data.get("source_document_id") == doc_id
        assert data.get("status") == "linked"
        
        # Store mapping ID for unlink test
        TestLinkDocumentToControl.mapping_id = data.get("id")
    
    def test_link_duplicate_document_fails(self, auth_headers, framework_id, control_id):
        """Linking same document twice should fail"""
        doc_id = getattr(TestCreateDocument, 'created_doc_id', None)
        if not doc_id:
            pytest.skip("No created document ID available")
        
        response = requests.post(
            f"{BASE_URL}/api/control-compliance/{framework_id}/{control_id}/link-document",
            json={
                "document_id": doc_id,
                "document_name": "TEST_Updated Policy Title",
                "document_type": "uploaded"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 400, "Should not allow duplicate linking"
    
    def test_link_without_document_id_fails(self, auth_headers, framework_id, control_id):
        """Linking without document_id should fail"""
        response = requests.post(
            f"{BASE_URL}/api/control-compliance/{framework_id}/{control_id}/link-document",
            json={
                "document_name": "Some Document"
            },
            headers=auth_headers
        )
        
        assert response.status_code == 400


class TestAnalyzeCoverage:
    """Test POST /api/control-compliance/{fw}/{ctrl}/analyze-coverage"""
    
    @pytest.fixture(scope="class")
    def framework_id(self):
        # NIST SP 800-53 framework UUID
        return "394b18c4-f22e-4b9a-984b-b5e2ec8143cb"
    
    @pytest.fixture(scope="class")
    def control_id(self):
        return "AC-2"
    
    def test_analyze_coverage_with_content(self, auth_headers, framework_id, control_id):
        """Analyze coverage for a document with content"""
        doc_id = getattr(TestCreateDocument, 'created_doc_id', None)
        if not doc_id:
            pytest.skip("No created document ID available")
        
        response = requests.post(
            f"{BASE_URL}/api/control-compliance/{framework_id}/{control_id}/analyze-coverage",
            json={"document_id": doc_id},
            headers=auth_headers,
            timeout=30  # AI analysis may take time
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "coverage_score" in data, "Response should contain 'coverage_score'"
        assert "coverage_level" in data, "Response should contain 'coverage_level'"
        assert data.get("coverage_level") in ["full", "partial", "minimal", "none"]
        assert isinstance(data.get("coverage_score"), (int, float))
        assert 0 <= data.get("coverage_score") <= 100
        
        # Optional fields
        if "addressed_requirements" in data:
            assert isinstance(data["addressed_requirements"], list)
        if "gaps" in data:
            assert isinstance(data["gaps"], list)
    
    def test_analyze_coverage_nonexistent_document(self, auth_headers, framework_id, control_id):
        """Analyze coverage for non-existent document should fail"""
        response = requests.post(
            f"{BASE_URL}/api/control-compliance/{framework_id}/{control_id}/analyze-coverage",
            json={"document_id": "nonexistent-doc-id-12345"},
            headers=auth_headers,
            timeout=30
        )
        
        assert response.status_code == 404


class TestUnlinkDocument:
    """Test DELETE /api/control-compliance/{fw}/{ctrl}/unlink-document/{id}"""
    
    @pytest.fixture(scope="class")
    def framework_id(self):
        # NIST SP 800-53 framework UUID
        return "394b18c4-f22e-4b9a-984b-b5e2ec8143cb"
    
    @pytest.fixture(scope="class")
    def control_id(self):
        return "AC-2"
    
    def test_unlink_document(self, auth_headers, framework_id, control_id):
        """Unlink a document from a control"""
        mapping_id = getattr(TestLinkDocumentToControl, 'mapping_id', None)
        if not mapping_id:
            pytest.skip("No mapping ID available")
        
        response = requests.delete(
            f"{BASE_URL}/api/control-compliance/{framework_id}/{control_id}/unlink-document/{mapping_id}",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data.get("message") == "Document unlinked"
    
    def test_unlink_nonexistent_mapping(self, auth_headers, framework_id, control_id):
        """Unlinking non-existent mapping should return 404"""
        response = requests.delete(
            f"{BASE_URL}/api/control-compliance/{framework_id}/{control_id}/unlink-document/nonexistent-mapping-id",
            headers=auth_headers
        )
        
        assert response.status_code == 404


class TestPolicyCoverageSummary:
    """Test that compliance overview includes policy coverage data"""
    
    def test_compliance_overview_has_policy_count(self, auth_headers):
        """Verify controls have policy_count field"""
        # NIST SP 800-53 framework UUID
        framework_id = "394b18c4-f22e-4b9a-984b-b5e2ec8143cb"
        response = requests.get(f"{BASE_URL}/api/control-compliance/{framework_id}", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        
        assert "controls" in data
        assert len(data["controls"]) > 0
        
        # Check first control has policy_count
        first_control = data["controls"][0]
        assert "policy_count" in first_control, "Control should have 'policy_count' field"
        assert isinstance(first_control["policy_count"], int)
        
        # Check policy_mappings field
        assert "policy_mappings" in first_control, "Control should have 'policy_mappings' field"
        assert isinstance(first_control["policy_mappings"], list)


class TestGetDocumentsForLinking:
    """Test that documents and generated policies are available for linking"""
    
    def test_get_documents_list(self, auth_headers):
        """Get list of uploaded documents"""
        response = requests.get(f"{BASE_URL}/api/documents", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        
        # Check for created documents
        created_docs = [d for d in data if d.get("file_type") == "created"]
        assert len(created_docs) > 0, "Should have at least one created document"
    
    def test_get_generated_policies_list(self, auth_headers):
        """Get list of generated policies"""
        response = requests.get(f"{BASE_URL}/api/policy-templates/generated", headers=auth_headers)
        
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)


class TestCleanup:
    """Cleanup test data"""
    
    def test_cleanup_test_documents(self, auth_headers):
        """Note: In a real scenario, we'd delete TEST_ prefixed documents"""
        # This is a placeholder - actual cleanup would require a delete endpoint
        # For now, just verify we can list documents
        response = requests.get(f"{BASE_URL}/api/documents", headers=auth_headers)
        assert response.status_code == 200
        print(f"Total documents in system: {len(response.json())}")
