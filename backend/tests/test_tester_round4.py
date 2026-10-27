"""Tester round 4: readable gaps (no keyword lists), subject/verb agreement in every template, identical results for an identical
upload, AI-merged coverage kept across human mapping decisions, audit-finding counts, one progress denominator."""
import re
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Policy, PolicyRequirementCoverage
from app.services import policy_coverage as pc
from app.services import policy_profile as pp
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

FIX = Path(__file__).parent / "fixtures" / "policies" / "ra_policy_dod_aws_raven_demo.docx"
AGREE = re.compile(r"\b(?:procedures|policies|results|controls) (?:is|was|has)\b|\bpolicy (?:are|were|have)\b", re.I)


def _upload(client, h, sid, title):
    from worker.handlers import handle_policy_analyze
    r = client.post("/api/v1/policies", files={"file": (FIX.name, FIX.read_bytes())}, data={"title": title, "system_ids": sid}, headers=h)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    with SessionLocal() as db:
        handle_policy_analyze(db, {"policy_id": pid})
        db.commit()
    return pid, client.get(f"/api/v1/policies/{pid}", headers=h).json()


@pytest.fixture(scope="module")
def two(client, signup_on):  # noqa: F811
    t = _signup(client, f"r4-{uuid.uuid4().hex[:6]}@example.com", "R4 Org")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "R4 Raven", "acronym": "R4RV", "baseline_key": "high", "categorization_mode": "fips199",
                                               "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    a = _upload(client, h, sid, "RA first")
    b = _upload(client, h, sid, "RA second (identical file)")
    return {"h": h, "a": a, "b": b}


def _rows(d):
    return {(c["control_id"], r["requirement_id"]): r for c in d["coverage"] for r in c["requirements"]}


def test_gaps_are_readable_sentences_never_keyword_lists(two):
    rows = _rows(two["a"][1])
    gaps = [r["gap"] for r in rows.values() if r["gap"]]
    assert gaps
    bad = [r["gap"] for r in rows.values() if r["gap"] and not pc.is_readable_gap(r["gap"].split(": ", 1)[-1], r.get("text") or "")]
    assert not bad, bad[:5]
    assert not [g for g in gaps if re.search(r"Add a statement(?! such as)", g)], "no generic 'Add a statement…' text"
    for k in (("ra-2.1", "CCI-004617"), ("ra-2.1", "ra-2.1_obj")):
        if k in rows and rows[k]["gap"]:
            assert "impact-level" in rows[k]["gap"] and "shall" in rows[k]["gap"], rows[k]["gap"]


def test_salad_detector_rejects_the_tester_examples():
    for g in ("State randomly in the tagged section.", "State employ, vulnerability, monitoring, techniques, facilitate and interoperability in the tagged section.",
              "Add a statement covering: review or analysis.", "The quoted text does not state prior, identified and reported; confirm it."):
        assert not pc.is_readable_gap(g), g
    req = "Create, enable, modify, disable, and remove system accounts."
    assert pc.is_readable_gap(pp.gap_text(req, "missing"), req), "the requirement's own list is wording, not salad"
    assert not pc.is_readable_gap("The related text does not cover employ, vulnerability, monitoring and techniques.", req)
    assert "ODP" not in pp.obligation("types of cryptography (defined in SC-13_ODP[01]) are implemented.")[0]
    assert pc.is_readable_gap(pp.gap_text("Monitor and scan for vulnerabilities in the system randomly in accordance with organization-defined process.", "review", "tagged section"))


def test_obligation_is_derived_from_the_requirement():
    assert pp.obligation("Defines a frequency for scanning for vulnerabilities.") == (
        "the organization will define a frequency for scanning for vulnerabilities", "The organization shall define a frequency for scanning for vulnerabilities.")
    that, shall = pp.obligation("usage restrictions are established and documented for each type of remote access allowed;")
    assert that.startswith("usage restrictions are established") and shall.startswith("Usage restrictions shall be established")
    assert pp.obligation("Develops, documents, and disseminates a policy.")[0] == "the organization will develop, document, and disseminate a policy"
    assert "organization-defined frequency" in pp.obligation("Review results [Assignment: organization-defined frequency].")[0]


def test_subject_verb_agreement_in_every_template():
    texts = ["", "The procedures are mentioned. The policy is reviewed. Procedures exist.",
             "The risk assessment policy and procedures are disseminated. The procedures are reviewed annually. An official is designated."]
    out = []
    for target_txt in ("policy", "procedures", "policy and procedures"):
        for concept, req in (("develop", f"Develop and document {target_txt}"), ("disseminate", f"Disseminate the {target_txt}"),
                             ("recipients", f"Defines personnel to whom the {target_txt} is disseminated"), ("frequency", f"Review and update the {target_txt} annually"),
                             ("events", f"Review and update the {target_txt} following events"), ("official", "Designate an official to manage the policy")):
            for t in texts:
                r = pc.evaluate(t, concept, target_txt, None, "risk assessment", req)
                out += [r.get("reason") or "", r.get("needs") or ""]
    for concept, tmpl in pc.LABEL.items():
        for target_txt in ("policy", "procedures", "policy and procedures"):
            be = "are" if target_txt.endswith("s") else "is"
            out.append(tmpl.format(target=target_txt, elem="purpose", fam="RA", be=be))
    bad = [s for s in out for m in AGREE.finditer(s) if not re.search(r"\bof the (?:RA |risk assessment )?(?:policy and )?$", s[:m.start()])]  # "Dissemination of the procedures is …" is fine
    assert not bad, bad[:5]


