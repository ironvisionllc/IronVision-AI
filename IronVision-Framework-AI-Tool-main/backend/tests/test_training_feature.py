"""
Test suite for Training & Awareness feature (Iteration 15)
Tests all training endpoints: modules list, module detail, lesson completion, quiz, quiz submission
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
DEMO_ADMIN_EMAIL = "demo-admin@grc.com"
DEMO_ADMIN_PASSWORD = "DemoAdmin123!"
DEMO_VIEWER_EMAIL = "demo-user@grc.com"
DEMO_VIEWER_PASSWORD = "DemoUser123!"


@pytest.fixture(scope="module")
def admin_token():
    """Get admin auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEMO_ADMIN_EMAIL,
        "password": DEMO_ADMIN_PASSWORD
    })
    assert response.status_code == 200, f"Admin login failed: {response.text}"
    data = response.json()
    # Token field is 'token' not 'access_token'
    return data.get("token")


@pytest.fixture(scope="module")
def viewer_token():
    """Get viewer auth token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": DEMO_VIEWER_EMAIL,
        "password": DEMO_VIEWER_PASSWORD
    })
    assert response.status_code == 200, f"Viewer login failed: {response.text}"
    data = response.json()
    return data.get("token")


@pytest.fixture
def admin_headers(admin_token):
    """Headers with admin auth"""
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}


@pytest.fixture
def viewer_headers(viewer_token):
    """Headers with viewer auth"""
    return {"Authorization": f"Bearer {viewer_token}", "Content-Type": "application/json"}


# ============================================================================
# GET /api/training - List all training modules
# ============================================================================
class TestTrainingModulesList:
    """Tests for GET /api/training endpoint"""

    def test_get_training_modules_returns_12_modules(self, admin_headers):
        """Verify exactly 12 training modules are returned"""
        response = requests.get(f"{BASE_URL}/api/training", headers=admin_headers)
        assert response.status_code == 200, f"Failed to get training modules: {response.text}"
        modules = response.json()
        assert isinstance(modules, list), "Response should be a list"
        assert len(modules) == 12, f"Expected 12 modules, got {len(modules)}"

    def test_modules_have_required_fields(self, admin_headers):
        """Verify each module has category, difficulty, total_lessons fields"""
        response = requests.get(f"{BASE_URL}/api/training", headers=admin_headers)
        assert response.status_code == 200
        modules = response.json()
        
        required_fields = ["id", "title", "description", "category", "difficulty", "total_lessons"]
        for mod in modules:
            for field in required_fields:
                assert field in mod, f"Module {mod.get('id', 'unknown')} missing field: {field}"

    def test_modules_have_correct_categories(self, admin_headers):
        """Verify modules have grc or platform category"""
        response = requests.get(f"{BASE_URL}/api/training", headers=admin_headers)
        assert response.status_code == 200
        modules = response.json()
        
        grc_count = sum(1 for m in modules if m["category"] == "grc")
        platform_count = sum(1 for m in modules if m["category"] == "platform")
        
        assert grc_count == 7, f"Expected 7 GRC modules, got {grc_count}"
        assert platform_count == 5, f"Expected 5 platform modules, got {platform_count}"

    def test_modules_have_valid_difficulty(self, admin_headers):
        """Verify modules have valid difficulty levels"""
        response = requests.get(f"{BASE_URL}/api/training", headers=admin_headers)
        assert response.status_code == 200
        modules = response.json()
        
        valid_difficulties = ["beginner", "intermediate", "advanced"]
        for mod in modules:
            assert mod["difficulty"] in valid_difficulties, f"Invalid difficulty: {mod['difficulty']}"

    def test_modules_have_positive_total_lessons(self, admin_headers):
        """Verify each module has at least 1 lesson"""
        response = requests.get(f"{BASE_URL}/api/training", headers=admin_headers)
        assert response.status_code == 200
        modules = response.json()
        
        for mod in modules:
            assert mod["total_lessons"] > 0, f"Module {mod['id']} has no lessons"

    def test_viewer_can_access_training_modules(self, viewer_headers):
        """Verify viewer role can access training modules"""
        response = requests.get(f"{BASE_URL}/api/training", headers=viewer_headers)
        assert response.status_code == 200, f"Viewer should be able to access training: {response.text}"
        modules = response.json()
        assert len(modules) == 12


# ============================================================================
# GET /api/training/{training_id} - Get module detail
# ============================================================================
class TestTrainingModuleDetail:
    """Tests for GET /api/training/{training_id} endpoint"""

    def test_get_module_detail_returns_lessons(self, admin_headers):
        """Verify module detail includes lessons array"""
        # Use first GRC module
        training_id = "train-grc-001"
        response = requests.get(f"{BASE_URL}/api/training/{training_id}", headers=admin_headers)
        assert response.status_code == 200, f"Failed to get module detail: {response.text}"
        
        module = response.json()
        assert "lessons" in module, "Module detail should include lessons"
        assert isinstance(module["lessons"], list), "Lessons should be a list"
        assert len(module["lessons"]) > 0, "Module should have at least one lesson"

    def test_lessons_have_required_fields(self, admin_headers):
        """Verify each lesson has id, title, order, content"""
        training_id = "train-grc-001"
        response = requests.get(f"{BASE_URL}/api/training/{training_id}", headers=admin_headers)
        assert response.status_code == 200
        
        module = response.json()
        for lesson in module["lessons"]:
            assert "id" in lesson, "Lesson missing id"
            assert "title" in lesson, "Lesson missing title"
            assert "order" in lesson, "Lesson missing order"
            assert "content" in lesson, "Lesson missing content"

    def test_module_detail_includes_progress_fields(self, admin_headers):
        """Verify module detail includes progress tracking fields"""
        training_id = "train-grc-001"
        response = requests.get(f"{BASE_URL}/api/training/{training_id}", headers=admin_headers)
        assert response.status_code == 200
        
        module = response.json()
        assert "completed_lessons" in module, "Module should have completed_lessons field"
        assert isinstance(module["completed_lessons"], list), "completed_lessons should be a list"

    def test_nonexistent_module_returns_404(self, admin_headers):
        """Verify 404 for non-existent module"""
        response = requests.get(f"{BASE_URL}/api/training/nonexistent-module", headers=admin_headers)
        assert response.status_code == 404

    def test_all_12_modules_accessible(self, admin_headers):
        """Verify all 12 modules can be accessed individually"""
        grc_ids = [f"train-grc-00{i}" for i in range(1, 8)]  # train-grc-001 to train-grc-007
        platform_ids = [f"train-plat-00{i}" for i in range(1, 6)]  # train-plat-001 to train-plat-005
        all_ids = grc_ids + platform_ids
        
        for training_id in all_ids:
            response = requests.get(f"{BASE_URL}/api/training/{training_id}", headers=admin_headers)
            assert response.status_code == 200, f"Failed to access module {training_id}: {response.text}"


# ============================================================================
# POST /api/training/{training_id}/lesson/{lesson_id}/complete - Mark lesson complete
# ============================================================================
class TestLessonCompletion:
    """Tests for POST /api/training/{training_id}/lesson/{lesson_id}/complete endpoint"""

    def test_mark_lesson_complete(self, admin_headers):
        """Verify lesson can be marked as complete"""
        training_id = "train-grc-001"
        lesson_id = "les-grc001-01"
        
        response = requests.post(
            f"{BASE_URL}/api/training/{training_id}/lesson/{lesson_id}/complete",
            headers=admin_headers
        )
        assert response.status_code == 200, f"Failed to mark lesson complete: {response.text}"
        
        data = response.json()
        assert "status" in data, "Response should have status"
        assert data["status"] == "ok", "Status should be ok"

    def test_lesson_completion_persists(self, admin_headers):
        """Verify lesson completion is persisted"""
        training_id = "train-grc-001"
        lesson_id = "les-grc001-02"
        
        # Mark complete
        requests.post(
            f"{BASE_URL}/api/training/{training_id}/lesson/{lesson_id}/complete",
            headers=admin_headers
        )
        
        # Verify in module detail
        response = requests.get(f"{BASE_URL}/api/training/{training_id}", headers=admin_headers)
        assert response.status_code == 200
        
        module = response.json()
        assert lesson_id in module.get("completed_lessons", []), "Lesson should be in completed_lessons"

    def test_viewer_can_complete_lessons(self, viewer_headers):
        """Verify viewer can also complete lessons (training is for all users)"""
        training_id = "train-plat-001"
        lesson_id = "les-plat001-01"
        
        response = requests.post(
            f"{BASE_URL}/api/training/{training_id}/lesson/{lesson_id}/complete",
            headers=viewer_headers
        )
        assert response.status_code == 200, f"Viewer should be able to complete lessons: {response.text}"


# ============================================================================
# GET /api/training/{training_id}/quiz - Get quiz questions
# ============================================================================
class TestQuizRetrieval:
    """Tests for GET /api/training/{training_id}/quiz endpoint"""

    def test_get_quiz_returns_questions(self, admin_headers):
        """Verify quiz endpoint returns questions"""
        training_id = "train-grc-001"
        response = requests.get(f"{BASE_URL}/api/training/{training_id}/quiz", headers=admin_headers)
        assert response.status_code == 200, f"Failed to get quiz: {response.text}"
        
        quiz = response.json()
        assert "questions" in quiz, "Quiz should have questions"
        assert isinstance(quiz["questions"], list), "Questions should be a list"
        assert len(quiz["questions"]) > 0, "Quiz should have at least one question"

    def test_quiz_does_not_expose_correct_answers(self, admin_headers):
        """Verify correct_answer is NOT included in quiz response (anti-cheat)"""
        training_id = "train-grc-001"
        response = requests.get(f"{BASE_URL}/api/training/{training_id}/quiz", headers=admin_headers)
        assert response.status_code == 200
        
        quiz = response.json()
        for q in quiz["questions"]:
            assert "correct_answer" not in q, "Quiz should NOT expose correct_answer to prevent cheating"

    def test_quiz_questions_have_options(self, admin_headers):
        """Verify each question has options array"""
        training_id = "train-grc-001"
        response = requests.get(f"{BASE_URL}/api/training/{training_id}/quiz", headers=admin_headers)
        assert response.status_code == 200
        
        quiz = response.json()
        for q in quiz["questions"]:
            assert "question" in q, "Question should have question text"
            assert "options" in q, "Question should have options"
            assert isinstance(q["options"], list), "Options should be a list"
            assert len(q["options"]) >= 2, "Question should have at least 2 options"

    def test_quiz_has_passing_score(self, admin_headers):
        """Verify quiz includes passing_score"""
        training_id = "train-grc-001"
        response = requests.get(f"{BASE_URL}/api/training/{training_id}/quiz", headers=admin_headers)
        assert response.status_code == 200
        
        quiz = response.json()
        assert "passing_score" in quiz, "Quiz should have passing_score"
        assert quiz["passing_score"] == 70, "Default passing score should be 70"

    def test_nonexistent_quiz_returns_404(self, admin_headers):
        """Verify 404 for non-existent quiz"""
        response = requests.get(f"{BASE_URL}/api/training/nonexistent/quiz", headers=admin_headers)
        assert response.status_code == 404


# ============================================================================
# POST /api/training/{training_id}/quiz/submit - Submit quiz answers
# ============================================================================
class TestQuizSubmission:
    """Tests for POST /api/training/{training_id}/quiz/submit endpoint"""

    def test_submit_quiz_returns_score(self, admin_headers):
        """Verify quiz submission returns score and pass/fail"""
        training_id = "train-grc-001"
        
        # First get the quiz to know how many questions
        quiz_response = requests.get(f"{BASE_URL}/api/training/{training_id}/quiz", headers=admin_headers)
        quiz = quiz_response.json()
        num_questions = len(quiz["questions"])
        
        # Submit all wrong answers (index -1 or 0 for all)
        answers = [0] * num_questions
        
        response = requests.post(
            f"{BASE_URL}/api/training/{training_id}/quiz/submit",
            headers=admin_headers,
            json={"answers": answers}
        )
        assert response.status_code == 200, f"Failed to submit quiz: {response.text}"
        
        result = response.json()
        assert "score" in result, "Result should have score"
        assert "passed" in result, "Result should have passed"
        assert "correct_answers" in result, "Result should have correct_answers count"
        assert "total_questions" in result, "Result should have total_questions"

    def test_submit_quiz_with_correct_answers_passes(self, admin_headers):
        """Verify submitting correct answers results in pass"""
        training_id = "train-grc-001"
        
        # Known correct answers for train-grc-001 quiz (from training_data.py)
        # Q1: Over 80% (index 2), Q2: Whaling (index 1), Q3: 14 chars (index 3)
        # Q4: Hardware keys (index 2), Q5: Don't click, report (index 2)
        # Q6: Following through doors (index 1), Q7: No penalty (index 1)
        correct_answers = [2, 1, 3, 2, 2, 1, 1]
        
        response = requests.post(
            f"{BASE_URL}/api/training/{training_id}/quiz/submit",
            headers=admin_headers,
            json={"answers": correct_answers}
        )
        assert response.status_code == 200
        
        result = response.json()
        assert result["score"] == 100, f"Expected 100% score with all correct answers, got {result['score']}"
        assert result["passed"] is True, "Should pass with 100% score"

    def test_submit_quiz_returns_detailed_results(self, admin_headers):
        """Verify quiz submission returns detailed per-question results"""
        training_id = "train-grc-002"
        
        # Get quiz first
        quiz_response = requests.get(f"{BASE_URL}/api/training/{training_id}/quiz", headers=admin_headers)
        quiz = quiz_response.json()
        num_questions = len(quiz["questions"])
        
        answers = [0] * num_questions
        
        response = requests.post(
            f"{BASE_URL}/api/training/{training_id}/quiz/submit",
            headers=admin_headers,
            json={"answers": answers}
        )
        assert response.status_code == 200
        
        result = response.json()
        assert "results" in result, "Result should have detailed results"
        assert len(result["results"]) == num_questions, "Should have result for each question"
        
        for r in result["results"]:
            assert "question" in r, "Result should have question text"
            assert "user_answer" in r, "Result should have user_answer"
            assert "correct_answer" in r, "Result should have correct_answer (revealed after submission)"
            assert "is_correct" in r, "Result should have is_correct"

    def test_viewer_can_submit_quiz(self, viewer_headers):
        """Verify viewer can submit quiz"""
        training_id = "train-plat-001"
        
        quiz_response = requests.get(f"{BASE_URL}/api/training/{training_id}/quiz", headers=viewer_headers)
        quiz = quiz_response.json()
        num_questions = len(quiz["questions"])
        
        answers = [0] * num_questions
        
        response = requests.post(
            f"{BASE_URL}/api/training/{training_id}/quiz/submit",
            headers=viewer_headers,
            json={"answers": answers}
        )
        assert response.status_code == 200, f"Viewer should be able to submit quiz: {response.text}"


# ============================================================================
# Module ID pattern verification
# ============================================================================
class TestModuleIdPatterns:
    """Verify module and lesson ID patterns match expected format"""

    def test_grc_module_ids(self, admin_headers):
        """Verify GRC module IDs follow pattern train-grc-00X"""
        response = requests.get(f"{BASE_URL}/api/training", headers=admin_headers)
        modules = response.json()
        
        grc_modules = [m for m in modules if m["category"] == "grc"]
        for mod in grc_modules:
            assert mod["id"].startswith("train-grc-"), f"GRC module ID should start with train-grc-: {mod['id']}"

    def test_platform_module_ids(self, admin_headers):
        """Verify platform module IDs follow pattern train-plat-00X"""
        response = requests.get(f"{BASE_URL}/api/training", headers=admin_headers)
        modules = response.json()
        
        platform_modules = [m for m in modules if m["category"] == "platform"]
        for mod in platform_modules:
            assert mod["id"].startswith("train-plat-"), f"Platform module ID should start with train-plat-: {mod['id']}"

    def test_lesson_ids_follow_pattern(self, admin_headers):
        """Verify lesson IDs follow pattern les-{module}-XX"""
        training_id = "train-grc-001"
        response = requests.get(f"{BASE_URL}/api/training/{training_id}", headers=admin_headers)
        module = response.json()
        
        for lesson in module["lessons"]:
            assert lesson["id"].startswith("les-"), f"Lesson ID should start with les-: {lesson['id']}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
