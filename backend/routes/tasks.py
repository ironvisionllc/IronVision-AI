from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, Any
from datetime import datetime, timezone

from database import db
from models import Task, TaskCreate
from utils import get_current_user, guard_demo, log_activity
from routes.notifications import create_notification

router = APIRouter()


@router.get("/tasks")
async def get_tasks(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    tasks = await db.tasks.find({"organization_id": org_id}, {"_id": 0}).to_list(1000)
    return tasks


@router.post("/tasks")
async def create_task(data: TaskCreate, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    assignee_name = None
    if data.assignee_id:
        assignee = await db.users.find_one({"id": data.assignee_id}, {"_id": 0, "name": 1})
        assignee_name = assignee.get("name") if assignee else None

    task = Task(
        organization_id=org_id,
        title=data.title,
        description=data.description,
        status=data.status,
        priority=data.priority,
        assignee_id=data.assignee_id,
        assignee_name=assignee_name,
        due_date=data.due_date,
        related_framework_id=data.related_framework_id,
        related_control_id=data.related_control_id,
        tags=data.tags,
        created_by=current_user["id"]
    )

    doc = task.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    doc["updated_at"] = doc["updated_at"].isoformat()
    await db.tasks.insert_one(doc)

    await log_activity(org_id, current_user["id"], current_user.get("name", ""), "task_created", f"Created task: {data.title}")

    # Notify assignee if task is assigned
    if data.assignee_id and data.assignee_id != current_user["id"]:
        await create_notification(
            org_id, data.assignee_id,
            "New Task Assigned",
            f"You've been assigned: {data.title}",
            "task", "/tasks"
        )

    doc.pop("_id", None)
    return doc


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, data: Dict[str, Any], current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    update_data = {k: v for k, v in data.items() if k in ["title", "description", "status", "priority", "assignee_id", "due_date", "tags"]}
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()

    if "assignee_id" in update_data and update_data["assignee_id"]:
        assignee = await db.users.find_one({"id": update_data["assignee_id"]}, {"_id": 0, "name": 1})
        update_data["assignee_name"] = assignee.get("name") if assignee else None

    result = await db.tasks.update_one({"id": task_id, "organization_id": org_id}, {"$set": update_data})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")

    await log_activity(org_id, current_user["id"], current_user.get("name", ""), "task_updated", f"Updated task: {data.get('title', task_id)}")

    return {"message": "Task updated successfully"}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, current_user: Dict = Depends(get_current_user)):
    guard_demo(current_user)
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    result = await db.tasks.delete_one({"id": task_id, "organization_id": org_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"message": "Task deleted successfully"}


@router.get("/tasks/stats")
async def get_task_stats(current_user: Dict = Depends(get_current_user)):
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    tasks = await db.tasks.find({"organization_id": org_id}, {"_id": 0}).to_list(1000)

    stats = {"todo": 0, "in_progress": 0, "review": 0, "done": 0, "total": len(tasks), "overdue": 0}
    now = datetime.now(timezone.utc).isoformat()[:10]

    for t in tasks:
        s = t.get("status", "todo")
        if s in stats:
            stats[s] += 1
        if t.get("due_date") and t["due_date"] < now and s != "done":
            stats["overdue"] += 1

    return stats
