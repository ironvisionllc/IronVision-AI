"""
Universal Compliance Ingestion Layer
- Parses STIG (XML), CIS (YAML/CSV), PCI (JSON), Questionnaires (CSV/JSON)
- Normalizes into unified control graph
- Auto-maps across existing frameworks using AI
- Ties to SIEM data for real-time compliance status
"""
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form
from pydantic import BaseModel
from typing import Dict, Optional, List, Any
from datetime import datetime, timezone
import uuid
import os
import re
import json
import csv
import io
import logging

import yaml
import defusedxml.ElementTree as ET

from emergentintegrations.llm.chat import LlmChat, UserMessage

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingestion", tags=["ingestion"])

# ─── Parsers ──────────────────────────────────────────────

def parse_stig_xml(content: bytes) -> dict:
    """Parse DISA STIG XML (XCCDF Benchmark format)."""
    root = ET.fromstring(content)
    ns = {"xccdf": "http://checklists.nist.gov/xccdf/1.2",
          "xccdf1": "http://checklists.nist.gov/xccdf/1.1"}

    checklist_name = ""
    controls = []

    # Try 1.2 namespace first, then 1.1, then no namespace
    for nskey, nsmap in [("xccdf", ns), ("xccdf1", ns), ("", {})]:
        prefix = f"{{{nsmap.get(nskey, '')}}}" if nskey else ""

        title_el = root.find(f"{prefix}title")
        if title_el is not None and title_el.text:
            checklist_name = title_el.text
            break

    if not checklist_name:
        checklist_name = root.attrib.get("id", "STIG Checklist")

    # Parse Groups → Rules
    for group in _find_all_recursive(root, "Group"):
        group_id = group.attrib.get("id", "")
        for rule in _find_all_recursive(group, "Rule"):
            rule_id = rule.attrib.get("id", "")
            severity = rule.attrib.get("severity", "medium")

            title_text = _get_text(rule, "title") or _get_text(group, "title") or rule_id
            desc_text = _get_text(rule, "description") or ""
            # Clean embedded XML from description
            desc_text = re.sub(r'<[^>]+>', ' ', desc_text).strip()[:500]

            fix_text = _get_text(rule, "fixtext") or ""
            check_text = ""
            check_el = _find_recursive(rule, "check-content")
            if check_el is not None and check_el.text:
                check_text = check_el.text.strip()[:300]

            controls.append({
                "source_id": rule_id or group_id,
                "title": title_text,
                "description": desc_text,
                "severity": _normalize_severity(severity),
                "category": "Security Technical Implementation Guide",
                "fix_text": fix_text[:300],
                "check_text": check_text,
            })

    # Fallback: if no Groups found, try plain Rule elements
    if not controls:
        for rule in _find_all_recursive(root, "Rule"):
            rule_id = rule.attrib.get("id", "")
            severity = rule.attrib.get("severity", "medium")
            title_text = _get_text(rule, "title") or rule_id
            desc_text = _get_text(rule, "description") or ""
            desc_text = re.sub(r'<[^>]+>', ' ', desc_text).strip()[:500]
            controls.append({
                "source_id": rule_id,
                "title": title_text,
                "description": desc_text,
                "severity": _normalize_severity(severity),
                "category": "STIG Rule",
            })

    return {"name": checklist_name, "controls": controls}


def _find_all_recursive(element, tag):
    """Find all elements with tag, ignoring namespaces."""
    results = []
    for el in element.iter():
        local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if local == tag:
            results.append(el)
    return results


def _find_recursive(element, tag):
    """Find first element with tag, ignoring namespaces."""
    for el in element.iter():
        local = el.tag.split("}")[-1] if "}" in el.tag else el.tag
        if local == tag:
            return el
    return None


def _get_text(element, tag):
    """Get text of first child with tag, ignoring namespaces."""
    el = _find_recursive(element, tag)
    if el is not None and el.text:
        return el.text.strip()
    return ""


