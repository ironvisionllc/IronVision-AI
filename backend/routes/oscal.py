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


@router.get("/export/ssp")
async def export_system_security_plan(current_user: Dict = Depends(get_current_user)):
    """Export entire compliance workspace as OSCAL System Security Plan (SSP) draft."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    now = datetime.now(timezone.utc).isoformat()

    # Get organization info
    org = await db.organizations.find_one({"id": org_id}, {"_id": 0}) if org_id else None
    org_name = org.get("name", "Organization") if org else "Organization"

    # 1. Gather all framework compliance data
    frameworks = await db.frameworks.find({"type": "standard"}, {"_id": 0}).to_list(100)
    all_controls = await db.controls.find({}, {"_id": 0}).to_list(10000)
    all_compliance = await db.control_compliance.find({"organization_id": org_id}, {"_id": 0}).to_list(10000)

    compliance_map = {}
    for c in all_compliance:
        compliance_map[f"{c['framework_id']}:{c['control_id']}"] = c

    # 2. Build implemented requirements
    implemented_requirements = []
    for ctrl in all_controls:
        key = f"{ctrl['framework_id']}:{ctrl['control_id']}"
        comp = compliance_map.get(key, {})
        status = comp.get("status", "not_assessed")

        status_map = {"compliant": "implemented", "partial": "partially-implemented",
                      "non_compliant": "planned", "not_assessed": "alternative"}

        impl_req = {
            "uuid": str(uuid.uuid4()),
            "control-id": ctrl["control_id"],
            "props": [
                {"name": "implementation-status", "value": status_map.get(status, "alternative")},
            ],
            "statements": [{
                "statement-id": f"{ctrl['control_id']}_stmt",
                "uuid": str(uuid.uuid4()),
                "prose": comp.get("ai_assessment", ctrl.get("description", f"Implementation of {ctrl['control_id']}"))[:500],
            }],
        }
        implemented_requirements.append(impl_req)

    # 3. Gather policies as components
    policies = await db.generated_templates.find(
        {"organization_id": org_id, "status": "approved"}, {"_id": 0}
    ).to_list(100)

    components = []
    for pol in policies:
        comp = {
            "uuid": str(uuid.uuid4()),
            "type": "policy",
            "title": pol.get("title", "Untitled Policy"),
            "description": f"Approved policy document — {len(pol.get('sections', []))} sections",
            "status": {"state": "operational"},
            "props": [
                {"name": "policy-id", "value": pol.get("id", "")},
                {"name": "approval-status", "value": "approved"},
            ],
        }
        components.append(comp)

    # 4. Gather evidence artifacts
    evidence = await db.evidence_artifacts.find(
        {"organization_id": org_id}, {"_id": 0}
    ).to_list(500)

    back_matter_resources = []
    for ev in evidence:
        res = {
            "uuid": str(uuid.uuid4()),
            "title": ev.get("title", "Evidence"),
            "description": ev.get("description", ""),
            "props": [
                {"name": "evidence-type", "value": ev.get("evidence_type", "")},
                {"name": "source", "value": ev.get("source", "")},
                {"name": "collected-at", "value": ev.get("collected_at", "")},
                {"name": "freshness", "value": ev.get("freshness", "")},
            ],
        }
        back_matter_resources.append(res)

    # 5. Gather POA&M entries
    poam_entries = await db.poam_entries.find(
        {"organization_id": org_id}, {"_id": 0}
    ).to_list(500)

    poam_items = []
    for pe in poam_entries:
        item = {
            "uuid": str(uuid.uuid4()),
            "title": pe.get("title", ""),
            "description": pe.get("description", ""),
            "props": [
                {"name": "poam-id", "value": pe.get("poam_id", "")},
                {"name": "severity", "value": pe.get("severity", "")},
                {"name": "priority", "value": pe.get("priority", "")},
                {"name": "status", "value": pe.get("status", "open")},
                {"name": "scheduled-completion", "value": pe.get("scheduled_completion", "")},
            ],
        }
        poam_items.append(item)

    # 6. Assemble OSCAL SSP
    ssp = {
        "system-security-plan": {
            "uuid": str(uuid.uuid4()),
            "metadata": {
                "title": f"{org_name} — System Security Plan",
                "version": "1.0-draft",
                "oscal-version": "1.2.1",
                "published": now,
                "last-modified": now,
                "props": [
                    {"name": "generated-by", "value": "IronVision AI GRC Platform"},
                    {"name": "generation-date", "value": now},
                ],
                "roles": [
                    {"id": "system-owner", "title": "System Owner"},
                    {"id": "authorizing-official", "title": "Authorizing Official"},
                    {"id": "information-system-security-officer", "title": "ISSO"},
                ],
            },
            "import-profile": {
                "href": "#nist-800-53-profile",
                "remarks": "Imports NIST SP 800-53 Rev 5 controls"
            },
            "system-characteristics": {
                "system-name": f"{org_name} Information System",
                "system-id": {"identifier-type": "https://ironvision.ai", "id": org_id or str(uuid.uuid4())},
                "description": f"System Security Plan generated by IronVision AI for {org_name}. Covers {len(frameworks)} compliance frameworks with {len(all_controls)} total controls.",
                "security-sensitivity-level": "moderate",
                "system-information": {
                    "information-types": [{
                        "uuid": str(uuid.uuid4()),
                        "title": "Compliance and Governance Data",
                        "description": "GRC platform data including compliance assessments, policies, evidence, and risk scores",
                        "categorizations": [{
                            "system": "https://doi.org/10.6028/NIST.SP.800-60v2r1",
                            "information-type-ids": ["C.3.5.8"]
                        }],
                        "confidentiality-impact": {"base": "moderate"},
                        "integrity-impact": {"base": "moderate"},
                        "availability-impact": {"base": "low"},
                    }]
                },
                "security-impact-level": {
                    "security-objective-confidentiality": "moderate",
                    "security-objective-integrity": "moderate",
                    "security-objective-availability": "low",
                },
                "status": {"state": "operational"},
                "props": [
                    {"name": "total-frameworks", "value": str(len(frameworks))},
                    {"name": "total-controls", "value": str(len(all_controls))},
                    {"name": "total-policies", "value": str(len(policies))},
                    {"name": "total-evidence", "value": str(len(evidence))},
                    {"name": "total-poam-items", "value": str(len(poam_entries))},
                ],
            },
            "system-implementation": {
                "components": components,
                "remarks": f"System includes {len(components)} approved policy documents as operational components.",
            },
            "control-implementation": {
                "description": f"Control implementation details for {len(implemented_requirements)} controls across {len(frameworks)} frameworks.",
                "implemented-requirements": implemented_requirements[:500],
            },
            "back-matter": {
                "resources": back_matter_resources[:200],
            },
        }
    }

    # Add POA&M as separate section
    if poam_items:
        ssp["plan-of-action-and-milestones"] = {
            "uuid": str(uuid.uuid4()),
            "metadata": {
                "title": f"{org_name} — Plan of Action and Milestones",
                "version": "1.0",
                "oscal-version": "1.2.1",
                "last-modified": now,
            },
            "poam-items": poam_items,
        }

    return ssp
