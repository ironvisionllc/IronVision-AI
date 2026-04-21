"""
OSCAL (Open Security Controls Assessment Language) Support
- Import OSCAL catalogs, component-definitions, assessment-results
- Export existing framework data as OSCAL JSON
- OSCAL v1.2.1 compatible
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from typing import Dict, List
from datetime import datetime, timezone
import uuid
import json
import logging

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/oscal", tags=["oscal"])


# ─── OSCAL Parsers ──────────────────────────────────────

def parse_oscal_catalog(data: dict) -> dict:
    """Parse OSCAL Catalog JSON → normalized controls."""
    catalog = data.get("catalog", data)
    metadata = catalog.get("metadata", {})
    name = metadata.get("title", "OSCAL Catalog")

    controls = []
    groups = catalog.get("groups", [])
    _extract_controls_from_groups(groups, controls, "")

    # Also check top-level controls
    for ctrl in catalog.get("controls", []):
        controls.append(_normalize_oscal_control(ctrl, ""))

    return {"name": name, "oscal_type": "catalog", "controls": controls, "metadata": metadata}


def parse_oscal_component_definition(data: dict) -> dict:
    """Parse OSCAL Component Definition JSON → control implementations."""
    comp_def = data.get("component-definition", data)
    metadata = comp_def.get("metadata", {})
    name = metadata.get("title", "OSCAL Component Definition")

    controls = []
    for component in comp_def.get("components", []):
        comp_title = component.get("title", "Unknown Component")
        comp_type = component.get("type", "software")

        for impl in component.get("control-implementations", []):
            source = impl.get("source", "")
            for req in impl.get("implemented-requirements", []):
                ctrl_id = req.get("control-id", "")
                desc_parts = []
                for stmt in req.get("statements", []):
                    prose = stmt.get("prose", "")
                    if prose:
                        desc_parts.append(prose)
                if not desc_parts:
                    desc_parts.append(req.get("prose", req.get("description", "")))

                controls.append({
                    "source_id": ctrl_id,
                    "title": f"{comp_title}: {ctrl_id}",
                    "description": " ".join(desc_parts)[:500],
                    "severity": _extract_severity_from_props(req.get("props", [])),
                    "category": comp_title,
                    "component_type": comp_type,
                    "implementation_status": _extract_prop(req.get("props", []), "implementation-status", "planned"),
                    "source_profile": source,
                })

    return {"name": name, "oscal_type": "component-definition", "controls": controls, "metadata": metadata}


def parse_oscal_assessment_results(data: dict) -> dict:
    """Parse OSCAL Assessment Results JSON → findings."""
    ar = data.get("assessment-results", data)
    metadata = ar.get("metadata", {})
    name = metadata.get("title", "OSCAL Assessment Results")

    controls = []
    for result in ar.get("results", []):
        result_title = result.get("title", "Assessment")
        for finding in result.get("findings", []):
            target = finding.get("target", {})
            ctrl_id = target.get("target-id", finding.get("uuid", "")[:12])
            status = target.get("status", {}).get("state", "not-satisfied")

            desc = finding.get("description", "")
            # Extract from observations if present
            obs_uuids = [r.get("observation-uuid", "") for r in finding.get("related-observations", [])]

            severity = "medium"
            for risk in finding.get("associated-risks", []):
                risk_level = risk.get("risk-level", "")
                if risk_level in ("high", "critical"):
                    severity = "high"
                elif risk_level == "low":
                    severity = "low"

            controls.append({
                "source_id": ctrl_id,
                "title": finding.get("title", f"Finding: {ctrl_id}"),
                "description": desc[:500] if desc else f"Assessment finding for {ctrl_id}",
                "severity": _extract_severity_from_props(finding.get("props", []), severity),
                "category": result_title,
                "assessment_status": status,
                "observation_refs": obs_uuids,
            })

    return {"name": name, "oscal_type": "assessment-results", "controls": controls, "metadata": metadata}


def _extract_controls_from_groups(groups: list, controls: list, parent_title: str):
    """Recursively extract controls from OSCAL groups."""
    for group in groups:
        group_title = group.get("title", "")
        full_category = f"{parent_title} > {group_title}" if parent_title else group_title

        for ctrl in group.get("controls", []):
            controls.append(_normalize_oscal_control(ctrl, full_category))
            # Handle sub-controls (enhancements)
            for sub in ctrl.get("controls", []):
                controls.append(_normalize_oscal_control(sub, full_category))

        # Nested groups
        _extract_controls_from_groups(group.get("groups", []), controls, full_category)


def _normalize_oscal_control(ctrl: dict, category: str) -> dict:
    """Normalize an OSCAL control to our unified schema."""
    ctrl_id = ctrl.get("id", "")
    title = ctrl.get("title", ctrl_id)
    prose_parts = []
    for part in ctrl.get("parts", []):
        if part.get("prose"):
            prose_parts.append(part["prose"])
        for sub in part.get("parts", []):
            if sub.get("prose"):
                prose_parts.append(sub["prose"])
    description = " ".join(prose_parts)[:500] if prose_parts else ""

    return {
        "source_id": ctrl_id,
        "title": title,
        "description": description,
        "severity": _extract_severity_from_props(ctrl.get("props", [])),
        "category": category,
    }


def _extract_severity_from_props(props: list, default: str = "medium") -> str:
    """Extract severity from OSCAL props array."""
    for p in props:
        name = p.get("name", "").lower()
        if name in ("priority", "severity", "risk-level", "impact"):
            val = p.get("value", "").lower()
            if val in ("p1", "high", "critical"):
                return "high"
            if val in ("p3", "low", "info"):
                return "low"
    return default


def _extract_prop(props: list, name: str, default: str = "") -> str:
    """Extract a specific prop value by name."""
    for p in props:
        if p.get("name", "").lower() == name.lower():
            return p.get("value", default)
    return default


# ─── Import Endpoint ─────────────────────────────────────

@router.post("/import")
async def import_oscal(
    file: UploadFile = File(...),
    current_user: Dict = Depends(get_current_user)
):
    """Import an OSCAL JSON document (catalog, component-definition, or assessment-results)."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    content = await file.read()

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        raise HTTPException(400, "Invalid JSON file")

    # Detect OSCAL type
    if "catalog" in data:
        parsed = parse_oscal_catalog(data)
    elif "component-definition" in data:
        parsed = parse_oscal_component_definition(data)
    elif "assessment-results" in data:
        parsed = parse_oscal_assessment_results(data)
    else:
        raise HTTPException(400, "Unrecognized OSCAL type. Supported: catalog, component-definition, assessment-results")

    if not parsed.get("controls"):
        raise HTTPException(400, "No controls/findings found in the OSCAL document")

    now = datetime.now(timezone.utc).isoformat()
    checklist_id = str(uuid.uuid4())

    # Store as an ingested checklist (unified with other ingestion types)
    checklist_doc = {
        "id": checklist_id,
        "name": parsed["name"],
        "source_type": f"oscal-{parsed['oscal_type']}",
        "original_filename": file.filename or "oscal-import.json",
        "total_controls": len(parsed["controls"]),
        "mapped_controls": 0,
        "organization_id": org_id,
        "status": "parsed",
        "oscal_metadata": {
            "type": parsed["oscal_type"],
            "title": parsed.get("metadata", {}).get("title", ""),
            "version": parsed.get("metadata", {}).get("version", ""),
        },
        "created_at": now,
        "created_by": current_user["id"],
    }
    await db.ingested_checklists.insert_one(checklist_doc)

    for ctrl in parsed["controls"]:
        ctrl_doc = {
            "id": str(uuid.uuid4()),
            "checklist_id": checklist_id,
            "source_id": ctrl["source_id"],
            "title": ctrl["title"],
            "description": ctrl.get("description", ""),
            "severity": ctrl["severity"],
            "category": ctrl.get("category", "General"),
            "source_type": f"oscal-{parsed['oscal_type']}",
            "framework_mappings": [],
            "siem_categories": [],
            "status": "unmapped",
            "organization_id": org_id,
            "created_at": now,
        }
        # Add extra OSCAL-specific fields
        if ctrl.get("implementation_status"):
            ctrl_doc["implementation_status"] = ctrl["implementation_status"]
        if ctrl.get("assessment_status"):
            ctrl_doc["assessment_status"] = ctrl["assessment_status"]
        await db.ingested_controls.insert_one(ctrl_doc)

    del checklist_doc["_id"]
    return {
        "checklist": checklist_doc,
        "oscal_type": parsed["oscal_type"],
        "controls_parsed": len(parsed["controls"]),
        "message": f"Imported {len(parsed['controls'])} controls from OSCAL {parsed['oscal_type']}: {parsed['name']}"
    }