def test_identical_upload_gives_identical_coverage(two):
    ra, rb = _rows(two["a"][1]), _rows(two["b"][1])
    assert ra.keys() == rb.keys()
    diff = [k for k in ra if (ra[k]["status"], ra[k]["gap"], [s.get("text") for s in ra[k].get("snippets") or []])
            != (rb[k]["status"], rb[k]["gap"], [s.get("text") for s in rb[k].get("snippets") or []])]
    assert not diff, diff[:5]


def test_human_mapping_decision_keeps_ai_merged_rows(two):
    pid = uuid.UUID(two["b"][0])
    with SessionLocal() as db:
        pol = db.get(Policy, pid)
        pol.analysis = {**pol.analysis, "analyzer": "v2"}
        row = db.scalar(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id == pid, PolicyRequirementCoverage.control_id == "ra-5",
                                                                PolicyRequirementCoverage.status != "met").limit(1))
        rid = row.requirement_id
        row.status, row.source, row.concept, row.needs = "met", "ai", "profile-ai", None
        db.commit()
    with SessionLocal() as db:  # what policy_mapping.decide / review_bulk do after a decision: pc.analyze(db, policy) without AI
        pol = db.get(Policy, pid)
        pc.analyze(db, pol)
        db.commit()
    with SessionLocal() as db:
        pol = db.get(Policy, pid)
        kept = db.scalar(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id == pid, PolicyRequirementCoverage.control_id == "ra-5",
                                                                 PolicyRequirementCoverage.requirement_id == rid))
        assert (kept.status, kept.source) == ("met", "ai"), "AI-merged result must not be replaced by a deterministic-only re-run"
        assert pol.analysis["analyzer"] == "v2" and pol.analysis["progress"]["phase"] == "done", "final summary kept"


def test_cached_ai_path_gives_identical_results(monkeypatch, client, signup_on):  # noqa: F811
    from tests.test_policy_v2 import FakeSvc
    from app.services import rmf
    from app.services import policy_mapping as pm
    fake = FakeSvc()
    monkeypatch.setattr("app.services.ai.service.get_ai_service", lambda: fake)
    monkeypatch.setenv("POLICY_ANALYZER", "v2")
    text = rmf.extract_text(FIX.name, FIX.read_bytes())
    t = _signup(client, f"r4c-{uuid.uuid4().hex[:6]}@example.com", "R4 cache Org")
    org = uuid.UUID(client.get("/api/v1/auth/me", headers=auth(t["access_token"])).json()["org_id"])
    res, stats = [], []
    for i in range(2):
        with SessionLocal() as db:
            p = Policy(org_id=org, policy_key=f"R4C-{i}-{uuid.uuid4().hex[:4]}", title=f"R4 cache {i}", version=1, status="current", text_content=text,
                       analysis_status="queued")
            db.add(p)
            db.commit()
            cids = {m["control_id"] for m in pm.extract_mappings(db, text) if m["confidence"] in ("High", "Medium") and not m.get("not_selected")}
            pre = pc.prefetch_ai(db, p, cids, pc.in_scope_requirements(db, cids))
            stats.append(pre[pc.V2_STATS])
            rmf.analyze_policy(db, p, None, None, use_ai=True, ai_prefetched=pre)
            db.commit()
            res.append({(c.control_id, c.requirement_id): (c.status, c.needs, c.snippets) for c in
                        db.scalars(select(PolicyRequirementCoverage).where(PolicyRequirementCoverage.policy_id == p.id))})
    assert stats[1]["cache_hits"] == stats[1]["batches"] > 0, "second identical upload is served from the tenant cache"
    assert res[0] == res[1]


def test_progress_denominator_and_audit_counts(two):
    p = two["a"][1]["policy"]["analysis"]["progress"]
    assert p["requirements_in_scope"] == p["requirements_analyzed"] == sum(len(c["requirements"]) for c in two["a"][1]["coverage"])
    assert p["audit_findings"] == len(two["a"][1]["findings"]), "final count = findings actually stored and listed"


def test_audit_note_explains_suggestions_not_stored():
    from types import SimpleNamespace
    from worker.handlers import _audit_note
    ai = {"findings": [{"control_id": "ra-5"}] * 3}
    assert "not linked to a system" in _audit_note(SimpleNamespace(system_ids=[], analysis={}), ai, [])
    assert _audit_note(SimpleNamespace(system_ids=["x"], analysis={}), ai, [SimpleNamespace(control_id="ra-5", description=str(i), origin="ai") for i in range(3)]) is None
    assert "1 dropped" in _audit_note(SimpleNamespace(system_ids=["x"], analysis={}), ai, [SimpleNamespace(control_id="ra-5", description=str(i), origin="ai") for i in range(2)])
