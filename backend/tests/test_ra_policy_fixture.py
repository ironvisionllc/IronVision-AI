"""User-provided UAT demo policy (tests/fixtures/policies/ra_policy_dod_aws_raven_demo.docx – DEMONSTRATION TEMPLATE, placeholder names):
the analysis must never yield AC-17 / remote-access findings, must honour "not selected" / withdrawn, must read the traceability matrix
(DOCX tables) and must not produce keyword-salad gap text. Deterministic analysis + a simulated AI audit reply that hallucinates AC-17."""
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Organization, Policy, PolicyControlMap, PolicyFinding, PolicyRequirementCoverage, System
from app.services.rmf import analyze_policy, extract_text

FIX = Path(__file__).parent / "fixtures" / "policies" / "ra_policy_dod_aws_raven_demo.docx"
AI_REPLY = {"findings": [
    {"control_id": "ac-17", "description": "Remote access is not addressed.", "quote": None},  # out of scope – must be dropped
    {"control_id": "ra-6", "description": "No TSCM survey frequency.", "quote": None},          # policy states not selected – dropped
    {"control_id": "ra-5", "description": "False-positive process is vague.", "quote": "document false positives with evidence for SCA review"}]}


@pytest.fixture(scope="module")
def ra():
    text = extract_text(FIX.name, FIX.read_bytes())
    with SessionLocal() as db:
        org = Organization(name="RA FIXTURE – SYNTHETIC", slug=f"ra-fix-{uuid.uuid4().hex[:8]}", is_synthetic=True, is_sandbox=True)
        db.add(org)
        db.flush()
        sysm = System(id=uuid.uuid4(), org_id=org.id, name="SYNTHETIC The Raven")
        db.add(sysm)
        db.flush()
        pol = Policy(org_id=org.id, policy_key="RA-FIX", title="RA fixture", version=1, status="current", text_content=text,
                     analysis_status="queued", system_ids=[str(sysm.id)])
        db.add(pol)
        db.flush()
        analyze_policy(db, pol, ai_output=AI_REPLY)
        db.commit()
        pid = pol.id
    with SessionLocal() as db:
        pol = db.get(Policy, pid)
        yield {"text": text, "analysis": pol.analysis,
               "maps": {m.control_id: m for m in db.scalars(select(PolicyControlMap).where(PolicyControlMap.policy_id == pid, PolicyControlMap.valid_to.is_(None)))},
               "cov": list(db.scalars(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id == pid))),
               "findings": list(db.scalars(select(PolicyFinding).where(PolicyFinding.policy_id == pid)))}


def test_docx_tables_are_extracted(ra):
    assert "RA-6 | Technical Surveillance Countermeasures Survey | None | 13 | Not selected" in ra["text"]
    assert "EC2 operating systems | ACAS; Amazon Inspector |" in ra["text"]


def test_never_ac17_or_remote_access(ra):
    assert not [c for c in ra["maps"] if c.startswith("ac-")]
    assert not [c for c in ra["cov"] if c.control_id.startswith("ac-")]
    assert not [f for f in ra["findings"] if (f.control_id or "").startswith("ac-") or re.search(r"remote access", f.description, re.I)]
    assert "ac-17" in [d["control_id"] for d in ra["analysis"]["ai_dropped_out_of_scope"]]
    assert {f.control_id for f in ra["findings"] if f.origin == "ai"} == {"ra-5"}


def test_not_selected_flagged_not_gaps_and_withdrawn_ignored(ra):
    ns = ra["analysis"]["not_selected"]
    assert set(ns) == {"ra-6", "ra-3.4"}
    for c in ns:
        assert ra["maps"][c].review_flag and "policy states not selected" in ra["maps"][c].basis
        assert not [r for r in ra["cov"] if r.control_id == c]
    assert not {"ra-4", "ra-5.1", "ra-5.7", "ra-5.9"} & set(ra["maps"])


def test_out_of_family_title_matches_are_possible_related_not_review_items(ra):
    rel = {r["control_id"]: r for r in ra["analysis"]["possible_related_controls"]}
    assert {"ca-7", "ir-8", "pe-3.1"} <= set(rel) and all(r["matched_text"] for r in rel.values())
    assert not set(rel) & set(ra["maps"])
    assert {c.split("-")[0] for c in ra["maps"]} == {"ra"}
    assert ra["analysis"]["counts"]["possible_related_not_proposed"] == len(rel)


def test_traceability_matrix_rows_mapped_and_quoted(ra):
    t = ra["text"]
    matrix = t[t.index("16. Control Traceability Matrix"):t.index("17. Acronyms")]
    rows = [ln for ln in matrix.splitlines() if re.match(r"RA-\d+(?:\(\d+\))? \| ", ln)]
    assert len(rows) == 23
    for ln in rows:
        m = re.match(r"RA-(\d+)(?:\((\d+)\))?", ln)
        cid = f"ra-{m.group(1)}" + (f".{m.group(2)}" if m.group(2) else "")
        if "Withdrawn" in ln:
            assert cid not in ra["maps"]
            continue
        assert ln.strip()[:300] in (ra["maps"][cid].snippets or []), cid


def test_no_keyword_salad_reasons(ra):
    bad = [r.reason for r in ra["cov"] if re.search(r"does not state: |states [a-z ]+, develop doc|in accordance\.$|A value is stated for something else", r.reason)]
    assert not bad, bad[:3]