# ─── Export Endpoints ─────────────────────────────────────

@router.get("/export/catalog/{framework_id}")
async def export_framework_as_oscal_catalog(framework_id: str, current_user: Dict = Depends(get_current_user)):
    """Export an existing framework as an OSCAL Catalog JSON."""
    framework = await db.frameworks.find_one({"id": framework_id}, {"_id": 0})
    if not framework:
        raise HTTPException(404, "Framework not found")

    controls = await db.controls.find({"framework_id": framework_id}, {"_id": 0}).to_list(5000)
    if not controls:
        raise HTTPException(404, "No controls found for this framework")

    # Group by category
    categories = {}
    for c in controls:
        cat = c.get("category", "General")
        categories.setdefault(cat, []).append(c)

    oscal_groups = []
    for cat_name, cat_controls in categories.items():
        oscal_controls = []
        for c in cat_controls:
            oscal_ctrl = {
                "id": c["control_id"],
                "title": c["title"],
                "parts": [{
                    "id": f"{c['control_id']}_stmt",
                    "name": "statement",
                    "prose": c.get("description", "")
                }]
            }
            oscal_controls.append(oscal_ctrl)

        oscal_groups.append({
            "id": cat_name.lower().replace(" ", "-").replace("&", "and")[:50],
            "title": cat_name,
            "controls": oscal_controls
        })

    oscal_catalog = {
        "catalog": {
            "uuid": str(uuid.uuid4()),
            "metadata": {
                "title": framework["name"],
                "version": framework.get("version", "1.0"),
                "oscal-version": "1.2.1",
                "published": datetime.now(timezone.utc).isoformat(),
                "last-modified": datetime.now(timezone.utc).isoformat(),
                "props": [
                    {"name": "source", "value": "IronVision GRC Platform"},
                    {"name": "framework-type", "value": framework.get("type", "standard")},
                ]
            },
            "groups": oscal_groups
        }
    }

    return oscal_catalog


