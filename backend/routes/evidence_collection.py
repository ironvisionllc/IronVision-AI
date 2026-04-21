"""
Automated Evidence Collection Engine
- Auto-collects evidence from SIEM events, pipeline scans, policy documents, and compliance assessments
- Links evidence artifacts to framework controls
- Tracks evidence freshness, coverage gaps, and collection status
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List
from datetime import datetime, timezone, timedelta
import uuid
import json
import logging

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/evidence-collection", tags=["evidence-collection"])

EVIDENCE_TYPES = {
    "siem_snapshot": {"label": "SIEM Event Snapshot", "icon": "lightning", "auto": True},
    "pipeline_report": {"label": "Pipeline Scan Report", "icon": "git-branch", "auto": True},
    "policy_document": {"label": "Policy Document", "icon": "file-text", "auto": True},
    "compliance_assessment": {"label": "Compliance Assessment", "icon": "shield-check", "auto": True},
    "checklist_mapping": {"label": "Checklist Mapping", "icon": "list-checks", "auto": True},
    "manual_upload": {"label": "Manual Upload", "icon": "upload", "auto": False},
}


@router.post("/collect")
async def run_automated_collection(current_user: Dict = Depends(get_current_user)):
    """Run automated evidence collection across all sources."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()
    collected = []

    # 1. Collect SIEM evidence snapshots
    siem_evidence = await _collect_siem_evidence(org_id, now)
    collected.extend(siem_evidence)

    # 2. Collect pipeline scan reports
    pipeline_evidence = await _collect_pipeline_evidence(org_id, now)
    collected.extend(pipeline_evidence)

    # 3. Collect approved policy documents
    policy_evidence = await _collect_policy_evidence(org_id, now)
    collected.extend(policy_evidence)

    # 4. Collect compliance assessment results
    assessment_evidence = await _collect_assessment_evidence(org_id, now)
    collected.extend(assessment_evidence)

    # 5. Collect ingested checklist mappings
    checklist_evidence = await _collect_checklist_evidence(org_id, now)
    collected.extend(checklist_evidence)

    # Store collection run
    run_doc = {
        "id": str(uuid.uuid4()),
        "organization_id": org_id,
        "total_collected": len(collected),
        "by_type": {},
        "created_at": now,
        "created_by": current_user["id"],
    }
    for e in collected:
        t = e.get("evidence_type", "unknown")
        run_doc["by_type"][t] = run_doc["by_type"].get(t, 0) + 1

    await db.evidence_collection_runs.insert_one(run_doc)

    return {
        "message": f"Collected {len(collected)} evidence artifacts",
        "total": len(collected),
        "by_type": run_doc["by_type"],
        "run_id": run_doc["id"],
    }


@router.get("/artifacts")
async def list_evidence_artifacts(current_user: Dict = Depends(get_current_user)):
    """List all collected evidence artifacts."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    artifacts = await db.evidence_artifacts.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("collected_at", -1).to_list(500)
    return artifacts


@router.get("/artifacts/{artifact_id}")
async def get_artifact_detail(artifact_id: str, current_user: Dict = Depends(get_current_user)):
    """Get evidence artifact detail."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    artifact = await db.evidence_artifacts.find_one(
        {"id": artifact_id, "organization_id": org_id}, {"_id": 0}
    )
    if not artifact:
        raise HTTPException(404, "Artifact not found")
    return artifact


