"""Generalisation beyond RA: SYNTHETIC demo-style AC and SC policies (tests/fixtures/policies/{ac,sc}_policy_raven_demo.docx, built by
scripts/perf/make_demo_policies.py). AC includes real remote access (AC-17 positive); SC must never get AC-17/remote-access results.
Deterministic analysis + a simulated AI audit reply that hallucinates out-of-scope controls."""
import json
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Organization, Policy, PolicyControlMap, PolicyFinding, PolicyRequirementCoverage, System
from app.services.rmf import analyze_policy, extract_text

FIX = Path(__file__).parent / "fixtures" / "policies"
GOLD = Path("/app/docs/perf/corpus")
AI = {"ac": {"findings": [{"control_id": "ra-5", "description": "No vulnerability scanning.", "quote": None},
                          {"control_id": "ac-7", "description": "No action after the logon limit.", "quote": None}]},
      "sc": {"findings": [{"control_id": "ac-17", "description": "Remote access is not addressed.", "quote": None},
                          {"control_id": "sc-12", "description": "Key distribution and destruction not stated.", "quote": None}]}}


def _run(key: str) -> dict:
    f = FIX / f"{key}_policy_raven_demo.docx"
    text = extract_text(f.name, f.read_bytes())
    with SessionLocal() as db:
        org = Organization(name=f"{key.upper()} FIXTURE – SYNTHETIC", slug=f"{key}-fix-{uuid.uuid4().hex[:8]}", is_synthetic=True, is_sandbox=True)
        db.add(org)
        db.flush()
        sysm = System(id=uuid.uuid4(), org_id=org.id, name="SYNTHETIC The Raven")
        db.add(sysm)
        db.flush()
        pol = Policy(org_id=org.id, policy_key=key.upper(), title=key, version=1, status="current", text_content=text, analysis_status="queued", system_ids=[str(sysm.id)])
        db.add(pol)
        db.flush()
        analyze_policy(db, pol, ai_output=AI[key])
        db.commit()
        pid = pol.id
    with SessionLocal() as db:
        pol = db.get(Policy, pid)
        return {"text": text, "analysis": pol.analysis, "gold": json.loads((GOLD / f"{key}_raven.gold.json").read_text()),
                "maps": {m.control_id: m for m in db.scalars(select(PolicyControlMap).where(PolicyControlMap.policy_id == pid, PolicyControlMap.valid_to.is_(None)))},
                "cov": list(db.scalars(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id == pid))),
                "findings": list(db.scalars(select(PolicyFinding).where(PolicyFinding.policy_id == pid)))}


@pytest.fixture(scope="module")
def ac():
    return _run("ac")


@pytest.fixture(scope="module")
def sc():
    return _run("sc")


@pytest.mark.parametrize("name", ["ac", "sc"])
def test_scope_negatives_not_selected_withdrawn(name, request):
    r = request.getfixturevalue(name)
    g = r["gold"]
    neg = set(g["negative_controls"])
    assert not neg & {c for c, m in r["maps"].items() if m.status == "proposed"}
    assert not neg & {c.control_id for c in r["cov"]}
    assert not neg & {f.control_id for f in r["findings"]}
    assert set(g["not_selected"]) <= set(r["analysis"]["not_selected"])
    assert not set(g["not_selected"]) & {c.control_id for c in r["cov"]}
    assert not set(g["withdrawn"]) & set(r["maps"])
    assert set(g["withdrawn"]) | set(g["not_selected"]) | set(c for c in {x["control_id"] for x in g["requirements"]}) >= {c for c in r["maps"] if c.split("-")[0] == name}


def test_ac_remote_access_is_a_positive_case(ac):
    assert ac["maps"]["ac-17"].confidence == "High" and {"ac-17.1", "ac-17.2", "ac-17.3", "ac-17.4"} <= set(ac["maps"])
    rows = [c for c in ac["cov"] if c.control_id == "ac-17"]
    assert rows and all(c.status in ("met", "partial") for c in rows)  # deterministic only; v2+AI benchmark: all met
    assert "ra-5" in [d["control_id"] for d in ac["analysis"]["ai_dropped_out_of_scope"]]


def test_sc_never_yields_remote_access(sc):
    assert not [c for c in sc["maps"] if c.startswith("ac-")]
    assert not [f for f in sc["findings"] if re.search(r"remote access|\bac-17\b", (f.description or "") + (f.control_id or ""), re.I)]
    assert "ac-17" in [d["control_id"] for d in sc["analysis"]["ai_dropped_out_of_scope"]]


@pytest.mark.parametrize("name", ["ac", "sc"])
def test_deterministic_recall_and_no_false_gaps_on_tagged_parts(name, request):
    r = request.getfixturevalue(name)
    cov = {(c.control_id, c.requirement_id): c for c in r["cov"]}
    met = [x for x in r["gold"]["requirements"] if x["label"] == "met"]
    hit = [x for x in met if (k := (x["control_id"], x["requirement_id"])) in cov and cov[k].status in ("met", "partial")]
    assert len(hit) / len(met) >= 0.95, (name, len(hit), len(met))  # without AI: explicit part tags + guard keep real coverage visible