def parse_cis_yaml(content: bytes) -> dict:
    """Parse CIS Benchmark in YAML format."""
    data = yaml.safe_load(content)
    checklist_name = data.get("benchmark_name", data.get("title", data.get("name", "CIS Benchmark")))
    controls = []

    sections = data.get("sections", data.get("controls", data.get("recommendations", data.get("items", []))))
    if isinstance(sections, list):
        for item in sections:
            if isinstance(item, dict):
                controls.append({
                    "source_id": str(item.get("id", item.get("control_id", item.get("number", str(uuid.uuid4())[:8])))),
                    "title": item.get("title", item.get("name", item.get("recommendation", "Untitled"))),
                    "description": item.get("description", item.get("rationale", item.get("detail", "")))[:500],
                    "severity": _normalize_severity(item.get("severity", item.get("level", item.get("scored", "medium")))),
                    "category": item.get("section", item.get("category", item.get("group", "General"))),
                })

                # Handle nested sub-controls
                subs = item.get("sub_controls", item.get("children", item.get("sub_items", [])))
                if isinstance(subs, list):
                    for sub in subs:
                        if isinstance(sub, dict):
                            controls.append({
                                "source_id": str(sub.get("id", sub.get("control_id", str(uuid.uuid4())[:8]))),
                                "title": sub.get("title", sub.get("name", "Untitled")),
                                "description": sub.get("description", sub.get("rationale", ""))[:500],
                                "severity": _normalize_severity(sub.get("severity", sub.get("level", "medium"))),
                                "category": item.get("title", item.get("section", "General")),
                            })

    return {"name": checklist_name, "controls": controls}


def parse_cis_csv(content: bytes) -> dict:
    """Parse CIS Benchmark in CSV format."""
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    controls = []
    checklist_name = "CIS Benchmark (CSV)"

    for row in reader:
        # Normalize field names (lowercase, strip)
        norm = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items() if k}
        source_id = norm.get("id", norm.get("control_id", norm.get("number", norm.get("recommendation_#", str(uuid.uuid4())[:8]))))
        title = norm.get("title", norm.get("recommendation", norm.get("name", norm.get("control", "Untitled"))))
        desc = norm.get("description", norm.get("rationale", norm.get("detail", "")))[:500]
        sev = norm.get("severity", norm.get("level", norm.get("scored", "medium")))
        cat = norm.get("section", norm.get("category", norm.get("group", "General")))

        controls.append({
            "source_id": str(source_id),
            "title": title,
            "description": desc,
            "severity": _normalize_severity(sev),
            "category": cat,
        })

    return {"name": checklist_name, "controls": controls}


def parse_pci_json(content: bytes) -> dict:
    """Parse PCI DSS checklist in JSON format."""
    data = json.loads(content)
    checklist_name = data.get("name", data.get("title", data.get("standard", "PCI DSS Checklist")))
    controls = []

    requirements = data.get("requirements", data.get("controls", data.get("items", data.get("sections", []))))
    if isinstance(requirements, list):
        for req in requirements:
            if isinstance(req, dict):
                controls.append({
                    "source_id": str(req.get("id", req.get("requirement_id", req.get("number", str(uuid.uuid4())[:8])))),
                    "title": req.get("title", req.get("name", req.get("requirement", "Untitled"))),
                    "description": req.get("description", req.get("detail", req.get("guidance", "")))[:500],
                    "severity": _normalize_severity(req.get("severity", req.get("priority", "high"))),
                    "category": req.get("section", req.get("category", req.get("group", "PCI DSS"))),
                })

                # Sub-requirements
                subs = req.get("sub_requirements", req.get("children", req.get("sub_controls", [])))
                if isinstance(subs, list):
                    for sub in subs:
                        if isinstance(sub, dict):
                            controls.append({
                                "source_id": str(sub.get("id", sub.get("requirement_id", str(uuid.uuid4())[:8]))),
                                "title": sub.get("title", sub.get("name", "Untitled")),
                                "description": sub.get("description", sub.get("detail", ""))[:500],
                                "severity": _normalize_severity(sub.get("severity", "high")),
                                "category": req.get("title", req.get("section", "PCI DSS")),
                            })

    return {"name": checklist_name, "controls": controls}


