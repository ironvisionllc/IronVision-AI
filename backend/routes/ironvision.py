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



# ── Get Single Generated Policy with Full Content ─────────────────────
@router.get("/ironvision/generated-policies/{policy_id}")
async def get_generated_policy(policy_id: str, current_user: Dict = Depends(get_current_user)):
    """Fetch a single generated policy with full content from Atlas."""
    from bson import ObjectId
    
    iv_db = get_ironvision_db()
    if iv_db is None:
        raise HTTPException(status_code=503, detail="IronVision Atlas not configured")
    
    try:
        oid = ObjectId(policy_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid policy ID format")
    
    policy = await iv_db.createdpolicies.find_one({"_id": oid})
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    # Serialize the policy
    result = {
        "id": str(policy["_id"]),
        "policyName": policy.get("policyName", "Untitled"),
        "framework": policy.get("framework", ""),
        "controlFamily": policy.get("controlFamily", ""),
        "companyName": policy.get("companyName", ""),
        "companyAddress": policy.get("companyAddress", ""),
        "status": policy.get("status", "draft"),
        "version": policy.get("version", 1),
        "content": policy.get("content", {}),
        "citations": policy.get("citations", {}),
        "generationMetadata": policy.get("generationMetadata", {}),
        "createdAt": policy.get("createdAt", "").isoformat() if hasattr(policy.get("createdAt"), "isoformat") else str(policy.get("createdAt", "")),
        "updatedAt": policy.get("updatedAt", "").isoformat() if hasattr(policy.get("updatedAt"), "isoformat") else str(policy.get("updatedAt", "")),
    }
    
    return result


# ── List All Generated Policies ───────────────────────────────────────
@router.get("/ironvision/generated-policies")
async def list_generated_policies(
    current_user: Dict = Depends(get_current_user),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
):
    """List all generated policies from Atlas with pagination."""
    iv_db = get_ironvision_db()
    if iv_db is None:
        raise HTTPException(status_code=503, detail="IronVision Atlas not configured")
    
    skip = (page - 1) * limit
    
    # Get total count
    total = await iv_db.createdpolicies.count_documents({})
    
    # Fetch policies
    policies = await iv_db.createdpolicies.find({}).sort("createdAt", -1).skip(skip).limit(limit).to_list(limit)
    
    result = []
    for p in policies:
        result.append({
            "id": str(p["_id"]),
            "policyName": p.get("policyName", "Untitled"),
            "framework": p.get("framework", ""),
            "controlFamily": p.get("controlFamily", ""),
            "companyName": p.get("companyName", ""),
            "status": p.get("status", "draft"),
            "version": p.get("version", 1),
            "qualityScore": p.get("generationMetadata", {}).get("qualityScore"),
            "qualityLevel": p.get("generationMetadata", {}).get("qualityLevel"),
            "createdAt": p.get("createdAt", "").isoformat() if hasattr(p.get("createdAt"), "isoformat") else str(p.get("createdAt", "")),
        })
    
    return {
        "policies": result,
        "total": total,
        "page": page,
        "limit": limit,
        "pages": (total + limit - 1) // limit
    }


# ── Export Policy as HTML/Text ────────────────────────────────────────
@router.get("/ironvision/generated-policies/{policy_id}/export")
async def export_generated_policy(
    policy_id: str,
    format: str = Query("html", regex="^(html|text|markdown)$"),
    current_user: Dict = Depends(get_current_user)
):
    """Export a generated policy in HTML, text, or markdown format."""
    from bson import ObjectId
    
    iv_db = get_ironvision_db()
    if iv_db is None:
        raise HTTPException(status_code=503, detail="IronVision Atlas not configured")
    
    try:
        oid = ObjectId(policy_id)
    except:
        raise HTTPException(status_code=400, detail="Invalid policy ID format")
    
    policy = await iv_db.createdpolicies.find_one({"_id": oid})
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    
    content = policy.get("content", {})
    header = content.get("header", {})
    sections = content.get("sections", [])
    
    policy_name = policy.get("policyName", "Untitled Policy")
    company_name = policy.get("companyName", header.get("preparedBy", "Organization"))
    
    if format == "html":
        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>{policy_name}</title>
    <style>
        body {{ font-family: 'Segoe UI', Arial, sans-serif; max-width: 900px; margin: 0 auto; padding: 40px; line-height: 1.6; }}
        h1 {{ color: #1a365d; border-bottom: 3px solid #2c5282; padding-bottom: 10px; }}
        h2 {{ color: #2c5282; margin-top: 30px; border-bottom: 1px solid #e2e8f0; padding-bottom: 8px; }}
        h3 {{ color: #4a5568; margin-top: 20px; }}
        .header {{ background: #f7fafc; padding: 20px; border-radius: 8px; margin-bottom: 30px; }}
        .header p {{ margin: 5px 0; color: #4a5568; }}
        .section {{ margin-bottom: 30px; }}
        .subsection {{ margin-left: 20px; margin-bottom: 15px; }}
        .content {{ color: #2d3748; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; }}
        th, td {{ border: 1px solid #e2e8f0; padding: 10px; text-align: left; }}
        th {{ background: #edf2f7; }}
        .footer {{ margin-top: 50px; padding-top: 20px; border-top: 1px solid #e2e8f0; color: #718096; font-size: 0.9em; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{header.get('title', policy_name)}</h1>
        <p><strong>Prepared By:</strong> {company_name}</p>
        <p><strong>Framework:</strong> {policy.get('framework', 'NIST 800-53')}</p>
        <p><strong>Control Family:</strong> {policy.get('controlFamily', '')}</p>
        <p><strong>Version:</strong> {policy.get('version', 1)}</p>
        <p><strong>Date:</strong> {policy.get('createdAt', '').strftime('%B %d, %Y') if hasattr(policy.get('createdAt'), 'strftime') else str(policy.get('createdAt', ''))[:10]}</p>
    </div>
"""
        
        # Add sections
        section_map = {}
        for s in sections:
            if isinstance(s, str):
                section_map[s] = content.get(s, {})
            elif isinstance(s, dict):
                section_map[s.get('id', s.get('title', ''))] = s
        
        # Process each section
        for section_key in ['overview', 'roles', 'policy', 'procedures', 'enforcement', 'definitions', 'revisionHistory', 'approvals', 'distribution']:
            section_data = content.get(section_key, {})
            if section_data:
                section_title = section_key.replace('_', ' ').title()
                if section_key == 'revisionHistory':
                    section_title = 'Revision History'
                
                html += f'    <div class="section">\n        <h2>{section_title}</h2>\n'
                
                if isinstance(section_data, dict):
                    subsections = section_data.get('subsections', [])
                    for sub in subsections:
                        if isinstance(sub, dict):
                            sub_title = sub.get('title', '')
                            sub_content = sub.get('content', '')
                            if sub_title:
                                html += f'        <div class="subsection">\n            <h3>{sub_title}</h3>\n'
                            if sub_content:
                                html += f'            <div class="content"><p>{sub_content}</p></div>\n'
                            html += '        </div>\n'
                
                html += '    </div>\n'
        
        html += f"""
    <div class="footer">
        <p>Generated by IronVision AI Policy Builder</p>
        <p>This document is confidential and intended for internal use only.</p>
    </div>
</body>
</html>"""
        
        return {"format": "html", "content": html, "filename": f"{policy_name.replace(' ', '_')}.html"}
    
    elif format == "markdown":
        md = f"# {header.get('title', policy_name)}\n\n"
        md += f"**Prepared By:** {company_name}  \n"
        md += f"**Framework:** {policy.get('framework', 'NIST 800-53')}  \n"
        md += f"**Control Family:** {policy.get('controlFamily', '')}  \n"
        md += f"**Version:** {policy.get('version', 1)}  \n\n---\n\n"
        
        for section_key in ['overview', 'roles', 'policy', 'procedures', 'enforcement', 'definitions', 'revisionHistory', 'approvals', 'distribution']:
            section_data = content.get(section_key, {})
            if section_data and isinstance(section_data, dict):
                section_title = section_key.replace('_', ' ').title()
                if section_key == 'revisionHistory':
                    section_title = 'Revision History'
                
                md += f"## {section_title}\n\n"
                
                subsections = section_data.get('subsections', [])
                for sub in subsections:
                    if isinstance(sub, dict):
                        sub_title = sub.get('title', '')
                        sub_content = sub.get('content', '')
                        if sub_title:
                            md += f"### {sub_title}\n\n"
                        if sub_content:
                            md += f"{sub_content}\n\n"
        
        return {"format": "markdown", "content": md, "filename": f"{policy_name.replace(' ', '_')}.md"}
    
    else:  # text
        txt = f"{header.get('title', policy_name)}\n"
        txt += "=" * len(header.get('title', policy_name)) + "\n\n"
        txt += f"Prepared By: {company_name}\n"
        txt += f"Framework: {policy.get('framework', 'NIST 800-53')}\n"
        txt += f"Control Family: {policy.get('controlFamily', '')}\n"
        txt += f"Version: {policy.get('version', 1)}\n\n"
        txt += "-" * 50 + "\n\n"
        
        for section_key in ['overview', 'roles', 'policy', 'procedures', 'enforcement', 'definitions', 'revisionHistory', 'approvals', 'distribution']:
            section_data = content.get(section_key, {})
            if section_data and isinstance(section_data, dict):
                section_title = section_key.replace('_', ' ').upper()
                txt += f"\n{section_title}\n"
                txt += "-" * len(section_title) + "\n\n"
                
                subsections = section_data.get('subsections', [])
                for sub in subsections:
                    if isinstance(sub, dict):
                        sub_title = sub.get('title', '')
                        sub_content = sub.get('content', '')
                        if sub_title:
                            txt += f"{sub_title}\n"
                        if sub_content:
                            txt += f"{sub_content}\n\n"
        
        return {"format": "text", "content": txt, "filename": f"{policy_name.replace(' ', '_')}.txt"}
