"""
Natural Language Compliance Interrogation
- Enhanced AI chat that queries live compliance data
- Answers questions like "Which controls are non-compliant?" with real data
- Integrates with all platform data: frameworks, Tenable, pipelines, POA&M, risk scores
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Dict, Optional
from datetime import datetime, timezone
import uuid
import os
import re
import json
import logging

from emergentintegrations.llm.chat import LlmChat, UserMessage

from database import db
from utils import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/interrogate", tags=["interrogation"])


class QueryRequest(BaseModel):
    question: str
    session_id: Optional[str] = None


@router.post("/ask")
async def ask_compliance_question(req: QueryRequest, current_user: Dict = Depends(get_current_user)):
    """Answer a natural language compliance question using live platform data."""
    org_id = current_user["roles"][0]["organization_id"] if current_user.get("roles") else None

    # Gather live context from the platform
    context = await _build_context(org_id)

    api_key = os.environ.get("EMERGENT_LLM_KEY")
    session = req.session_id or f"interrogate-{uuid.uuid4()}"

    chat = LlmChat(
        api_key=api_key,
        session_id=session,
        system_message="""You are a GRC compliance analyst with access to live platform data. Answer questions using ONLY the data provided below. Be specific with numbers, control IDs, and framework names. If the data doesn't contain enough info, say so.

Format your answer clearly with bullet points and sections where appropriate. Always cite specific data points."""
    ).with_model("openai", "gpt-5.2")

    prompt = f"""Based on the following LIVE compliance platform data, answer this question:

QUESTION: {req.question}

LIVE PLATFORM DATA:
{context}

Answer specifically using the data above. Include control IDs, framework names, counts, and percentages where relevant."""

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        answer = response if isinstance(response, str) else str(response)
    except Exception as e:
        logger.error(f"Interrogation failed: {e}")
        raise HTTPException(500, "Failed to process question")

    return {
        "question": req.question,
        "answer": answer,
        "session_id": session,
        "data_timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def _build_context(org_id: str) -> str:
    """Build a comprehensive context string from all platform data."""
    parts = []

    # 1. Framework compliance summary
    frameworks = await db.frameworks.find({"type": "standard"}, {"_id": 0}).to_list(100)
    compliance = await db.control_compliance.find({"organization_id": org_id}, {"_id": 0}).to_list(10000)

    fw_map = {f["id"]: f["name"] for f in frameworks}
    fw_stats = {}
    for c in compliance:
        fw_name = fw_map.get(c["framework_id"], "Unknown")
        fw_stats.setdefault(fw_name, {"compliant": 0, "partial": 0, "non_compliant": 0, "not_assessed": 0})
        status = c.get("status", "not_assessed")
        if status in fw_stats[fw_name]:
            fw_stats[fw_name][status] += 1

    parts.append("=== FRAMEWORK COMPLIANCE STATUS ===")
    for fw_name, stats in fw_stats.items():
        total = sum(stats.values())
        parts.append(f"{fw_name}: {stats['compliant']} compliant, {stats['partial']} partial, {stats['non_compliant']} non-compliant, {stats['not_assessed']} not assessed (total: {total})")

    # Non-compliant controls detail
    non_comp = [c for c in compliance if c.get("status") == "non_compliant"]
    if non_comp:
        parts.append(f"\n=== NON-COMPLIANT CONTROLS ({len(non_comp)}) ===")
        for c in non_comp[:30]:
            fw_name = fw_map.get(c["framework_id"], "?")
            reason = (c.get("ai_assessment") or "")[:80]
            parts.append(f"  {c['control_id']} ({fw_name}): {reason}")

    # 2. Tenable findings
    tenable = await db.tenable_findings.find({"organization_id": org_id}, {"_id": 0}).to_list(500)
    if tenable:
        vulns = [f for f in tenable if f.get("finding_type") == "vulnerability"]
        checks = [f for f in tenable if f.get("finding_type") == "compliance"]
        open_vulns = [v for v in vulns if v.get("state") in ("open", "reopened")]
        parts.append("\n=== TENABLE SCAN DATA ===")
        parts.append(f"Vulnerabilities: {len(vulns)} total ({len(open_vulns)} open)")
        for v in open_vulns[:10]:
            cves = ", ".join(v.get("cves", [])[:2])
            parts.append(f"  [{v.get('severity','').upper()}] {v.get('title','')[:60]} on {v.get('asset_hostname','')} (CVE: {cves})")
        failed_checks = [c for c in checks if c.get("status") == "FAILED"]
        parts.append(f"Compliance checks: {len(checks)} total ({len(failed_checks)} failed)")
        for c in failed_checks[:10]:
            parts.append(f"  FAILED: {c.get('title','')[:60]} | Expected: {c.get('expected_value','')} | Actual: {c.get('actual_value','')}")

    # 3. Pipeline data
    pipeline_runs = await db.pipeline_runs.find({"organization_id": org_id}, {"_id": 0}).to_list(50)
    if pipeline_runs:
        parts.append("\n=== CI/CD PIPELINE DATA ===")
        parts.append(f"Total runs: {len(pipeline_runs)}")
        failed = [r for r in pipeline_runs if r.get("gate_result") == "fail"]
        parts.append(f"Failed gates: {len(failed)}")
        for r in pipeline_runs[:5]:
            parts.append(f"  {r.get('pipeline_name','')}: {r.get('total_findings',0)} findings, gate={r.get('gate_result','pending')}, risk={r.get('risk_score',0)}")

    # 4. POA&M entries
    poam = await db.poam_entries.find({"organization_id": org_id}, {"_id": 0}).to_list(100)
    if poam:
        open_poam = [p for p in poam if p.get("status") == "open"]
        parts.append("\n=== POA&M ENTRIES ===")
        parts.append(f"Total: {len(poam)}, Open: {len(open_poam)}")
        for p in open_poam[:10]:
            parts.append(f"  [{p.get('severity','').upper()}/{p.get('priority','')}] {p.get('title','')[:60]} | Due: {p.get('scheduled_completion','')[:10]}")

    # 5. Risk scores
    risk_history = await db.risk_score_history.find(
        {"organization_id": org_id}, {"_id": 0}
    ).sort("timestamp", -1).to_list(1)
    if risk_history:
        r = risk_history[0]
        parts.append("\n=== RISK SCORE ===")
        parts.append(f"Org Score: {r.get('score',0)} ({r.get('level','unknown')})")
        for k, v in r.get("factors", {}).items():
            parts.append(f"  {k}: {v}")

    # 6. Evidence coverage
    evidence = await db.evidence_artifacts.find({"organization_id": org_id}, {"_id": 0, "evidence_type": 1}).to_list(500)
    if evidence:
        by_type = {}
        for e in evidence:
            t = e.get("evidence_type", "unknown")
            by_type[t] = by_type.get(t, 0) + 1
        parts.append("\n=== EVIDENCE ARTIFACTS ===")
        parts.append(f"Total: {len(evidence)}")
        for t, c in by_type.items():
            parts.append(f"  {t}: {c}")

    return "\n".join(parts)
