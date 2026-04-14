import requests
import sys
import json
from datetime import datetime

class IronVisionAPITester:
    def __init__(self, base_url="https://compliance-ingestion.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        test_headers = {'Content-Type': 'application/json'}
        if self.token:
            test_headers['Authorization'] = f'Bearer {self.token}'
        if headers:
            test_headers.update(headers)

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        print(f"   URL: {url}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=test_headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=test_headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=test_headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=test_headers, timeout=10)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    response_data = response.json()
                    if isinstance(response_data, dict) and len(str(response_data)) < 200:
                        print(f"   Response: {response_data}")
                except:
                    pass
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    error_data = response.json()
                    print(f"   Error: {error_data}")
                except:
                    print(f"   Error: {response.text[:200]}")
                self.failed_tests.append(f"{name}: Expected {expected_status}, got {response.status_code}")

            return success, response.json() if response.content else {}

        except requests.exceptions.Timeout:
            print(f"❌ Failed - Request timeout")
            self.failed_tests.append(f"{name}: Request timeout")
            return False, {}
        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            self.failed_tests.append(f"{name}: {str(e)}")
            return False, {}

    def test_login(self, email, password):
        """Test login and get token"""
        success, response = self.run_test(
            "Login",
            "POST",
            "auth/login",
            200,
            data={"email": email, "password": password}
        )
        if success and 'token' in response:
            self.token = response['token']
            print(f"   Token obtained: {self.token[:20]}...")
            return True, response.get('user', {})
        return False, {}

    def test_auth_endpoints(self):
        """Test authentication endpoints"""
        print("\n" + "="*50)
        print("TESTING AUTHENTICATION ENDPOINTS")
        print("="*50)
        
        # Test login with demo admin
        login_success, user_data = self.test_login("demo-admin@grc.com", "DemoAdmin123!")
        if not login_success:
            print("❌ Login failed, stopping auth tests")
            return False
            
        # Test /auth/me
        self.run_test("Get Current User", "GET", "auth/me", 200)
        
        # Test organizations
        self.run_test("Get Organizations", "GET", "organizations", 200)
        
        return True

    def test_dashboard_endpoints(self):
        """Test dashboard and analytics endpoints"""
        print("\n" + "="*50)
        print("TESTING DASHBOARD ENDPOINTS")
        print("="*50)
        
        self.run_test("Dashboard Analytics", "GET", "analytics/dashboard", 200)
        self.run_test("Executive Summary", "GET", "reports/executive-summary", 200)
        self.run_test("Compliance Trends", "GET", "compliance-trends", 200)

    def test_frameworks_endpoints(self):
        """Test frameworks endpoints"""
        print("\n" + "="*50)
        print("TESTING FRAMEWORKS ENDPOINTS")
        print("="*50)
        
        self.run_test("Get Frameworks", "GET", "frameworks", 200)
        self.run_test("Get Framework Controls", "GET", "frameworks/controls", 200)

    def test_policies_endpoints(self):
        """Test policies endpoints"""
        print("\n" + "="*50)
        print("TESTING POLICIES ENDPOINTS")
        print("="*50)
        
        self.run_test("Get Policies", "GET", "policies", 200)

    def test_risks_endpoints(self):
        """Test risks endpoints"""
        print("\n" + "="*50)
        print("TESTING RISKS ENDPOINTS")
        print("="*50)
        
        self.run_test("Get Risks", "GET", "risks", 200)

    def test_tasks_endpoints(self):
        """Test tasks endpoints"""
        print("\n" + "="*50)
        print("TESTING TASKS ENDPOINTS")
        print("="*50)
        
        self.run_test("Get Tasks", "GET", "tasks", 200)

    def test_vendors_endpoints(self):
        """Test vendors endpoints"""
        print("\n" + "="*50)
        print("TESTING VENDORS ENDPOINTS")
        print("="*50)
        
        self.run_test("Get Vendors", "GET", "vendors", 200)

    def test_mappings_endpoints(self):
        """Test mappings endpoints"""
        print("\n" + "="*50)
        print("TESTING MAPPINGS ENDPOINTS")
        print("="*50)
        
        self.run_test("Get Mappings", "GET", "mappings", 200)

    def test_audits_endpoints(self):
        """Test audits endpoints"""
        print("\n" + "="*50)
        print("TESTING AUDITS ENDPOINTS")
        print("="*50)
        
        self.run_test("Get Audits", "GET", "audits", 200)

    def test_training_endpoints(self):
        """Test training endpoints"""
        print("\n" + "="*50)
        print("TESTING TRAINING ENDPOINTS")
        print("="*50)
        
        self.run_test("Get Training", "GET", "training", 200)

    def test_evidence_endpoints(self):
        """Test evidence endpoints"""
        print("\n" + "="*50)
        print("TESTING EVIDENCE ENDPOINTS")
        print("="*50)
        
        self.run_test("Get Evidence", "GET", "evidence", 200)

    def test_activity_endpoints(self):
        """Test activity endpoints"""
        print("\n" + "="*50)
        print("TESTING ACTIVITY ENDPOINTS")
        print("="*50)
        
        self.run_test("Get Activity", "GET", "activity", 200)

    def test_notifications_endpoints(self):
        """Test notifications endpoints"""
        print("\n" + "="*50)
        print("TESTING NOTIFICATIONS ENDPOINTS")
        print("="*50)
        
        self.run_test("Get Notifications", "GET", "notifications", 200)

    def test_policy_builder_endpoints(self):
        """Test policy builder endpoints"""
        print("\n" + "="*50)
        print("TESTING POLICY BUILDER ENDPOINTS")
        print("="*50)
        
        self.run_test("Get Control Families", "GET", "policy-builder/control-families", 200)

def main():
    print("🚀 Starting IronVision GRC Platform API Tests")
    print(f"⏰ Test started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Setup
    tester = IronVisionAPITester()
    
    # Run authentication tests first
    if not tester.test_auth_endpoints():
        print("\n❌ Authentication failed, stopping all tests")
        return 1
    
    # Run all endpoint tests
    test_methods = [
        tester.test_dashboard_endpoints,
        tester.test_frameworks_endpoints,
        tester.test_policies_endpoints,
        tester.test_risks_endpoints,
        tester.test_tasks_endpoints,
        tester.test_vendors_endpoints,
        tester.test_mappings_endpoints,
        tester.test_audits_endpoints,
        tester.test_training_endpoints,
        tester.test_evidence_endpoints,
        tester.test_activity_endpoints,
        tester.test_notifications_endpoints,
        tester.test_policy_builder_endpoints,
    ]
    
    for test_method in test_methods:
        try:
            test_method()
        except Exception as e:
            print(f"❌ Test method {test_method.__name__} failed: {str(e)}")
    
    # Print final results
    print("\n" + "="*60)
    print("FINAL TEST RESULTS")
    print("="*60)
    print(f"📊 Tests passed: {tester.tests_passed}/{tester.tests_run}")
    print(f"📈 Success rate: {(tester.tests_passed/tester.tests_run*100):.1f}%")
    
    if tester.failed_tests:
        print(f"\n❌ Failed tests ({len(tester.failed_tests)}):")
        for i, failure in enumerate(tester.failed_tests, 1):
            print(f"   {i}. {failure}")
    
    print(f"\n⏰ Test completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    return 0 if tester.tests_passed == tester.tests_run else 1

if __name__ == "__main__":
    sys.exit(main())