@router.delete("/artifacts/{artifact_id}")
async def delete_artifact(artifact_id: str, current_user: Dict = Depends(get_current_user)):
    """Delete an evidence artifact."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    result = await db.evidence_artifacts.delete_one(
        {"id": artifact_id, "organization_id": org_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(404, "Artifact not found")
    return {"message": "Artifact deleted"}


@router.get("/coverage")
async def get_evidence_coverage(current_user: Dict = Depends(get_current_user)):
    """Get evidence coverage analysis across all frameworks."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    frameworks = await db.frameworks.find({"type": "standard"}, {"_id": 0}).to_list(100)
    artifacts = await db.evidence_artifacts.find(
        {"organization_id": org_id}, {"_id": 0, "control_ids": 1, "evidence_type": 1, "collected_at": 1}
    ).to_list(5000)

    # Build control → evidence map
    control_evidence = {}
    for a in artifacts:
        for cid in a.get("control_ids", []):
            control_evidence.setdefault(cid, []).append({
                "type": a.get("evidence_type", ""),
                "date": a.get("collected_at", ""),
            })

    stale_threshold = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    fw_coverage = []
    total_controls_all = 0
    covered_controls_all = 0

    for fw in frameworks:
        controls = await db.controls.find(
            {"framework_id": fw["id"]}, {"_id": 0, "control_id": 1}
        ).to_list(5000)

        total = len(controls)
        covered = 0
        stale = 0
        fresh = 0

        for c in controls:
            cid = c["control_id"]
            evidence = control_evidence.get(cid, [])
            if evidence:
                covered += 1
                latest = max(e["date"] for e in evidence)
                if latest >= stale_threshold:
                    fresh += 1
                else:
                    stale += 1

        total_controls_all += total
        covered_controls_all += covered

        fw_coverage.append({
            "framework_id": fw["id"],
            "framework_name": fw["name"],
            "total_controls": total,
            "covered": covered,
            "uncovered": total - covered,
            "fresh": fresh,
            "stale": stale,
            "coverage_pct": round(covered / max(total, 1) * 100, 1),
        })

    fw_coverage.sort(key=lambda x: -x["coverage_pct"])

    return {
        "frameworks": fw_coverage,
        "summary": {
            "total_controls": total_controls_all,
            "covered": covered_controls_all,
            "coverage_pct": round(covered_controls_all / max(total_controls_all, 1) * 100, 1),
            "total_artifacts": len(artifacts),
        },
    }


@router.get("/runs")
async def list_collection_runs(current_user: Dict = Depends(get_current_user)):
    """List evidence collection run history."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    runs = await db.evidence_collection_runs.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return runs


@router.get("/stats")
async def get_evidence_stats(current_user: Dict = Depends(get_current_user)):
    """Get evidence collection statistics."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    total = await db.evidence_artifacts.count_documents({"organization_id": org_id})

    pipeline = [
        {"$match": {"organization_id": org_id}},
        {"$group": {"_id": "$evidence_type", "count": {"$sum": 1}}}
    ]
    by_type = {}
    async for doc in db.evidence_artifacts.aggregate(pipeline):
        by_type[doc["_id"]] = doc["count"]

    stale_threshold = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    fresh = await db.evidence_artifacts.count_documents(
        {"organization_id": org_id, "collected_at": {"$gte": stale_threshold}}
    )

    runs = await db.evidence_collection_runs.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(1)
    last_run = runs[0] if runs else None

    return {
        "total_artifacts": total,
        "by_type": by_type,
        "fresh": fresh,
        "stale": total - fresh,
        "last_collection": last_run,
    }


# ─── Collection Helpers ───────────────────────────────────

async def _collect_siem_evidence(org_id: str, now: str) -> list:
    """Collect SIEM event summaries as evidence."""
    collected = []
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()

    # Get SIEM summary by category
    pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$category",
            "count": {"$sum": 1},
            "critical": {"$sum": {"$cond": [{"$eq": ["$severity", "critical"]}, 1, 0]}},
            "high": {"$sum": {"$cond": [{"$eq": ["$severity", "high"]}, 1, 0]}},
            "latest": {"$max": "$timestamp"},
        }}
    ]

    from routes.control_compliance import SIEM_CONTROL_MAP
    async for doc in db.siem_events.aggregate(pipeline):
        category = doc["_id"]
        control_ids = SIEM_CONTROL_MAP.get(category, [])

        artifact = {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "evidence_type": "siem_snapshot",
            "title": f"SIEM: {category.replace('_', ' ').title()} Events (30d)",
            "description": f"{doc['count']} events ({doc['critical']} critical, {doc['high']} high) in the {category} category over the last 30 days.",
            "source": "SIEM Integration",
            "content_summary": json.dumps({
                "category": category,
                "total_events": doc["count"],
                "critical": doc["critical"],
                "high": doc["high"],
                "latest_event": doc["latest"],
                "period": "30 days",
            }),
            "control_ids": control_ids[:20],
            "collected_at": now,
            "freshness": "current",
        }

        existing = await db.evidence_artifacts.find_one({
            "organization_id": org_id,
            "evidence_type": "siem_snapshot",
            "title": artifact["title"],
        })
        if existing:
            await db.evidence_artifacts.update_one(
                {"id": existing["id"]},
                {"$set": {"content_summary": artifact["content_summary"], "collected_at": now, "description": artifact["description"]}}
            )
        else:
            await db.evidence_artifacts.insert_one(artifact)
        collected.append(artifact)

    return collected


