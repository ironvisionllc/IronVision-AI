"""P1 #2 "approved but still listed": approve ≤500 items with the real Approve-selected endpoint on a realistic 27-policy fixture,
reload the queue and check which items remain – and why (same item vs. a legitimately new dependent item)."""
import uuid
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import ControlAssignment, Policy, PolicyControlMap, System
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

TEXT = (Path(__file__).resolve().parents[2] / "samples/policies/access_control_policy.txt").read_text()


@pytest.fixture(scope="module")
def ctx(client, signup_on):  # noqa: F811
    t = _signup(client, f"sl-{uuid.uuid4().hex[:6]}@example.com", "Still Listed Org")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "Still Listed", "acronym": f"SL{uuid.uuid4().hex[:3]}", "baseline_key": "moderate",
                                                "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    isso = auth(client.post("/api/v1/sandbox/act-as", json={"role": "isso"}, headers=h).json()["access_token"])
    from app.services import policy_coverage as pc
    with SessionLocal() as db:
        s = db.get(System, uuid.UUID(sid))
        ac = sorted(c for c in db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == s.id)) if c.startswith("ac-"))
        for i in range(27):
            p = Policy(org_id=s.org_id, policy_key=f"SYN-AC-{i:02d}", title=f"SYNTHETIC Access Control Policy {i:02d}", version=1, status="current",
                       text_content=TEXT, analysis_status="analyzed")
            db.add(p)
            db.flush()
            for c in ac[i % 3::3][:8]:
                db.add(PolicyControlMap(policy_id=p.id, org_id=s.org_id, control_id=c, status="proposed", source="statement_language",
                                        confidence="High", basis="SYNTHETIC", snippets=["SYNTHETIC"]))
            db.flush()
            pc.analyze(db, p)  # what the analysis job does after upload
        db.commit()
    return {"sid": sid, "isso": isso}


def _q(client, ctx):
    return client.get(f"/api/v1/mapping-review?system_id={ctx['sid']}", headers=ctx["isso"]).json()["queue"]


def test_approve_selected_then_reload(client, ctx):
    before = [x for x in _q(client, ctx) if not x.get("awaiting_sca")]
    print("BEFORE", len(before), Counter(x["kind"] for x in before))
    sel = [x for x in before if x["kind"] == "policy_map"][:500]
    items = [{"kind": x["kind"], "ids": x["ids"], "control_id": x["control_id"], "evidence_fp": x.get("evidence_fp")} for x in sel]
    r = client.post("/api/v1/mapping-review/decide", json={"system_id": ctx["sid"], "items": items, "action": "approve", "justification": ""}, headers=ctx["isso"])
    print("DECIDE", r.status_code, {k: v for k, v in r.json().items() if k != "partial"} if r.status_code == 200 else r.text[:300])
    after = [x for x in _q(client, ctx) if not x.get("awaiting_sca")]
    keys = {x["key"] for x in sel}
    same = [x for x in after if x["key"] in keys]
    new = [x for x in after if x["key"] not in {b["key"] for b in before}]
    print("AFTER", len(after), Counter(x["kind"] for x in after), "same-still-open", len(same), "new", len(new), Counter(x["kind"] for x in new))
    for x in new[:3]:
        print("NEW", x["kind"], x["control_id"], x.get("title", "")[:120], "|", x.get("why_new"))
    assert not same


def test_policy_status_approve_then_reload(client, ctx):
    ps = [x for x in _q(client, ctx) if x["kind"] == "policy_status" and not x.get("awaiting_sca")]
    items = [{"kind": x["kind"], "ids": x["ids"], "control_id": x["control_id"], "evidence_fp": x.get("evidence_fp")} for x in ps]
    r = client.post("/api/v1/mapping-review/decide", json={"system_id": ctx["sid"], "items": items, "action": "approve", "justification": ""}, headers=ctx["isso"])
    after = _q(client, ctx)
    print("PS DECIDE", r.status_code, r.json() if r.status_code == 200 else r.text[:200])
    print("PS AFTER open", Counter(x["kind"] for x in after if not x.get("awaiting_sca")), "awaiting SCA", Counter(x["kind"] for x in after if x.get("awaiting_sca")))
    assert not [x for x in after if x["key"] in {p["key"] for p in ps} and not x.get("awaiting_sca")]


def test_reanalysis_does_not_reopen(client, ctx):
    from app.services import policy_coverage as pc
    from app.services import policy_mapping as pm
    before = {x["key"] for x in _q(client, ctx)}
    with SessionLocal() as db:
        s = db.get(System, uuid.UUID(ctx["sid"]))
        for p in db.scalars(select(Policy).where(Policy.org_id == s.org_id)):
            pm.store_proposals(db, p, pm.extract_mappings(db, p.text_content))  # what re-analysis / worker restart reprocessing does
            pc.analyze(db, p)
        db.commit()
    after = _q(client, ctx)
    new = [x for x in after if x["key"] not in before]
    print("REANALYSIS new", len(new), Counter(x["kind"] for x in new), [(x["control_id"], x.get("why_new")) for x in new[:3]])
    with SessionLocal() as db:
        reproposed = [x for x in new if x["kind"] == "policy_map" and db.scalar(select(PolicyControlMap).where(
            PolicyControlMap.policy_id == uuid.UUID(x["policy_id"]), PolicyControlMap.control_id == x["control_id"], PolicyControlMap.status == "mapped",
            PolicyControlMap.valid_to.is_(None))) is not None]
    print("REANALYSIS re-proposed already-approved", len(reproposed), "first-time proposals", len(new) - len(reproposed))
    assert not reproposed  # approved (policy, control) pairs are never re-proposed by re-analysis


def test_mixed_selection_some_already_decided(client, ctx):
    q = [x for x in _q(client, ctx) if not x.get("awaiting_sca")]
    with SessionLocal() as db:
        approved = db.scalar(select(PolicyControlMap).where(PolicyControlMap.status == "mapped", PolicyControlMap.valid_to.is_(None),
                                                            PolicyControlMap.basis == "SYNTHETIC").limit(1))
    stale = {"kind": "policy_map", "ids": [str(approved.id)], "control_id": approved.control_id}
    items = [stale] + [{"kind": x["kind"], "ids": x["ids"], "control_id": x["control_id"], "evidence_fp": x.get("evidence_fp")} for x in q[:2]]
    r = client.post("/api/v1/mapping-review/decide", json={"system_id": ctx["sid"], "items": items, "action": "approve", "justification": ""}, headers=ctx["isso"])
    print("MIXED", r.status_code, r.text[:300])
    assert r.status_code == 200 and len(r.json()["skipped"]) == 1 and r.json()["skipped"][0]["control_id"] == approved.control_id
    with SessionLocal() as db:
        assert db.get(PolicyControlMap, approved.id).valid_to is None  # the approved row was not superseded by a duplicate decision
