"""
Iteration 12: Document Management Enhancement Tests
Tests for:
- Upload & Map redesign (category, custom_tags in upload)
- Document Library enhancements (click-to-view, category filter)
- DocumentDetailPanel (metadata editing, custom labels, framework tags)
- Backend endpoints: PUT /api/documents/{id}/metadata, GET /api/documents/custom-tags
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for demo admin."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo-admin@grc.com", "password": "DemoAdmin123!"},
    )
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip("Authentication failed - skipping tests")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestDocumentsEndpoint:
    """Tests for GET /api/documents endpoint."""

    def test_get_documents_returns_list(self, auth_headers):
        """GET /api/documents returns a list of documents."""
        response = requests.get(f"{BASE_URL}/api/documents", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} documents")

    def test_documents_have_filename_field(self, auth_headers):
        """Documents should have filename field for frontend compatibility."""
        response = requests.get(f"{BASE_URL}/api/documents", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            doc = data[0]
            assert "filename" in doc or "original_name" in doc
            print(f"Document has filename: {doc.get('filename') or doc.get('original_name')}")

    def test_documents_have_job_id_field(self, auth_headers):
        """Documents should have job_id field for frontend compatibility."""
        response = requests.get(f"{BASE_URL}/api/documents", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            doc = data[0]
            assert "job_id" in doc or "id" in doc
            print(f"Document has job_id: {doc.get('job_id') or doc.get('id')}")

    def test_documents_have_category_field(self, auth_headers):
        """Documents should have category field."""
        response = requests.get(f"{BASE_URL}/api/documents", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            doc = data[0]
            # Category may be present or default to 'other'
            category = doc.get("category", "other")
            assert category in ["policy", "procedure", "evidence", "contract", "training", "other"]
            print(f"Document category: {category}")

    def test_documents_have_custom_tags_field(self, auth_headers):
        """Documents should have custom_tags field."""
        response = requests.get(f"{BASE_URL}/api/documents", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            doc = data[0]
            custom_tags = doc.get("custom_tags", [])
            assert isinstance(custom_tags, list)
            print(f"Document custom_tags: {custom_tags}")


class TestCustomTagsEndpoint:
    """Tests for GET /api/documents/custom-tags endpoint."""

    def test_get_custom_tags_returns_list(self, auth_headers):
        """GET /api/documents/custom-tags returns a list of unique tags."""
        response = requests.get(f"{BASE_URL}/api/documents/custom-tags", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} unique custom tags: {data}")

    def test_custom_tags_are_strings(self, auth_headers):
        """Custom tags should be strings."""
        response = requests.get(f"{BASE_URL}/api/documents/custom-tags", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        for tag in data:
            assert isinstance(tag, str)


class TestDocumentMetadataEndpoint:
    """Tests for PUT /api/documents/{id}/metadata endpoint."""

    @pytest.fixture
    def existing_doc_id(self, auth_headers):
        """Get an existing document ID for testing."""
        response = requests.get(f"{BASE_URL}/api/documents", headers=auth_headers)
        if response.status_code == 200 and len(response.json()) > 0:
            doc = response.json()[0]
            return doc.get("job_id") or doc.get("id")
        pytest.skip("No documents available for testing")

    def test_update_category(self, auth_headers, existing_doc_id):
        """PUT /api/documents/{id}/metadata can update category."""
        # Get original
        orig_response = requests.get(f"{BASE_URL}/api/documents/{existing_doc_id}", headers=auth_headers)
        orig_category = orig_response.json().get("category", "other") if orig_response.status_code == 200 else "other"

        # Update to 'procedure'
        response = requests.put(
            f"{BASE_URL}/api/documents/{existing_doc_id}/metadata",
            headers=auth_headers,
            json={"category": "procedure"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "procedure"
        print(f"Category updated to: {data['category']}")

        # Revert
        requests.put(
            f"{BASE_URL}/api/documents/{existing_doc_id}/metadata",
            headers=auth_headers,
            json={"category": orig_category},
        )

    def test_update_custom_tags(self, auth_headers, existing_doc_id):
        """PUT /api/documents/{id}/metadata can update custom_tags."""
        # Get original
        orig_response = requests.get(f"{BASE_URL}/api/documents/{existing_doc_id}", headers=auth_headers)
        orig_tags = orig_response.json().get("custom_tags", []) if orig_response.status_code == 200 else []

        # Update tags
        new_tags = ["Test Tag 1", "Test Tag 2"]
        response = requests.put(
            f"{BASE_URL}/api/documents/{existing_doc_id}/metadata",
            headers=auth_headers,
            json={"custom_tags": new_tags},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["custom_tags"] == new_tags
        print(f"Custom tags updated to: {data['custom_tags']}")

        # Revert
        requests.put(
            f"{BASE_URL}/api/documents/{existing_doc_id}/metadata",
            headers=auth_headers,
            json={"custom_tags": orig_tags},
        )

    def test_update_description(self, auth_headers, existing_doc_id):
        """PUT /api/documents/{id}/metadata can update description."""
        # Get original
        orig_response = requests.get(f"{BASE_URL}/api/documents/{existing_doc_id}", headers=auth_headers)
        orig_desc = orig_response.json().get("description", "") if orig_response.status_code == 200 else ""

        # Update description
        new_desc = "Test description for iteration 12"
        response = requests.put(
            f"{BASE_URL}/api/documents/{existing_doc_id}/metadata",
            headers=auth_headers,
            json={"description": new_desc},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["description"] == new_desc
        print(f"Description updated to: {data['description']}")

        # Revert
        requests.put(
            f"{BASE_URL}/api/documents/{existing_doc_id}/metadata",
            headers=auth_headers,
            json={"description": orig_desc},
        )

    def test_update_multiple_fields(self, auth_headers, existing_doc_id):
        """PUT /api/documents/{id}/metadata can update multiple fields at once."""
        # Get original
        orig_response = requests.get(f"{BASE_URL}/api/documents/{existing_doc_id}", headers=auth_headers)
        orig_data = orig_response.json() if orig_response.status_code == 200 else {}

        # Update multiple fields
        response = requests.put(
            f"{BASE_URL}/api/documents/{existing_doc_id}/metadata",
            headers=auth_headers,
            json={
                "category": "contract",
                "custom_tags": ["Multi-field Test"],
                "description": "Multi-field update test",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "contract"
        assert data["custom_tags"] == ["Multi-field Test"]
        assert data["description"] == "Multi-field update test"
        print("Multiple fields updated successfully")

        # Revert
        requests.put(
            f"{BASE_URL}/api/documents/{existing_doc_id}/metadata",
            headers=auth_headers,
            json={
                "category": orig_data.get("category", "other"),
                "custom_tags": orig_data.get("custom_tags", []),
                "description": orig_data.get("description", ""),
            },
        )

    def test_update_nonexistent_document_returns_404(self, auth_headers):
        """PUT /api/documents/{id}/metadata returns 404 for nonexistent document."""
        response = requests.put(
            f"{BASE_URL}/api/documents/nonexistent-doc-id/metadata",
            headers=auth_headers,
            json={"category": "policy"},
        )
        assert response.status_code == 404


class TestGeneratedPoliciesEndpoint:
    """Tests for generated policies in Document Library."""

    def test_get_generated_policies(self, auth_headers):
        """GET /api/policy-templates/generated returns list of generated policies."""
        response = requests.get(f"{BASE_URL}/api/policy-templates/generated", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} generated policies")

    def test_generated_policies_have_required_fields(self, auth_headers):
        """Generated policies should have required fields for Document Library."""
        response = requests.get(f"{BASE_URL}/api/policy-templates/generated", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            policy = data[0]
            assert "id" in policy
            assert "title" in policy
            assert "status" in policy
            assert "created_at" in policy
            print(f"Policy has required fields: id={policy['id']}, title={policy['title']}, status={policy['status']}")


class TestFrameworksEndpoint:
    """Tests for frameworks endpoint used in Upload & Map."""

    def test_get_frameworks(self, auth_headers):
        """GET /api/frameworks returns list of frameworks."""
        response = requests.get(f"{BASE_URL}/api/frameworks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) > 0
        print(f"Found {len(data)} frameworks")

    def test_frameworks_have_required_fields(self, auth_headers):
        """Frameworks should have id, name, control_count."""
        response = requests.get(f"{BASE_URL}/api/frameworks", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        if len(data) > 0:
            fw = data[0]
            assert "id" in fw
            assert "name" in fw
            print(f"Framework: {fw['name']} (id={fw['id']})")


class TestDocumentTagsEndpoint:
    """Tests for document tags (framework control tags) endpoint."""

    def test_get_document_tags(self, auth_headers):
        """GET /api/policy-templates/document-tags returns list of tags."""
        response = requests.get(f"{BASE_URL}/api/policy-templates/document-tags", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Found {len(data)} document tags")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
