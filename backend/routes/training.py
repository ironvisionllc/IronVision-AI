from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List

from database import db
from utils import get_current_user, guard_demo

router = APIRouter()


@router.get("/training")
async def get_training_modules(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    modules = await db.training.find(
        {"organization_id": org_id},
        {"_id": 0, "lessons": 0}
    ).to_list(1000)

    # Attach completion info for current user
    user_id = current_user["id"]
    completions = await db.training_completions.find(
        {"user_id": user_id}, {"_id": 0}
    ).to_list(1000)
    completion_map = {c["training_id"]: c for c in completions}

    progress_docs = await db.training_progress.find(
        {"user_id": user_id, "organization_id": org_id}, {"_id": 0}
    ).to_list(1000)
    progress_map = {p["training_id"]: p.get("completed_lessons", []) for p in progress_docs}

    for mod in modules:
        mod["completed"] = mod["id"] in completion_map
        mod["quiz_score"] = completion_map.get(mod["id"], {}).get("score")
        mod["quiz_passed"] = completion_map.get(mod["id"], {}).get("passed")
        mod["completed_lessons"] = progress_map.get(mod["id"], [])
        mod["total_lessons"] = len(mod.get("lessons", []))  # Already excluded from projection, use fallback

    # Get lesson counts from a separate query
    all_modules = await db.training.find(
        {"organization_id": org_id},
        {"_id": 0, "id": 1, "lessons": 1}
    ).to_list(1000)
    lesson_count_map = {m["id"]: len(m.get("lessons", [])) for m in all_modules}
    for mod in modules:
        mod["total_lessons"] = lesson_count_map.get(mod["id"], 0)

    return modules


@router.get("/training/{training_id}")
async def get_training_detail(training_id: str, current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    module = await db.training.find_one(
        {"id": training_id, "organization_id": org_id}, {"_id": 0}
    )
    if not module:
        raise HTTPException(status_code=404, detail="Training module not found")

    user_id = current_user["id"]

    # Attach progress
    progress = await db.training_progress.find_one(
        {"training_id": training_id, "user_id": user_id, "organization_id": org_id},
        {"_id": 0}
    )
    module["completed_lessons"] = progress.get("completed_lessons", []) if progress else []

    # Attach completion
    completion = await db.training_completions.find_one(
        {"training_id": training_id, "user_id": user_id}, {"_id": 0}
    )
    module["completed"] = completion is not None
    module["quiz_score"] = completion.get("score") if completion else None
    module["quiz_passed"] = completion.get("passed") if completion else None

    return module


@router.post("/training/{training_id}/lesson/{lesson_id}/complete")
async def complete_lesson(training_id: str, lesson_id: str, current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    user_id = current_user["id"]

    progress = await db.training_progress.find_one(
        {"training_id": training_id, "user_id": user_id, "organization_id": org_id}
    )

    if progress:
        completed = progress.get("completed_lessons", [])
        if lesson_id not in completed:
            completed.append(lesson_id)
            await db.training_progress.update_one(
                {"training_id": training_id, "user_id": user_id, "organization_id": org_id},
                {"$set": {"completed_lessons": completed}}
            )
    else:
        await db.training_progress.insert_one({
            "training_id": training_id,
            "user_id": user_id,
            "organization_id": org_id,
            "completed_lessons": [lesson_id]
        })

    return {"status": "ok", "completed_lessons": (progress or {}).get("completed_lessons", []) + ([lesson_id] if not progress or lesson_id not in (progress or {}).get("completed_lessons", []) else [])}


@router.get("/training/{training_id}/quiz")
async def get_quiz(training_id: str, current_user: Dict = Depends(get_current_user)):
    quiz = await db.quizzes.find_one({"training_id": training_id}, {"_id": 0})
    if not quiz:
        raise HTTPException(status_code=404, detail="No quiz found for this training")
    # Strip correct answers so frontend can't cheat
    safe_questions = []
    for q in quiz.get("questions", []):
        safe_questions.append({
            "question": q["question"],
            "options": q["options"]
        })
    return {
        "id": quiz["id"],
        "training_id": quiz["training_id"],
        "passing_score": quiz.get("passing_score", 70),
        "questions": safe_questions,
        "total_questions": len(safe_questions)
    }


@router.post("/training/{training_id}/quiz/submit")
async def submit_quiz(training_id: str, data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    quiz = await db.quizzes.find_one({"training_id": training_id}, {"_id": 0})
    if not quiz:
        raise HTTPException(status_code=404, detail="Quiz not found")

    answers = data.get("answers", [])
    questions = quiz.get("questions", [])
    correct = 0
    results = []

    for i, q in enumerate(questions):
        user_answer = answers[i] if i < len(answers) else -1
        is_correct = user_answer == q.get("correct_answer")
        if is_correct:
            correct += 1
        results.append({
            "question": q["question"],
            "user_answer": user_answer,
            "correct_answer": q["correct_answer"],
            "is_correct": is_correct
        })

    total = len(questions)
    score = int((correct / total) * 100) if total > 0 else 0
    passed = score >= quiz.get("passing_score", 70)

    # Save or update completion
    user_id = current_user["id"]
    existing = await db.training_completions.find_one(
        {"training_id": training_id, "user_id": user_id}
    )
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    if existing:
        # Update if new score is higher
        if score > (existing.get("score") or 0):
            await db.training_completions.update_one(
                {"training_id": training_id, "user_id": user_id},
                {"$set": {"score": score, "passed": passed, "completed_at": now}}
            )
    else:
        import uuid
        await db.training_completions.insert_one({
            "id": str(uuid.uuid4()),
            "training_id": training_id,
            "user_id": user_id,
            "score": score,
            "passed": passed,
            "completed_at": now
        })

    return {
        "score": score,
        "passed": passed,
        "correct_answers": correct,
        "total_questions": total,
        "passing_score": quiz.get("passing_score", 70),
        "results": results
    }