@router.get("/export/assessment/{framework_id}")
async def export_assessment_as_oscal(framework_id: str, current_user: Dict = Depends(get_current_user)):
    """Export compliance assessment results for a framework as OSCAL Assessment Results JSON."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    framework = await db.frameworks.find_one({"id": framework_id}, {"_id": 0})
    if not framework:
        raise HTTPException(404, "Framework not found")

    compliance_data = await db.control_compliance.find(
        {"organization_id": org_id, "framework_id": framework_id}, {"_id": 0}
    ).to_list(5000)

    findings = []
    observations = []

    for comp in compliance_data:
        obs_uuid = str(uuid.uuid4())
        finding_uuid = str(uuid.uuid4())

        status_map = {
            "compliant": "satisfied",
            "partial": "not-satisfied",
            "non_compliant": "not-satisfied",
            "not_assessed": "other",
        }

        observations.append({
            "uuid": obs_uuid,
            "title": f"Assessment of {comp['control_id']}",
            "description": comp.get("ai_assessment", ""),
            "methods": ["EXAMINE", "TEST"],
            "collected": comp.get("updated_at", datetime.now(timezone.utc).isoformat()),
        })

        finding = {
            "uuid": finding_uuid,
            "title": f"Compliance Finding: {comp['control_id']}",
            "description": comp.get("ai_assessment", f"Compliance status: {comp.get('status', 'not_assessed')}"),
            "target": {
                "type": "objective-id",
                "target-id": comp["control_id"],
                "status": {
                    "state": status_map.get(comp.get("status", "not_assessed"), "other")
                }
            },
            "related-observations": [{"observation-uuid": obs_uuid}],
        }
        findings.append(finding)

    oscal_ar = {
        "assessment-results": {
            "uuid": str(uuid.uuid4()),
            "metadata": {
                "title": f"Assessment Results: {framework['name']}",
                "version": "1.0",
                "oscal-version": "1.2.1",
                "published": datetime.now(timezone.utc).isoformat(),
                "last-modified": datetime.now(timezone.utc).isoformat(),
                "props": [
                    {"name": "source", "value": "IronVision GRC Platform"},
                ]
            },
            "results": [{
                "uuid": str(uuid.uuid4()),
                "title": f"{framework['name']} Compliance Assessment",
                "start": datetime.now(timezone.utc).isoformat(),
                "findings": findings,
                "observations": observations,
            }]
        }
    }

    return oscal_ar