def parse_questionnaire(content: bytes, filename: str) -> dict:
    """Parse a generic compliance questionnaire (CSV or JSON)."""
    if filename.endswith(".json"):
        data = json.loads(content)
        checklist_name = data.get("name", data.get("title", "Compliance Questionnaire"))
        questions = data.get("questions", data.get("items", data.get("controls", [])))
        controls = []
        for q in questions:
            if isinstance(q, dict):
                controls.append({
                    "source_id": str(q.get("id", q.get("question_id", str(uuid.uuid4())[:8]))),
                    "title": q.get("question", q.get("title", q.get("name", "Untitled"))),
                    "description": q.get("description", q.get("guidance", q.get("expected_answer", "")))[:500],
                    "severity": _normalize_severity(q.get("severity", q.get("priority", q.get("weight", "medium")))),
                    "category": q.get("section", q.get("category", q.get("domain", "General"))),
                })
            elif isinstance(q, str):
                controls.append({
                    "source_id": str(uuid.uuid4())[:8],
                    "title": q,
                    "description": "",
                    "severity": "medium",
                    "category": "General",
                })
        return {"name": checklist_name, "controls": controls}
    else:
        # CSV questionnaire
        text = content.decode("utf-8", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        controls = []
        for row in reader:
            norm = {k.strip().lower().replace(" ", "_"): v.strip() for k, v in row.items() if k}
            controls.append({
                "source_id": norm.get("id", norm.get("question_id", str(uuid.uuid4())[:8])),
                "title": norm.get("question", norm.get("title", norm.get("control", "Untitled"))),
                "description": norm.get("description", norm.get("guidance", norm.get("expected_answer", "")))[:500],
                "severity": _normalize_severity(norm.get("severity", norm.get("priority", "medium"))),
                "category": norm.get("section", norm.get("category", norm.get("domain", "General"))),
            })
        return {"name": "Compliance Questionnaire (CSV)", "controls": controls}


def _normalize_severity(val) -> str:
    """Normalize severity to high/medium/low."""
    if val is None:
        return "medium"
    s = str(val).lower().strip()
    if s in ("high", "critical", "cat i", "cat_i", "1", "level 1", "yes", "scored", "true"):
        return "high"
    if s in ("low", "cat iii", "cat_iii", "3", "info", "informational"):
        return "low"
    return "medium"


# ─── Endpoints ─────────────────────────────────────────────

@router.post("/upload")
async def upload_checklist(
    file: UploadFile = File(...),
    source_type: str = Form(...),
    current_user: Dict = Depends(get_current_user)
):
    """Upload and parse a compliance checklist file."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    content = await file.read()
    filename = file.filename or "unknown"

    try:
        if source_type == "stig":
            parsed = parse_stig_xml(content)
        elif source_type == "cis":
            if filename.endswith((".yaml", ".yml")):
                parsed = parse_cis_yaml(content)
            else:
                parsed = parse_cis_csv(content)
        elif source_type == "pci":
            parsed = parse_pci_json(content)
        elif source_type == "questionnaire":
            parsed = parse_questionnaire(content, filename)
        else:
            raise HTTPException(400, f"Unsupported source_type: {source_type}. Use: stig, cis, pci, questionnaire")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Parse error for {filename}: {e}")
        raise HTTPException(400, f"Failed to parse file: {str(e)}")

    if not parsed.get("controls"):
        raise HTTPException(400, "No controls found in the uploaded file. Please verify the file format.")

    now = datetime.now(timezone.utc).isoformat()
    checklist_id = str(uuid.uuid4())

    checklist_doc = {
        "id": checklist_id,
        "name": parsed["name"],
        "source_type": source_type,
        "original_filename": filename,
        "total_controls": len(parsed["controls"]),
        "mapped_controls": 0,
        "organization_id": org_id,
        "status": "parsed",
        "created_at": now,
        "created_by": current_user["id"],
    }
    await db.ingested_checklists.insert_one(checklist_doc)

    # Insert normalized controls
    for ctrl in parsed["controls"]:
        ctrl_doc = {
            "id": str(uuid.uuid4()),
            "checklist_id": checklist_id,
            "source_id": ctrl["source_id"],
            "title": ctrl["title"],
            "description": ctrl.get("description", ""),
            "severity": ctrl["severity"],
            "category": ctrl.get("category", "General"),
            "source_type": source_type,
            "framework_mappings": [],
            "siem_categories": [],
            "status": "unmapped",
            "organization_id": org_id,
            "created_at": now,
        }
        await db.ingested_controls.insert_one(ctrl_doc)

    del checklist_doc["_id"]
    return {
        "checklist": checklist_doc,
        "controls_parsed": len(parsed["controls"]),
        "message": f"Successfully parsed {len(parsed['controls'])} controls from {parsed['name']}"
    }


@router.get("/checklists")
async def list_checklists(current_user: Dict = Depends(get_current_user)):
    """List all ingested checklists for the org."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    checklists = await db.ingested_checklists.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(100)
    return checklists


@router.get("/checklists/{checklist_id}")
async def get_checklist_detail(checklist_id: str, current_user: Dict = Depends(get_current_user)):
    """Get checklist detail with all its controls."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    checklist = await db.ingested_checklists.find_one(
        {"id": checklist_id, "organization_id": org_id}, {"_id": 0}
    )
    if not checklist:
        raise HTTPException(404, "Checklist not found")

    controls = await db.ingested_controls.find(
        {"checklist_id": checklist_id, "organization_id": org_id}, {"_id": 0}
    ).to_list(5000)

    # Compute mapping stats
    mapped = sum(1 for c in controls if c.get("framework_mappings"))
    severity_counts = {"high": 0, "medium": 0, "low": 0}
    for c in controls:
        severity_counts[c.get("severity", "medium")] = severity_counts.get(c.get("severity", "medium"), 0) + 1

    return {
        "checklist": checklist,
        "controls": controls,
        "stats": {
            "total": len(controls),
            "mapped": mapped,
            "unmapped": len(controls) - mapped,
            "severity": severity_counts,
        }
    }


@router.delete("/checklists/{checklist_id}")
async def delete_checklist(checklist_id: str, current_user: Dict = Depends(get_current_user)):
    """Delete an ingested checklist and its controls."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None
    result = await db.ingested_checklists.delete_one({"id": checklist_id, "organization_id": org_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Checklist not found")
    await db.ingested_controls.delete_many({"checklist_id": checklist_id, "organization_id": org_id})
    return {"message": "Checklist deleted"}


@router.post("/checklists/{checklist_id}/auto-map")
async def auto_map_checklist(checklist_id: str, current_user: Dict = Depends(get_current_user)):
    """Use AI to auto-map ingested controls to existing framework controls."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    checklist = await db.ingested_checklists.find_one(
        {"id": checklist_id, "organization_id": org_id}, {"_id": 0}
    )
    if not checklist:
        raise HTTPException(404, "Checklist not found")

    ingested = await db.ingested_controls.find(
        {"checklist_id": checklist_id, "organization_id": org_id}, {"_id": 0}
    ).to_list(5000)

    if not ingested:
        raise HTTPException(400, "No controls found for this checklist")

    # Get all existing framework controls for context
    frameworks = await db.frameworks.find({"type": "standard"}, {"_id": 0}).to_list(100)
    fw_map = {f["id"]: f["name"] for f in frameworks}

    all_controls = await db.controls.find({}, {"_id": 0, "framework_id": 1, "control_id": 1, "title": 1, "category": 1}).to_list(10000)

    # Build a reference summary of existing controls (condensed)
    fw_control_summary = {}
    for c in all_controls:
        fw_name = fw_map.get(c["framework_id"], "Unknown")
        fw_control_summary.setdefault(fw_name, []).append(f"{c['control_id']}: {c['title'][:60]}")

    ref_text = ""
    for fw_name, ctrls in fw_control_summary.items():
        ref_text += f"\n## {fw_name}\n" + "\n".join(ctrls[:30]) + "\n"
        if len(ctrls) > 30:
            ref_text += f"... and {len(ctrls)-30} more controls\n"

    # Process in batches of 15 for token limits
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    total_mapped = 0

    for i in range(0, len(ingested), 15):
        batch = ingested[i:i+15]
        batch_text = "\n".join([
            f"[{c['source_id']}] {c['title'][:80]} | Severity: {c['severity']} | Category: {c.get('category','')}"
            for c in batch
        ])

        chat = LlmChat(
            api_key=api_key,
            session_id=f"automap-{uuid.uuid4()}",
            system_message="You are a GRC compliance mapping expert. Map technical checklist items to high-level compliance framework controls. Be precise and identify ALL relevant framework controls."
        ).with_model("openai", "gpt-5.2")

        prompt = f"""Map these ingested checklist controls to existing compliance framework controls.

Ingested Controls (from {checklist['name']}):
{batch_text}

Available Framework Controls:
{ref_text[:8000]}

For each ingested control, identify 1-5 matching framework controls.
Return ONLY a JSON array:
[{{"source_id": "V-12345", "mappings": [{{"framework": "NIST SP 800-53", "control_id": "AC-2", "confidence": 0.85, "reason": "Both address user account management"}}]}}]

Rules:
- confidence: 0.0-1.0 (how closely they match)
- Only include mappings with confidence >= 0.5
- Map to as many frameworks as relevant"""

        try:
            response = await chat.send_message(UserMessage(text=prompt))
            response_text = response if isinstance(response, str) else str(response)

            json_match = re.search(r'\[[\s\S]*\]', response_text)
            if json_match:
                results = json.loads(json_match.group())

                for item in results:
                    src_id = item.get("source_id", "")
                    mappings = item.get("mappings", [])
                    if not src_id or not mappings:
                        continue

                    # Resolve framework_id from framework name
                    resolved_mappings = []
                    siem_cats = set()
                    for m in mappings:
                        fw_name_match = m.get("framework", "")
                        fw_id = None
                        for fid, fname in fw_map.items():
                            if fname.lower() in fw_name_match.lower() or fw_name_match.lower() in fname.lower():
                                fw_id = fid
                                break
                        resolved_mappings.append({
                            "framework_name": fw_name_match,
                            "framework_id": fw_id or "",
                            "control_id": m.get("control_id", ""),
                            "confidence": m.get("confidence", 0.5),
                            "reason": m.get("reason", ""),
                        })

                        # Determine SIEM categories from the mapped control
                        from routes.control_compliance import CONTROL_TO_SIEM
                        ctrl_siem = CONTROL_TO_SIEM.get(m.get("control_id", ""), [])
                        siem_cats.update(ctrl_siem)

                    new_status = "mapped" if resolved_mappings else "unmapped"
                    await db.ingested_controls.update_one(
                        {"checklist_id": checklist_id, "source_id": src_id, "organization_id": org_id},
                        {"$set": {
                            "framework_mappings": resolved_mappings,
                            "siem_categories": list(siem_cats),
                            "status": new_status,
                            "mapped_at": datetime.now(timezone.utc).isoformat(),
                        }}
                    )
                    if resolved_mappings:
                        total_mapped += 1

        except Exception as e:
            logger.error(f"AI mapping batch {i} failed: {e}")
            continue

    # Update checklist stats
    await db.ingested_checklists.update_one(
        {"id": checklist_id, "organization_id": org_id},
        {"$set": {
            "mapped_controls": total_mapped,
            "status": "mapped",
            "mapped_at": datetime.now(timezone.utc).isoformat(),
        }}
    )

    return {
        "message": f"Auto-mapped {total_mapped} of {len(ingested)} controls",
        "total": len(ingested),
        "mapped": total_mapped,
    }


@router.get("/checklists/{checklist_id}/overlap")
async def get_overlap_analysis(checklist_id: str, current_user: Dict = Depends(get_current_user)):
    """Get cross-framework overlap analysis for ingested controls."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    controls = await db.ingested_controls.find(
        {"checklist_id": checklist_id, "organization_id": org_id}, {"_id": 0}
    ).to_list(5000)

    # Build overlap matrix: framework → set of ingested control source_ids
    framework_coverage = {}
    control_overlap = {}

    for ctrl in controls:
        mappings = ctrl.get("framework_mappings", [])
        fw_names = set()
        for m in mappings:
            fw_name = m.get("framework_name", "")
            if fw_name:
                fw_names.add(fw_name)
                framework_coverage.setdefault(fw_name, set()).add(ctrl["source_id"])

        if len(fw_names) > 1:
            control_overlap[ctrl["source_id"]] = {
                "title": ctrl["title"],
                "frameworks": list(fw_names),
                "count": len(fw_names),
            }

    # Build framework overlap matrix
    fw_names = sorted(framework_coverage.keys())
    overlap_matrix = {}
    for i, fw1 in enumerate(fw_names):
        for fw2 in fw_names[i+1:]:
            shared = framework_coverage[fw1] & framework_coverage[fw2]
            if shared:
                key = f"{fw1} ↔ {fw2}"
                overlap_matrix[key] = {
                    "shared_count": len(shared),
                    "fw1_total": len(framework_coverage[fw1]),
                    "fw2_total": len(framework_coverage[fw2]),
                }

    return {
        "framework_coverage": {k: len(v) for k, v in framework_coverage.items()},
        "multi_framework_controls": sorted(control_overlap.values(), key=lambda x: -x["count"]),
        "overlap_matrix": overlap_matrix,
        "total_controls": len(controls),
        "mapped_to_any": sum(1 for c in controls if c.get("framework_mappings")),
    }


@router.get("/checklists/{checklist_id}/siem-status")
async def get_siem_status(checklist_id: str, current_user: Dict = Depends(get_current_user)):
    """Get SIEM compliance status for ingested controls."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    controls = await db.ingested_controls.find(
        {"checklist_id": checklist_id, "organization_id": org_id}, {"_id": 0}
    ).to_list(5000)

    # Get SIEM event counts (last 30 days)
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    siem_pipeline = [
        {"$match": {"timestamp": {"$gte": cutoff}}},
        {"$group": {"_id": "$category", "count": {"$sum": 1},
                    "critical": {"$sum": {"$cond": [{"$eq": ["$severity", "critical"]}, 1, 0]}},
                    "high": {"$sum": {"$cond": [{"$eq": ["$severity", "high"]}, 1, 0]}},
        }}
    ]
    siem_cats = {}
    async for doc in db.siem_events.aggregate(siem_pipeline):
        siem_cats[doc["_id"]] = {"count": doc["count"], "critical": doc["critical"], "high": doc["high"]}

    results = []
    with_siem = 0
    total_events = 0

    for ctrl in controls:
        categories = ctrl.get("siem_categories", [])
        events_count = sum(siem_cats.get(cat, {}).get("count", 0) for cat in categories)
        critical = sum(siem_cats.get(cat, {}).get("critical", 0) for cat in categories)
        high = sum(siem_cats.get(cat, {}).get("high", 0) for cat in categories)

        has_siem = len(categories) > 0 and events_count > 0
        if has_siem:
            with_siem += 1
            total_events += events_count

        # Determine compliance indication
        if not categories:
            siem_status = "no_mapping"
        elif events_count == 0:
            siem_status = "no_events"
        elif critical > 0:
            siem_status = "critical_findings"
        elif high > 0:
            siem_status = "attention_needed"
        else:
            siem_status = "monitored"

        results.append({
            "source_id": ctrl["source_id"],
            "title": ctrl["title"],
            "severity": ctrl["severity"],
            "siem_categories": categories,
            "siem_events_count": events_count,
            "siem_critical": critical,
            "siem_high": high,
            "siem_status": siem_status,
            "framework_mappings": ctrl.get("framework_mappings", []),
        })

    return {
        "controls": results,
        "summary": {
            "total": len(controls),
            "with_siem_data": with_siem,
            "total_events": total_events,
            "no_mapping": sum(1 for r in results if r["siem_status"] == "no_mapping"),
            "critical_findings": sum(1 for r in results if r["siem_status"] == "critical_findings"),
            "attention_needed": sum(1 for r in results if r["siem_status"] == "attention_needed"),
            "monitored": sum(1 for r in results if r["siem_status"] == "monitored"),
        }
    }


@router.get("/sample-files")
async def list_sample_files():
    """List available sample checklist files."""
    return [
        {"name": "sample_stig.xml", "source_type": "stig", "description": "Windows Server 2019 STIG (8 controls)"},
        {"name": "sample_cis.yaml", "source_type": "cis", "description": "CIS AWS Foundations Benchmark (12 controls)"},
        {"name": "sample_pci.json", "source_type": "pci", "description": "PCI DSS v4.0 Checklist (14 controls)"},
        {"name": "sample_questionnaire.json", "source_type": "questionnaire", "description": "Cloud Security Questionnaire (10 controls)"},
    ]


@router.get("/sample-files/{filename}")
async def download_sample_file(filename: str):
    """Download a sample checklist file."""
    from fastapi.responses import FileResponse
    import pathlib
    safe_names = {"sample_stig.xml", "sample_cis.yaml", "sample_pci.json", "sample_questionnaire.json"}
    if filename not in safe_names:
        raise HTTPException(404, "Sample file not found")
    path = pathlib.Path(__file__).parent.parent / "sample_checklists" / filename
    if not path.exists():
        raise HTTPException(404, "Sample file not found")
    return FileResponse(str(path), filename=filename)
