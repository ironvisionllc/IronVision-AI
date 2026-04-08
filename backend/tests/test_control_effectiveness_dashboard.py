"""
Test Control Effectiveness Dashboard Endpoint
Tests the new GET /api/control-effectiveness/dashboard endpoint
that aggregates effectiveness across all frameworks.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_EMAIL = "demo-admin@grc.com"
ADMIN_PASSWORD = "DemoAdmin123!"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")
    return response.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Return headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestControlEffectivenessDashboard:
    """Tests for GET /api/control-effectiveness/dashboard endpoint"""

    def test_dashboard_endpoint_returns_200(self, auth_headers):
        """Test that dashboard endpoint returns 200 OK"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/dashboard",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ Dashboard endpoint returns 200 OK")

    def test_dashboard_response_structure(self, auth_headers):
        """Test that response has required top-level fields"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/dashboard",
            headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        
        # Check required top-level fields
        required_fields = ["overall_score", "overall_grade", "total_frameworks", 
                          "total_controls_sampled", "distribution", "frameworks"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        print(f"✓ Response has all required top-level fields: {required_fields}")

    def test_dashboard_overall_score_valid(self, auth_headers):
        """Test that overall_score is a valid integer 0-100"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/dashboard",
            headers=auth_headers
        )
        data = response.json()
        
        assert isinstance(data["overall_score"], int), "overall_score should be an integer"
        assert 0 <= data["overall_score"] <= 100, f"overall_score {data['overall_score']} should be 0-100"
        print(f"✓ overall_score is valid: {data['overall_score']}")

    def test_dashboard_overall_grade_valid(self, auth_headers):
        """Test that overall_grade is a valid grade string"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/dashboard",
            headers=auth_headers
        )
        data = response.json()
        
        valid_grades = ["Excellent", "Good", "Fair", "Needs Improvement", "Critical"]
        assert data["overall_grade"] in valid_grades, f"Invalid grade: {data['overall_grade']}"
        print(f"✓ overall_grade is valid: {data['overall_grade']}")

    def test_dashboard_distribution_structure(self, auth_headers):
        """Test that distribution has all required grade categories"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/dashboard",
            headers=auth_headers
        )
        data = response.json()
        
        distribution = data["distribution"]
        required_keys = ["excellent", "good", "fair", "needs_improvement", "critical"]
        for key in required_keys:
            assert key in distribution, f"Missing distribution key: {key}"
            assert isinstance(distribution[key], int), f"distribution[{key}] should be int"
            assert distribution[key] >= 0, f"distribution[{key}] should be >= 0"
        
        print(f"✓ distribution has all required keys: {distribution}")

    def test_dashboard_frameworks_array(self, auth_headers):
        """Test that frameworks is an array with proper structure"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/dashboard",
            headers=auth_headers
        )
        data = response.json()
        
        frameworks = data["frameworks"]
        assert isinstance(frameworks, list), "frameworks should be a list"
        assert len(frameworks) > 0, "frameworks should not be empty"
        
        print(f"✓ frameworks array has {len(frameworks)} items")

    def test_dashboard_framework_item_structure(self, auth_headers):
        """Test that each framework item has required fields"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/dashboard",
            headers=auth_headers
        )
        data = response.json()
        
        frameworks = data["frameworks"]
        if len(frameworks) == 0:
            pytest.skip("No frameworks to test")
        
        # Check first framework item
        fw = frameworks[0]
        required_fields = ["framework_id", "framework_name", "average_score", 
                          "grade", "total_controls", "distribution"]
        for field in required_fields:
            assert field in fw, f"Framework missing field: {field}"
        
        # Validate types
        assert isinstance(fw["framework_id"], str), "framework_id should be string"
        assert isinstance(fw["framework_name"], str), "framework_name should be string"
        assert isinstance(fw["average_score"], int), "average_score should be int"
        assert isinstance(fw["grade"], str), "grade should be string"
        assert isinstance(fw["total_controls"], int), "total_controls should be int"
        assert isinstance(fw["distribution"], dict), "distribution should be dict"
        
        print(f"✓ Framework item has valid structure: {fw['framework_name']}")

    def test_dashboard_framework_distribution_structure(self, auth_headers):
        """Test that each framework's distribution has required keys"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/dashboard",
            headers=auth_headers
        )
        data = response.json()
        
        frameworks = data["frameworks"]
        if len(frameworks) == 0:
            pytest.skip("No frameworks to test")
        
        fw = frameworks[0]
        distribution = fw["distribution"]
        required_keys = ["excellent", "good", "fair", "needs_improvement", "critical"]
        for key in required_keys:
            assert key in distribution, f"Framework distribution missing key: {key}"
        
        print(f"✓ Framework distribution has all required keys")

    def test_dashboard_total_controls_matches_distribution(self, auth_headers):
        """Test that total_controls_sampled matches sum of distribution"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/dashboard",
            headers=auth_headers
        )
        data = response.json()
        
        distribution = data["distribution"]
        dist_sum = sum(distribution.values())
        
        assert dist_sum == data["total_controls_sampled"], \
            f"Distribution sum ({dist_sum}) should equal total_controls_sampled ({data['total_controls_sampled']})"
        
        print(f"✓ Distribution sum ({dist_sum}) matches total_controls_sampled")

    def test_dashboard_requires_auth(self):
        """Test that endpoint requires authentication"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/dashboard"
        )
        assert response.status_code in [401, 403], \
            f"Expected 401/403 without auth, got {response.status_code}"
        print(f"✓ Endpoint requires authentication (returns {response.status_code})")


class TestDashboardDataConsistency:
    """Tests for data consistency in dashboard response"""

    def test_framework_scores_within_range(self, auth_headers):
        """Test that all framework scores are 0-100"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/dashboard",
            headers=auth_headers
        )
        data = response.json()
        
        for fw in data["frameworks"]:
            assert 0 <= fw["average_score"] <= 100, \
                f"Framework {fw['framework_name']} score {fw['average_score']} out of range"
        
        print(f"✓ All {len(data['frameworks'])} framework scores are within 0-100")

    def test_framework_grades_valid(self, auth_headers):
        """Test that all framework grades are valid"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/dashboard",
            headers=auth_headers
        )
        data = response.json()
        
        valid_grades = ["Excellent", "Good", "Fair", "Needs Improvement", "Critical"]
        for fw in data["frameworks"]:
            assert fw["grade"] in valid_grades, \
                f"Framework {fw['framework_name']} has invalid grade: {fw['grade']}"
        
        print(f"✓ All framework grades are valid")

    def test_total_frameworks_matches_array_length(self, auth_headers):
        """Test that total_frameworks matches frameworks array length"""
        response = requests.get(
            f"{BASE_URL}/api/control-effectiveness/dashboard",
            headers=auth_headers
        )
        data = response.json()
        
        assert data["total_frameworks"] == len(data["frameworks"]), \
            f"total_frameworks ({data['total_frameworks']}) should match array length ({len(data['frameworks'])})"
        
        print(f"✓ total_frameworks ({data['total_frameworks']}) matches array length")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
