"""Tester round 3: general evidence upload from a control (documents, not scan-only), keyword-only stored rows never read "missing",
lenient Workbench list params (no 422 on empty/unknown queue or limit)."""
import io
import re
import uuid

import pytest

from app.db import SessionLocal
from app.models import Policy, PolicyRequirementCoverage
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401


def _org(client, tag):
    t = _signup(client, f"r3-{tag}-{uuid.uuid4().hex[:6]}@example.com", f"R3 {tag} {uuid.uuid4().hex[:4]}")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": f"R3 {tag}", "acronym": f"R{uuid.uuid4().hex[:4]}", "baseline_key": "low",
                                               "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    p = {r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"]) for r in ("isso", "ao")}
    me = client.get("/api/v1/auth/me", headers=h).json()
    return {"sid": sid, "admin": h, "org_id": me.get("org_id") or me.get("user", {}).get("org_id"), **p}


@pytest.fixture(scope="module")
def orgs(client, signup_on):  # noqa: F811
    return _org(client, "a"), _org(client, "b")


def _docx() -> bytes:
    import docx
    d = docx.Document()
    d.add_paragraph("Account review record – Q3")
    b = io.BytesIO()
    d.save(b)
    return b.getvalue()


@pytest.mark.parametrize("name,data", [("access-review.txt", b"Quarterly account review completed by the ISSO."),
                                       ("signed-memo.pdf", b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"),
                                       ("review.docx", None)])
def test_general_evidence_upload_links_to_control(client, orgs, name, data):
    a, _ = orgs
    r = client.post(f"/api/v1/systems/{a['sid']}/controls/ac-2/evidence", files={"file": (name, data or _docx())}, headers=a["isso"])
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["linked"] and len(j["sha256"]) == 64
    d = client.get(f"/api/v1/systems/{a['sid']}/workbench/controls/ac-2", headers=a["isso"]).json()
    assert j["evidence_id"] in [e["id"] for e in d["evidence"]]
    again = client.post(f"/api/v1/systems/{a['sid']}/controls/ac-2/evidence", files={"file": (name, data or _docx())}, headers=a["isso"])
    assert again.status_code == 201 and again.json()["status"] == "duplicate" and again.json()["evidence_id"] == j["evidence_id"]


def test_general_evidence_upload_rejections_rbac_and_isolation(client, orgs):
    a, b = orgs
    assert client.post(f"/api/v1/systems/{a['sid']}/controls/ac-2/evidence", files={"file": ("x.exe", b"MZ\x90")}, headers=a["isso"]).status_code == 415
    assert client.post(f"/api/v1/systems/{a['sid']}/controls/ac-2/evidence", files={"file": ("fake.pdf", b"not a pdf")}, headers=a["isso"]).status_code == 415
    assert client.post(f"/api/v1/systems/{a['sid']}/controls/ac-2/evidence", files={"file": ("n.txt", b"note text")}, headers=a["ao"]).status_code == 403
    assert client.post(f"/api/v1/systems/{a['sid']}/controls/ac-2/evidence", files={"file": ("n.txt", b"note text")}, headers=b["isso"]).status_code in (403, 404)
    assert client.post(f"/api/v1/systems/{a['sid']}/controls/zz-99/evidence", files={"file": ("n.txt", b"note text")}, headers=a["isso"]).status_code == 404


def test_old_keyword_only_missing_row_reads_as_needs_manual_review(client, orgs):
    a, _ = orgs
    with SessionLocal() as db:
        p = Policy(org_id=uuid.UUID(a["org_id"]), title="Access Control Policy", policy_key=f"ac-{uuid.uuid4().hex[:6]}", version=1, status="current",
                   text_content="Access control policy text.", analysis_status="analyzed", analysis={}, sha256=uuid.uuid4().hex)
        db.add(p)
        db.flush()
        db.add(PolicyRequirementCoverage(org_id=p.org_id, policy_id=p.id, policy_version=1, control_id="ac-2", requirement_type="objective",
                                         requirement_id="AC-02a.[01]", label="AC-02a.[01]", text="account types allowed for use within the system are defined",
                                         concept="generic", status="missing", confidence="Medium", reason="No sentence addresses this requirement.",
                                         needs="The policy does not clearly address this requirement. Fix: Add policy language.", source="deterministic"))
        db.commit()
        pid = str(p.id)
    d = client.get(f"/api/v1/policies/{pid}", headers=a["isso"]).json()
    rows = [r for c in d["coverage"] for r in c["requirements"]]
    assert rows and all(r["status"] != "missing" and r["effective"] != "missing" for r in rows)
    assert rows[0]["confidence"] == "Low" and rows[0]["reason"].startswith("AI unavailable")
    assert "missing:" not in d["coverage"][0]["line"] and d["coverage"][0]["summary"]["missing"] == 0
    with SessionLocal() as db:  # the deliberately stale row must not linger for the seed check
        db.query(PolicyRequirementCoverage).filter(PolicyRequirementCoverage.policy_id == uuid.UUID(pid)).delete()
        db.commit()


def test_seed_path_ships_no_keyword_only_missing_rows(orgs, monkeypatch):
    """The demo seed (seed_phase3) analyses the sample Access Control policy deterministically (no AI). Same path here, with AC-2 mapped:
    the checklist is built, and no row is a keyword-only "missing"."""
    from pathlib import Path

    from app.models import PolicyControlMap
    from app.services import policy_coverage as pc
    monkeypatch.setenv("POLICY_ANALYZER", "v-current")
    a, _ = orgs
    data = (Path(__file__).resolve().parents[2] / "samples" / "policies" / "access_control_policy.txt").read_text()
    with SessionLocal() as db:
        p = Policy(org_id=uuid.UUID(a["org_id"]), title="Access Control Policy", policy_key=f"seed-{uuid.uuid4().hex[:6]}", version=1,
                   status="current", text_content=data, system_ids=[a["sid"]], analysis={})
        db.add(p)
        db.flush()
        db.add(PolicyControlMap(policy_id=p.id, org_id=p.org_id, control_id="ac-2", status="mapped", source="explicit_id", confidence="High"))
        db.flush()
        pc.analyze(db, p, use_ai=False)
        db.commit()
        rows = db.query(PolicyRequirementCoverage).filter(PolicyRequirementCoverage.policy_id == p.id).all()
    assert rows, "the checklist must be built for the mapped control"
    bad = [r.requirement_id for r in rows if r.status == "missing" and r.concept != "profile-ai" and not re.fullmatch(r"[a-z]{2}-1", r.control_id)]
    assert not bad, bad


@pytest.mark.parametrize("q", ["queue=", "queue=undefined", "limit=", "limit=abc", "queue=true&limit=5000"])
def test_workbench_list_params_are_lenient(client, orgs, q):
    a, _ = orgs
    r = client.get(f"/api/v1/systems/{a['sid']}/workbench/controls?{q}", headers=a["isso"])
    assert r.status_code == 200 and isinstance(r.json(), list)


def _ac1_policy(a, text):
    from app.models import PolicyControlMap
    with SessionLocal() as db:
        p = Policy(org_id=uuid.UUID(a["org_id"]), title="Access Control Policy", policy_key=f"xx1-{uuid.uuid4().hex[:6]}", version=1,
                   status="current", text_content=text, system_ids=[a["sid"]], analysis={})
        db.add(p)
        db.flush()
        db.add(PolicyControlMap(policy_id=p.id, org_id=p.org_id, control_id="ac-1", status="mapped", source="explicit_id", confidence="High"))
        db.commit()
        return p.id


XX1_TEXT = ("1. Purpose\nThis access control policy establishes the purpose and scope of access control for the system.\n"
            "2. Roles\nThe ISSM is designated to manage the access control policy and procedures.\n")


def test_xx1_without_ai_is_never_missing(orgs, monkeypatch):
    from app.services import policy_coverage as pc
    a, _ = orgs
    pid = _ac1_policy(a, XX1_TEXT)
    with SessionLocal() as db:
        p = db.get(Policy, pid)
        rows = pc.analyze(db, p, use_ai=False)
        db.commit()
        assert rows and not [r for r in rows if r.status == "missing"]
        low = [r for r in rows if r.status == "partial" and r.reason.startswith(pc.XX1_ONLY)]
        assert low and all(r.confidence == "Low" for r in low)


def test_xx1_ai_missing_with_checklist_hit_needs_manual_review(orgs):
    from app.services import policy_coverage as pc
    a, _ = orgs
    pid = _ac1_policy(a, XX1_TEXT)
    with SessionLocal() as db:
        p = db.get(Policy, pid)
        reqs = pc.requirements(db, "ac-1")
        sents = pc._sentences(XX1_TEXT)
        det = {q["id"]: pc.evaluate_req(XX1_TEXT, sents, "ac-1", q, "Access Control")[1] for q in reqs}
        hit = next(i for i, r in det.items() if r["status"] != "missing" and r.get("snippets"))
        ai = {q["id"]: {"status": "missing", "quote": None, "rationale": "not found", "second_look": "none"} for q in reqs}
        rows = {r.requirement_id: r for r in pc.analyze(db, p, use_ai=True, ai_prefetched={"ac-1": ai})}
        db.commit()
    r = rows[hit]
    assert r.status == "partial" and r.confidence == "Low" and r.reason.startswith("Needs manual review")
    assert r.snippets and all(s.get("candidate") for s in r.snippets)


def test_stored_xx1_missing_reads_as_needs_manual_review(client, orgs):
    a, _ = orgs
    pid = _ac1_policy(a, XX1_TEXT)
    with SessionLocal() as db:
        db.add(PolicyRequirementCoverage(org_id=uuid.UUID(a["org_id"]), policy_id=pid, policy_version=1, control_id="ac-1", requirement_type="cci",
                                         requirement_id="CCI-000002", label="CCI-000002", text="Disseminate the access control policy",
                                         concept="disseminate", status="missing", confidence="Medium", reason="The policy is not stated to be disseminated.",
                                         needs="State dissemination.", source="deterministic"))
        db.commit()
    d = client.get(f"/api/v1/policies/{pid}", headers=a["isso"]).json()
    rows = [r for c in d["coverage"] for r in c["requirements"] if r["control_id"] == "ac-1"]
    assert rows and all(r["status"] != "missing" and r["effective"] != "missing" for r in rows)
    assert rows[0]["reason"].startswith("AI unavailable for this control – policy-element checklist only")