async def _collect_pipeline_evidence(org_id: str, now: str) -> list:
    """Collect pipeline scan reports as evidence."""
    collected = []
    runs = await db.pipeline_runs.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(20)

    for run in runs:
        # Map to controls based on scan type
        from routes.pipeline import SCAN_TO_CONTROL_CATEGORIES
        from routes.control_compliance import SIEM_CONTROL_MAP
        siem_cats = SCAN_TO_CONTROL_CATEGORIES.get(run.get("scan_type", "mixed"), ["system"])
        control_ids = []
        for cat in siem_cats:
            control_ids.extend(SIEM_CONTROL_MAP.get(cat, [])[:10])

        artifact = {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "evidence_type": "pipeline_report",
            "title": f"Pipeline: {run.get('pipeline_name', 'Unknown')} — {run.get('scan_type', 'scan').upper()}",
            "description": f"{run.get('total_findings', 0)} findings from {run.get('tool_name', run.get('scan_type', 'scan'))}. Gate: {run.get('gate_result', 'pending')}. Risk score: {run.get('risk_score', 0)}.",
            "source": f"CI/CD Pipeline ({run.get('repo', '')})",
            "content_summary": json.dumps({
                "pipeline": run.get("pipeline_name", ""),
                "scan_type": run.get("scan_type", ""),
                "findings": run.get("total_findings", 0),
                "severity": run.get("severity_counts", {}),
                "gate_result": run.get("gate_result", ""),
                "risk_score": run.get("risk_score", 0),
                "repo": run.get("repo", ""),
                "branch": run.get("branch", ""),
                "commit": run.get("commit_sha", ""),
            }),
            "control_ids": list(set(control_ids))[:20],
            "collected_at": now,
            "freshness": "current" if run.get("created_at", "") >= (datetime.now(timezone.utc) - timedelta(days=7)).isoformat() else "aging",
        }

        existing = await db.evidence_artifacts.find_one({
            "organization_id": org_id,
            "evidence_type": "pipeline_report",
            "title": artifact["title"],
        })
        if not existing:
            await db.evidence_artifacts.insert_one(artifact)
            collected.append(artifact)

    return collected


async def _collect_policy_evidence(org_id: str, now: str) -> list:
    """Collect approved policy documents as evidence."""
    collected = []

    # Approved generated policies
    approved = await db.generated_templates.find(
        {"organization_id": org_id, "status": "approved"}, {"_id": 0}
    ).to_list(100)

    for pol in approved:
        # Find mapped controls
        mappings = await db.mappings.find(
            {"organization_id": org_id, "source_policy_id": pol.get("id", "")}, {"_id": 0, "control_id": 1}
        ).to_list(100)
        control_ids = [m["control_id"] for m in mappings]

        artifact = {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "evidence_type": "policy_document",
            "title": f"Policy: {pol.get('title', 'Untitled')}",
            "description": f"Approved policy document mapped to {len(control_ids)} controls.",
            "source": "Policy Center",
            "content_summary": json.dumps({
                "policy_id": pol.get("id", ""),
                "title": pol.get("title", ""),
                "status": "approved",
                "sections": len(pol.get("sections", [])),
                "mapped_controls": len(control_ids),
            }),
            "control_ids": control_ids[:30],
            "collected_at": now,
            "freshness": "current",
        }

        existing = await db.evidence_artifacts.find_one({
            "organization_id": org_id,
            "evidence_type": "policy_document",
            "title": artifact["title"],
        })
        if not existing:
            await db.evidence_artifacts.insert_one(artifact)
            collected.append(artifact)

    # Approved uploaded documents
    approved_docs = await db.document_uploads.find(
        {"organization_id": org_id, "status": "approved"}, {"_id": 0}
    ).to_list(100)

    for doc in approved_docs:
        doc_name = doc.get("filename", doc.get("original_name", "Unknown"))
        artifact = {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "evidence_type": "policy_document",
            "title": f"Document: {doc_name}",
            "description": f"Approved {doc.get('category', 'document')} — {doc_name}",
            "source": "Document Library",
            "content_summary": json.dumps({
                "document_id": doc.get("id", ""),
                "filename": doc_name,
                "category": doc.get("category", ""),
                "status": "approved",
            }),
            "control_ids": [],
            "collected_at": now,
            "freshness": "current",
        }

        existing = await db.evidence_artifacts.find_one({
            "organization_id": org_id,
            "evidence_type": "policy_document",
            "title": artifact["title"],
        })
        if not existing:
            await db.evidence_artifacts.insert_one(artifact)
            collected.append(artifact)

    return collected


