"""
Test Evidence Library File Upload Feature
Tests: POST /api/evidence with multipart form data, GET /api/evidence, 
       GET /api/evidence/{id}/download, DELETE /api/evidence/{id}
"""
import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_USER_EMAIL = "test-upload@grc.com"
TEST_USER_PASSWORD = "TestUpload123!"
DEMO_ADMIN_EMAIL = "demo-admin@grc.com"
DEMO_ADMIN_PASSWORD = "DemoAdmin123!"


@pytest.fixture(scope="module")
def test_user_token():
    """Get auth token for test-upload user (non-demo)"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_USER_EMAIL,
        "password": TEST_USER_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Test user login failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def demo_admin_token():
    """Get auth token for demo admin"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEMO_ADMIN_EMAIL,
        "password": DEMO_ADMIN_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("token")
    pytest.skip(f"Demo admin login failed: {response.status_code} - {response.text}")


@pytest.fixture
def auth_headers(test_user_token):
    """Headers with auth token for test user"""
    return {"Authorization": f"Bearer {test_user_token}"}


@pytest.fixture
def demo_headers(demo_admin_token):
    """Headers with auth token for demo admin"""
    return {"Authorization": f"Bearer {demo_admin_token}"}


class TestEvidenceFileUpload:
    """Test evidence file upload functionality"""
    
    created_evidence_ids = []
    
    def test_01_create_evidence_with_file(self, auth_headers):
        """POST /api/evidence with file upload should succeed"""
        # Create a test file
        test_content = b"This is a test file content for evidence upload testing."
        files = {
            "file": ("test_document.txt", io.BytesIO(test_content), "text/plain")
        }
        data = {
            "description": "TEST_Evidence with file attachment",
            "evidence_type": "document",
            "control_id": "CC6.1",
            "framework_name": "SOC 2",
            "tags": "test,upload,automated"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/evidence",
            headers=auth_headers,
            files=files,
            data=data
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        # Verify response structure
        assert "id" in result
        assert result["description"] == "TEST_Evidence with file attachment"
        assert result["evidence_type"] == "document"
        assert result["control_id"] == "CC6.1"
        assert result["framework_name"] == "SOC 2"
        assert "test" in result["tags"]
        
        # Verify file info
        assert result.get("file") is not None, "File info should be present"
        assert result["file"]["original_name"] == "test_document.txt"
        assert result["file"]["size"] == len(test_content)
        assert "stored_name" in result["file"]
        
        self.__class__.created_evidence_ids.append(result["id"])
        print(f"Created evidence with file: {result['id']}")
    
    def test_02_create_evidence_without_file(self, auth_headers):
        """POST /api/evidence without file (metadata only) should succeed"""
        data = {
            "description": "TEST_Evidence without file - metadata only",
            "evidence_type": "attestation",
            "control_id": "A.9.2.5",
            "framework_name": "ISO 27001",
            "tags": "test,no-file"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/evidence",
            headers=auth_headers,
            data=data
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        result = response.json()
        
        assert "id" in result
        assert result["description"] == "TEST_Evidence without file - metadata only"
        assert result["evidence_type"] == "attestation"
        assert result.get("file") is None, "File should be None for metadata-only evidence"
        
        self.__class__.created_evidence_ids.append(result["id"])
        print(f"Created evidence without file: {result['id']}")
    
    def test_03_get_evidence_list(self, auth_headers):
        """GET /api/evidence should return evidence items with file metadata"""
        response = requests.get(f"{BASE_URL}/api/evidence", headers=auth_headers)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        evidence_list = response.json()
        
        assert isinstance(evidence_list, list)
        
        # Find our test evidence items
        test_items = [e for e in evidence_list if e.get("description", "").startswith("TEST_")]
        assert len(test_items) >= 2, f"Expected at least 2 test items, found {len(test_items)}"
        
        # Check item with file
        with_file = [e for e in test_items if e.get("file") is not None]
        assert len(with_file) >= 1, "Should have at least one evidence with file"
        
        file_item = with_file[0]
        assert "original_name" in file_item["file"]
        assert "size" in file_item["file"]
        assert "stored_name" in file_item["file"]
        
        print(f"Found {len(evidence_list)} total evidence items, {len(with_file)} with files")
    
    def test_04_download_evidence_file(self, auth_headers):
        """GET /api/evidence/{id}/download should download the attached file"""
        # First get evidence list to find one with a file
        response = requests.get(f"{BASE_URL}/api/evidence", headers=auth_headers)
        assert response.status_code == 200
        
        evidence_list = response.json()
        with_file = [e for e in evidence_list if e.get("file") is not None and e.get("description", "").startswith("TEST_")]
        
        if not with_file:
            pytest.skip("No test evidence with file found")
        
        evidence_id = with_file[0]["id"]
        original_name = with_file[0]["file"]["original_name"]
        
        # Download the file
        download_response = requests.get(
            f"{BASE_URL}/api/evidence/{evidence_id}/download",
            headers=auth_headers
        )
        
        assert download_response.status_code == 200, f"Expected 200, got {download_response.status_code}: {download_response.text}"
        
        # Check content-disposition header
        content_disp = download_response.headers.get("content-disposition", "")
        assert "attachment" in content_disp.lower() or original_name in content_disp, \
            f"Expected attachment header with filename, got: {content_disp}"
        
        # Verify content is not empty
        assert len(download_response.content) > 0, "Downloaded file should not be empty"
        
        print(f"Successfully downloaded file: {original_name} ({len(download_response.content)} bytes)")
    
    def test_05_download_nonexistent_evidence(self, auth_headers):
        """GET /api/evidence/{id}/download for non-existent ID should return 404"""
        response = requests.get(
            f"{BASE_URL}/api/evidence/nonexistent-id-12345/download",
            headers=auth_headers
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("Correctly returned 404 for non-existent evidence")
    
    def test_06_download_evidence_without_file(self, auth_headers):
        """GET /api/evidence/{id}/download for evidence without file should return 404"""
        # Find evidence without file
        response = requests.get(f"{BASE_URL}/api/evidence", headers=auth_headers)
        assert response.status_code == 200
        
        evidence_list = response.json()
        without_file = [e for e in evidence_list if e.get("file") is None and e.get("description", "").startswith("TEST_")]
        
        if not without_file:
            pytest.skip("No test evidence without file found")
        
        evidence_id = without_file[0]["id"]
        
        download_response = requests.get(
            f"{BASE_URL}/api/evidence/{evidence_id}/download",
            headers=auth_headers
        )
        
        assert download_response.status_code == 404, f"Expected 404, got {download_response.status_code}"
        assert "No file attached" in download_response.json().get("detail", "")
        print("Correctly returned 404 for evidence without file attachment")
    
    def test_07_demo_account_blocked_from_upload(self, demo_headers):
        """POST /api/evidence should return 403 for demo accounts"""
        data = {
            "description": "Demo should not be able to upload",
            "evidence_type": "document",
            "tags": ""
        }
        
        response = requests.post(
            f"{BASE_URL}/api/evidence",
            headers=demo_headers,
            data=data
        )
        
        assert response.status_code == 403, f"Expected 403 for demo account, got {response.status_code}"
        assert "Demo mode" in response.json().get("detail", "")
        print("Demo account correctly blocked from uploading evidence")
    
    def test_08_delete_evidence_removes_file(self, auth_headers):
        """DELETE /api/evidence/{id} should remove both DB record and file from disk"""
        # Create a new evidence with file for deletion test
        test_content = b"File to be deleted"
        files = {
            "file": ("delete_test.txt", io.BytesIO(test_content), "text/plain")
        }
        data = {
            "description": "TEST_Evidence to be deleted",
            "evidence_type": "document",
            "tags": "delete-test"
        }
        
        create_response = requests.post(
            f"{BASE_URL}/api/evidence",
            headers=auth_headers,
            files=files,
            data=data
        )
        
        assert create_response.status_code == 200
        evidence_id = create_response.json()["id"]
        stored_name = create_response.json()["file"]["stored_name"]
        
        # Delete the evidence
        delete_response = requests.delete(
            f"{BASE_URL}/api/evidence/{evidence_id}",
            headers=auth_headers
        )
        
        assert delete_response.status_code == 200, f"Expected 200, got {delete_response.status_code}"
        assert "deleted" in delete_response.json().get("message", "").lower()
        
        # Verify evidence is gone from list
        list_response = requests.get(f"{BASE_URL}/api/evidence", headers=auth_headers)
        evidence_list = list_response.json()
        deleted_item = [e for e in evidence_list if e.get("id") == evidence_id]
        assert len(deleted_item) == 0, "Deleted evidence should not appear in list"
        
        print(f"Successfully deleted evidence {evidence_id} and its file")
    
    def test_09_demo_account_blocked_from_delete(self, demo_headers):
        """DELETE /api/evidence/{id} should return 403 for demo accounts"""
        # Try to delete a demo evidence item
        response = requests.delete(
            f"{BASE_URL}/api/evidence/demo-ev-001",
            headers=demo_headers
        )
        
        assert response.status_code == 403, f"Expected 403 for demo account, got {response.status_code}"
        print("Demo account correctly blocked from deleting evidence")
    
    def test_10_cleanup_test_evidence(self, auth_headers):
        """Cleanup: Delete all TEST_ prefixed evidence items"""
        response = requests.get(f"{BASE_URL}/api/evidence", headers=auth_headers)
        if response.status_code != 200:
            return
        
        evidence_list = response.json()
        test_items = [e for e in evidence_list if e.get("description", "").startswith("TEST_")]
        
        deleted_count = 0
        for item in test_items:
            del_response = requests.delete(
                f"{BASE_URL}/api/evidence/{item['id']}",
                headers=auth_headers
            )
            if del_response.status_code == 200:
                deleted_count += 1
        
        print(f"Cleanup: Deleted {deleted_count} test evidence items")


class TestFileSizeLimit:
    """Test file size limit enforcement"""
    
    def test_file_over_50mb_rejected(self, auth_headers):
        """POST /api/evidence with file over 50MB should return 413"""
        # Create a file slightly over 50MB (50MB + 1KB)
        # Note: This test may be slow due to large payload
        large_content = b"x" * (50 * 1024 * 1024 + 1024)  # 50MB + 1KB
        
        files = {
            "file": ("large_file.bin", io.BytesIO(large_content), "application/octet-stream")
        }
        data = {
            "description": "TEST_Large file that should be rejected",
            "evidence_type": "document",
            "tags": ""
        }
        
        response = requests.post(
            f"{BASE_URL}/api/evidence",
            headers=auth_headers,
            files=files,
            data=data,
            timeout=120  # Longer timeout for large upload
        )
        
        assert response.status_code == 413, f"Expected 413 for oversized file, got {response.status_code}"
        assert "too large" in response.json().get("detail", "").lower() or "50MB" in response.json().get("detail", "")
        print("Correctly rejected file over 50MB with 413 error")


class TestEvidenceWithDifferentFileTypes:
    """Test evidence upload with various file types"""
    
    created_ids = []
    
    def test_upload_pdf_file(self, auth_headers):
        """Upload PDF file type"""
        # Minimal PDF content
        pdf_content = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF"
        files = {
            "file": ("test_report.pdf", io.BytesIO(pdf_content), "application/pdf")
        }
        data = {
            "description": "TEST_PDF Report Upload",
            "evidence_type": "report",
            "tags": "pdf,test"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/evidence",
            headers=auth_headers,
            files=files,
            data=data
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["file"]["original_name"] == "test_report.pdf"
        assert result["file"]["content_type"] == "application/pdf"
        self.__class__.created_ids.append(result["id"])
        print("Successfully uploaded PDF file")
    
    def test_upload_image_file(self, auth_headers):
        """Upload image file type"""
        # Minimal PNG content (1x1 transparent pixel)
        png_content = bytes([
            0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
            0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
            0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01,
            0x08, 0x06, 0x00, 0x00, 0x00, 0x1F, 0x15, 0xC4,
            0x89, 0x00, 0x00, 0x00, 0x0A, 0x49, 0x44, 0x41,
            0x54, 0x78, 0x9C, 0x63, 0x00, 0x01, 0x00, 0x00,
            0x05, 0x00, 0x01, 0x0D, 0x0A, 0x2D, 0xB4, 0x00,
            0x00, 0x00, 0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE,
            0x42, 0x60, 0x82
        ])
        files = {
            "file": ("screenshot.png", io.BytesIO(png_content), "image/png")
        }
        data = {
            "description": "TEST_Screenshot Upload",
            "evidence_type": "screenshot",
            "tags": "image,test"
        }
        
        response = requests.post(
            f"{BASE_URL}/api/evidence",
            headers=auth_headers,
            files=files,
            data=data
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["file"]["original_name"] == "screenshot.png"
        self.__class__.created_ids.append(result["id"])
        print("Successfully uploaded PNG image")
    
    def test_cleanup_file_type_tests(self, auth_headers):
        """Cleanup file type test evidence"""
        for eid in self.__class__.created_ids:
            requests.delete(f"{BASE_URL}/api/evidence/{eid}", headers=auth_headers)
        print(f"Cleaned up {len(self.__class__.created_ids)} file type test items")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
