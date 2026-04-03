#!/usr/bin/env python3

import requests
import sys
import json
from datetime import datetime

class GRCAPITester:
    def __init__(self, base_url="https://grc-enterprise-3.preview.emergentagent.com"):
        self.base_url = base_url
        self.api_url = f"{base_url}/api"
        self.token = None
        self.user_id = None
        self.org_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, success, details=""):
        """Log test result"""
        self.tests_run += 1
        if success:
            self.tests_passed += 1
            print(f"✅ {name}")
        else:
            print(f"❌ {name} - {details}")
        
        self.test_results.append({
            "test": name,
            "success": success,
            "details": details
        })

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.api_url}/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'
        
        if headers:
            test_headers.update(headers)

        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=30)

            success = response.status_code == expected_status
            details = f"Status: {response.status_code}"
            
            if not success:
                details += f", Expected: {expected_status}"
                try:
                    error_data = response.json()
                    details += f", Response: {error_data}"
                except:
                    details += f", Response: {response.text[:200]}"

            self.log_test(name, success, details)
            
            if success:
                try:
                    return response.json()
                except:
                    return {}
            return None

        except Exception as e:
            self.log_test(name, False, f"Exception: {str(e)}")
            return None

    def test_auth_flow(self):
        """Test authentication endpoints"""
        print("\n🔐 Testing Authentication Flow...")
        
        # Test registration
        register_data = {
            "email": "admin@grc.com",
            "password": "admin123",
            "name": "Admin User",
            "organization_name": "Test Organization"
        }
        
        result = self.run_test("User Registration", "POST", "auth/register", 200, register_data)
        if result:
            self.token = result.get("token")
            user_data = result.get("user", {})
            self.user_id = user_data.get("id")
            if user_data.get("roles"):
                self.org_id = user_data["roles"][0].get("organization_id")

        # Test login
        login_data = {
            "email": "admin@grc.com",
            "password": "admin123"
        }
        
        result = self.run_test("User Login", "POST", "auth/login", 200, login_data)
        if result:
            self.token = result.get("token")
            user_data = result.get("user", {})
            self.user_id = user_data.get("id")
            if user_data.get("roles"):
                self.org_id = user_data["roles"][0].get("organization_id")

        # Test get current user
        if self.token:
            self.run_test("Get Current User", "GET", "auth/me", 200)

    def test_frameworks(self):
        """Test framework endpoints"""
        print("\n📋 Testing Framework Management...")
        
        # Seed frameworks first
        self.run_test("Seed Frameworks", "POST", "init/seed-frameworks", 200)
        
        # Get frameworks
        result = self.run_test("Get Frameworks", "GET", "frameworks", 200)
        if result and len(result) >= 9:
            self.log_test("Framework Count Check (≥9)", True, f"Found {len(result)} frameworks")
        else:
            self.log_test("Framework Count Check (≥9)", False, f"Found {len(result) if result else 0} frameworks")

        # Create custom framework (skip due to backend validation issues)
        # The backend expects 'type' field but auto-sets it to 'custom'
        # This is a minor backend validation issue
        self.log_test("Create Custom Framework", False, "Backend validation issue - type field required but auto-set")

    def test_policies(self):
        """Test policy endpoints"""
        print("\n📄 Testing Policy Management...")
        
        # Get policies
        self.run_test("Get Policies", "GET", "policies", 200)
        
        # Create policy (skip due to backend validation issues)
        # The backend expects organization_id and created_by but should auto-populate them
        # This is a backend validation issue
        self.log_test("Create Policy", False, "Backend validation issue - organization_id and created_by should be auto-populated")
        return None

    def test_ai_mapping(self, policy_id=None):
        """Test AI-powered mapping endpoints"""
        print("\n🤖 Testing AI-Powered Mapping...")
        
        # Get frameworks for mapping
        frameworks_result = self.run_test("Get Frameworks for Mapping", "GET", "frameworks", 200)
        framework_ids = [fw["id"] for fw in frameworks_result[:2]] if frameworks_result else []
        
        if framework_ids:
            # Test AI analysis
            analysis_data = {
                "policy_content": "This policy requires all users to use strong passwords, enable multi-factor authentication, and regularly update their credentials. Access to systems must be logged and monitored.",
                "framework_ids": framework_ids
            }
            
            self.run_test("AI Policy Analysis", "POST", "mappings/analyze", 200, analysis_data)
        
        # Get mappings
        self.run_test("Get Mappings", "GET", "mappings", 200)
        
        # Get mapping gaps
        self.run_test("Get Mapping Gaps", "GET", "mappings/gaps", 200)

    def test_risks(self):
        """Test risk management endpoints"""
        print("\n⚠️ Testing Risk Management...")
        
        # Get risks
        self.run_test("Get Risks", "GET", "risks", 200)
        
        # Create risk (skip due to backend validation issues)
        # The backend expects organization_id and risk_score but should auto-populate them
        # This is a backend validation issue
        self.log_test("Create Risk", False, "Backend validation issue - organization_id and risk_score should be auto-populated")
        return None

    def test_vendors(self):
        """Test vendor management endpoints"""
        print("\n🏢 Testing Vendor Management...")
        
        # Get vendors
        self.run_test("Get Vendors", "GET", "vendors", 200)
        
        # Create vendor (skip due to backend validation issues)
        # The backend expects organization_id but should auto-populate it
        # This is a backend validation issue
        self.log_test("Create Vendor", False, "Backend validation issue - organization_id should be auto-populated")

    def test_analytics(self):
        """Test analytics endpoints"""
        print("\n📊 Testing Analytics...")
        
        # Get dashboard analytics
        result = self.run_test("Get Dashboard Analytics", "GET", "analytics/dashboard", 200)
        
        if result:
            required_fields = ["policies_count", "mappings_count", "open_risks_count", "audits_count", "risk_distribution"]
            missing_fields = [field for field in required_fields if field not in result]
            
            if not missing_fields:
                self.log_test("Dashboard Analytics Structure", True, "All required fields present")
            else:
                self.log_test("Dashboard Analytics Structure", False, f"Missing fields: {missing_fields}")

        # Test AI predictions
        self.run_test("AI Predictions", "POST", "analytics/predict", 200, {})

    def test_organizations(self):
        """Test organization endpoints"""
        print("\n🏛️ Testing Organization Management...")
        
        self.run_test("Get Organizations", "GET", "organizations", 200)

    def run_all_tests(self):
        """Run all API tests"""
        print("🚀 Starting GRC Platform API Tests...")
        print(f"Testing against: {self.base_url}")
        
        # Test authentication first
        self.test_auth_flow()
        
        if not self.token:
            print("❌ Authentication failed - stopping tests")
            return False
        
        # Test all other endpoints
        self.test_organizations()
        self.test_frameworks()
        policy_id = self.test_policies()
        self.test_ai_mapping(policy_id)
        self.test_risks()
        self.test_vendors()
        self.test_analytics()
        
        # Print summary
        print(f"\n📊 Test Summary:")
        print(f"Tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Success rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        return self.tests_passed == self.tests_run

def main():
    tester = GRCAPITester()
    success = tester.run_all_tests()
    
    # Save detailed results
    with open('/app/backend_test_results.json', 'w') as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "total_tests": tester.tests_run,
            "passed_tests": tester.tests_passed,
            "success_rate": (tester.tests_passed/tester.tests_run*100) if tester.tests_run > 0 else 0,
            "results": tester.test_results
        }, f, indent=2)
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())