async def _collect_assessment_evidence(org_id: str, now: str) -> list:
    """Collect compliance assessment results as evidence."""
    collected = []
    frameworks = await db.frameworks.find({"type": "standard"}, {"_id": 0}).to_list(100)

    for fw in frameworks:
        compliance = await db.control_compliance.find(
            {"organization_id": org_id, "framework_id": fw["id"]}, {"_id": 0}
        ).to_list(5000)

        if not compliance:
            continue

        compliant = sum(1 for c in compliance if c.get("status") == "compliant")
        partial = sum(1 for c in compliance if c.get("status") == "partial")
        non_compliant = sum(1 for c in compliance if c.get("status") == "non_compliant")
        total = await db.controls.count_documents({"framework_id": fw["id"]})
        control_ids = [c["control_id"] for c in compliance if c.get("status") in ("compliant", "partial")]

        artifact = {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "evidence_type": "compliance_assessment",
            "title": f"Assessment: {fw['name']}",
            "description": f"{compliant} compliant, {partial} partial, {non_compliant} non-compliant out of {total} controls.",
            "source": "AI Compliance Assessment",
            "content_summary": json.dumps({
                "framework": fw["name"],
                "framework_id": fw["id"],
                "total": total,
                "compliant": compliant,
                "partial": partial,
                "non_compliant": non_compliant,
                "assessed": len(compliance),
            }),
            "control_ids": control_ids[:30],
            "collected_at": now,
            "freshness": "current",
        }

        existing = await db.evidence_artifacts.find_one({
            "organization_id": org_id,
            "evidence_type": "compliance_assessment",
            "title": artifact["title"],
        })
        if existing:
            await db.evidence_artifacts.update_one(
                {"id": existing["id"]},
                {"$set": {"content_summary": artifact["content_summary"], "collected_at": now, "description": artifact["description"], "control_ids": artifact["control_ids"]}}
            )
        else:
            await db.evidence_artifacts.insert_one(artifact)
        collected.append(artifact)

    return collected


async def _collect_checklist_evidence(org_id: str, now: str) -> list:
    """Collect ingested checklist mapping results as evidence."""
    collected = []
    checklists = await db.ingested_checklists.find(
        {"organization_id": org_id, "status": "mapped"}, {"_id": 0}
    ).to_list(50)

    for cl in checklists:
        controls = await db.ingested_controls.find(
            {"checklist_id": cl["id"], "organization_id": org_id, "status": "mapped"}, {"_id": 0}
        ).to_list(5000)

        mapped_fw_controls = set()
        for c in controls:
            for m in c.get("framework_mappings", []):
                mapped_fw_controls.add(m.get("control_id", ""))

        artifact = {
            "id": str(uuid.uuid4()),
            "organization_id": org_id,
            "evidence_type": "checklist_mapping",
            "title": f"Checklist: {cl['name']}",
            "description": f"{cl.get('source_type', '').upper()} checklist — {len(controls)} controls mapped to {len(mapped_fw_controls)} framework controls.",
            "source": "Compliance Ingestion Layer",
            "content_summary": json.dumps({
                "checklist_id": cl["id"],
                "name": cl["name"],
                "source_type": cl.get("source_type", ""),
                "total_controls": cl.get("total_controls", 0),
                "mapped_controls": len(controls),
                "framework_controls_covered": len(mapped_fw_controls),
            }),
            "control_ids": list(mapped_fw_controls)[:30],
            "collected_at": now,
            "freshness": "current",
        }

        existing = await db.evidence_artifacts.find_one({
            "organization_id": org_id,
            "evidence_type": "checklist_mapping",
            "title": artifact["title"],
        })
        if existing:
            await db.evidence_artifacts.update_one(
                {"id": existing["id"]},
                {"$set": {"content_summary": artifact["content_summary"], "collected_at": now, "description": artifact["description"]}}
            )
        else:
            await db.evidence_artifacts.insert_one(artifact)
        collected.append(artifact)

    return collected
