"""
IronVision Policy Builder Routes
Proxies to IronVision's MongoDB Atlas for Policy Builder data:
- Control questions/questionnaires
- Policy drafts and generated policies
- Analysis reports
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Dict, Optional
from datetime import datetime, timezone

from utils import get_current_user
from ironvision_db import get_ironvision_db

router = APIRouter()


def serialize_doc(doc):
    """Convert MongoDB document to JSON-serializable dict."""
    if doc is None:
        return None
    out = {}
    for k, v in doc.items():
        if k == "_id":
            out["_id"] = str(v)
        elif hasattr(v, "isoformat"):
            out[k] = v.isoformat()
        elif isinstance(v, dict):
            out[k] = serialize_doc(v)
        elif isinstance(v, list):
            out[k] = [serialize_doc(i) if isinstance(i, dict) else str(i) if hasattr(i, '__str__') and type(i).__name__ == 'ObjectId' else i for i in v]
        else:
            out[k] = v
    return out


def serialize_list(docs):
    return [serialize_doc(d) for d in docs]


# ── Dashboard Stats ──────────────────────────────────────────────────
@router.get("/ironvision/dashboard-stats")
async def iv_dashboard_stats(current_user: Dict = Depends(get_current_user)):
    iv_db = get_ironvision_db()
    if iv_db is None:
        raise HTTPException(status_code=503, detail="IronVision Atlas not configured")

    user_id = current_user.get("id", "")

    total_policies = await iv_db.createdpolicies.count_documents({"userId": user_id})
    total_reports = await iv_db.filerecords.count_documents({
        "userId": user_id, "status": {"$in": ["Analysis Completed", "analyzed"]}
    })
    active_analyses = await iv_db.filerecords.count_documents({
        "userId": user_id, "status": {"$in": ["Processing", "Analyzing"]}
    })
    drafts_count = await iv_db.controlquestionanswers.count_documents({
        "userId": user_id, "status": "draft"
    })

    # Recent documents
    recent_policies = await iv_db.createdpolicies.find(
        {"userId": user_id}
    ).sort("createdAt", -1).limit(5).to_list(5)

    recent_files = await iv_db.filerecords.find(
        {"userId": user_id}
    ).sort("createdAt", -1).limit(5).to_list(5)

    recent_docs = []
    for p in recent_policies:
        recent_docs.append({
            "id": str(p["_id"]),
            "name": p.get("policyName", "Untitled"),
            "type": "created",
            "framework": p.get("framework", ""),
            "controlFamily": p.get("controlFamily", ""),
            "status": p.get("status", "draft"),
            "date": p.get("createdAt", datetime.now(timezone.utc)).isoformat() if hasattr(p.get("createdAt"), "isoformat") else str(p.get("createdAt", "")),
        })
    for f in recent_files:
        recent_docs.append({
            "id": str(f["_id"]),
            "name": f.get("originalName", "Untitled"),
            "type": "file",
            "framework": f.get("framework", ""),
            "controlFamily": f.get("controlFamily", ""),
            "status": f.get("status", ""),
            "date": f.get("createdAt", datetime.now(timezone.utc)).isoformat() if hasattr(f.get("createdAt"), "isoformat") else str(f.get("createdAt", "")),
        })

    recent_docs.sort(key=lambda x: x["date"], reverse=True)

    return {
        "stats": {
            "totalPolicies": total_policies,
            "totalReports": total_reports,
            "activeAnalyses": active_analyses,
            "drafts": drafts_count,
        },
        "recentDocuments": recent_docs[:8],
    }


# ── Policies Unified List ─────────────────────────────────────────────
@router.get("/ironvision/policies")
async def iv_policies_list(
    current_user: Dict = Depends(get_current_user),
    page: int = Query(1, ge=1),
    limit: int = Query(30, ge=1, le=100),
    tab: str = Query("all"),
    search: str = Query(""),
):
    iv_db = get_ironvision_db()
    if iv_db is None:
        raise HTTPException(status_code=503, detail="IronVision Atlas not configured")

    user_id = current_user.get("id", "")
    skip = (page - 1) * limit
    items = []

    # Fetch drafts
    drafts = await iv_db.controlquestionanswers.find(
        {"userId": user_id, "status": "draft"}
    ).sort("updatedAt", -1).to_list(500)

    for d in drafts:
        items.append({
            "id": str(d["_id"]),
            "name": d.get("policyName", "Untitled Draft"),
            "framework": d.get("framework", ""),
            "controlFamily": d.get("controlFamily", ""),
            "status": "draft",
            "type": "draft",
            "answeredCount": len([v for v in d.get("answers", {}).values() if v]),
            "createdAt": d.get("createdAt", ""),
            "updatedAt": d.get("updatedAt", ""),
        })

    # Fetch created policies
    policies = await iv_db.createdpolicies.find(
        {"userId": user_id}
    ).sort("createdAt", -1).to_list(500)

    for p in policies:
        items.append({
            "id": str(p["_id"]),
            "name": p.get("policyName", "Untitled"),
            "framework": p.get("framework", ""),
            "controlFamily": p.get("controlFamily", ""),
            "status": p.get("status", "draft"),
            "type": "policy",
            "version": p.get("version", 1),
            "fileRecordId": str(p["fileRecordId"]) if p.get("fileRecordId") else None,
            "createdAt": p.get("createdAt", ""),
            "updatedAt": p.get("updatedAt", ""),
        })

    # Fetch file records (uploaded documents)
    files = await iv_db.filerecords.find(
        {"userId": user_id}
    ).sort("createdAt", -1).to_list(500)

    for f in files:
        items.append({
            "id": str(f["_id"]),
            "name": f.get("originalName", "Untitled"),
            "framework": f.get("framework", ""),
            "controlFamily": f.get("controlFamily", ""),
            "status": f.get("status", "").lower().replace(" ", "_").replace("_completed", "ed") if f.get("status") else "",
            "type": "file",
            "jobId": f.get("jobId", ""),
            "createdAt": f.get("createdAt", ""),
            "updatedAt": f.get("updatedAt", ""),
        })

    # Serialize dates
    for item in items:
        for key in ["createdAt", "updatedAt"]:
            val = item.get(key)
            if val and hasattr(val, "isoformat"):
                item[key] = val.isoformat()
            elif val:
                item[key] = str(val)

    # Filter by tab
    if tab == "drafts":
        items = [i for i in items if i["status"] == "draft"]
    elif tab == "processing":
        items = [i for i in items if i["status"] in ("processing", "generating")]
    elif tab == "ready":
        items = [i for i in items if i["status"] in ("ready", "analyzing", "ready_for_analysis")]
    elif tab == "analyzed":
        items = [i for i in items if i["status"] in ("analyzed", "analysis_completed")]

    # Search
    if search:
        sq = search.lower()
        items = [i for i in items if sq in i["name"].lower() or sq in i.get("framework", "").lower()]

    total = len(items)
    paginated = items[skip:skip + limit]

    return {
        "success": True,
        "data": paginated,
        "stats": {
            "total": total,
            "drafts": sum(1 for i in items if i["status"] == "draft"),
            "processing": sum(1 for i in items if i["status"] in ("processing", "generating")),
            "ready": sum(1 for i in items if i["status"] in ("ready", "analyzing")),
            "completed": sum(1 for i in items if i["status"] in ("analyzed", "analysis_completed")),
        },
        "pagination": {"total": total, "pages": max(1, (total + limit - 1) // limit), "page": page, "limit": limit},
    }


# ── Control Questions (Questionnaires) ──────────────────────────────
@router.get("/ironvision/control-questions")
async def iv_control_questions(
    framework: str = Query(...),
    controlFamily: str = Query(...),
    current_user: Dict = Depends(get_current_user),
):
    iv_db = get_ironvision_db()
    if iv_db is None:
        raise HTTPException(status_code=503, detail="IronVision Atlas not configured")

    questions = await iv_db.controlquestions.find(
        {"framework": framework, "controlFamily": controlFamily}
    ).to_list(200)

    return serialize_list(questions)


# ── Frameworks Dropdown ──────────────────────────────────────────────
@router.get("/ironvision/dropdowns/frameworks")
async def iv_frameworks_dropdown(current_user: Dict = Depends(get_current_user)):
    iv_db = get_ironvision_db()
    if iv_db is None:
        raise HTTPException(status_code=503, detail="IronVision Atlas not configured")

    frameworks = await iv_db.frameworks.find({}).to_list(50)
    if not frameworks:
        # Fallback: return known frameworks
        return [
            {"_id": "1", "label": "nist-800-53", "value": "nist-800-53", "displayName": "NIST 800-53"},
            {"_id": "2", "label": "cis-controls-v8", "value": "cis-controls-v8", "displayName": "CIS Controls v8"},
            {"_id": "3", "label": "fedramp-high", "value": "fedramp-high", "displayName": "FedRAMP High"},
            {"_id": "4", "label": "fedramp-moderate", "value": "fedramp-moderate", "displayName": "FedRAMP Moderate"},
            {"_id": "5", "label": "hipaa-security-rule", "value": "hipaa-security-rule", "displayName": "HIPAA Security Rule"},
            {"_id": "6", "label": "nist-csf-2.0", "value": "nist-csf-2.0", "displayName": "NIST CSF 2.0"},
        ]
    return serialize_list(frameworks)


@router.get("/ironvision/dropdowns/control-families")
async def iv_control_families_dropdown(
    framework: str = Query(...),
    current_user: Dict = Depends(get_current_user),
):
    iv_db = get_ironvision_db()
    if iv_db is None:
        raise HTTPException(status_code=503, detail="IronVision Atlas not configured")

    families = await iv_db.controlfamilies.find({"framework": framework}).to_list(100)
    if not families:
        families = await iv_db.controlFamilies.find({"framework": framework}).to_list(100)
    return serialize_list(families)


# ── Analysis Reports ─────────────────────────────────────────────────
@router.get("/ironvision/analysis-reports")
async def iv_analysis_reports(current_user: Dict = Depends(get_current_user)):
    iv_db = get_ironvision_db()
    if iv_db is None:
        raise HTTPException(status_code=503, detail="IronVision Atlas not configured")

    user_id = current_user.get("id", "")

    reports = await iv_db.filerecords.find(
        {"userId": user_id, "status": {"$in": ["Analysis Completed", "analyzed"]}}
    ).sort("updatedAt", -1).to_list(100)

    result = []
    for r in reports:
        result.append({
            "id": str(r["_id"]),
            "name": r.get("originalName", "Untitled"),
            "framework": r.get("framework", ""),
            "controlFamily": r.get("controlFamily", ""),
            "status": r.get("status", ""),
            "jobId": r.get("jobId", ""),
            "createdAt": r.get("createdAt", "").isoformat() if hasattr(r.get("createdAt"), "isoformat") else str(r.get("createdAt", "")),
            "updatedAt": r.get("updatedAt", "").isoformat() if hasattr(r.get("updatedAt"), "isoformat") else str(r.get("updatedAt", "")),
        })

    return result
