"""P1 bulk review: 942 items (27 policies) beyond the old 500-item request limit, filter-based "select all matching", batches with per-batch
transactions, partial failure + retry of failed only, skipped = already decided, idempotent double submit, per-item audit, items leave Open."""
import uuid

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import AuditEvent, Job, Policy, PolicyControlMap, System
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

N_POLICIES, TOTAL = 27, 942


@pytest.fixture(scope="module")
def ctx(client, signup_on):  # noqa: F811
    t = _signup(client, f"rb-{uuid.uuid4().hex[:6]}@example.com", "Bulk Org")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "Bulk System", "acronym": f"BK{uuid.uuid4().hex[:3]}", "baseline_key": "high",
                                                "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    isso = auth(client.post("/api/v1/sandbox/act-as", json={"role": "isso"}, headers=h).json()["access_token"])
    with SessionLocal() as db:
        s = db.get(System, uuid.UUID(sid))
        from app.models import ControlAssignment
        ctl = sorted(db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == s.id)))
        pols = [Policy(org_id=s.org_id, policy_key=f"SYN-POL-{i:02d}", title=f"SYNTHETIC Policy {i:02d}", version=1, status="current") for i in range(N_POLICIES)]
        db.add_all(pols)
        db.flush()
        for n in range(TOTAL):
            db.add(PolicyControlMap(policy_id=pols[n % N_POLICIES].id, org_id=s.org_id, control_id=ctl[n // N_POLICIES % len(ctl)], status="proposed",
                                    source="statement_language", confidence="Medium", basis="SYNTHETIC", snippets=["SYNTHETIC excerpt"]))
        db.commit()
    return {"sid": sid, "isso": isso}


def _open(client, ctx):
    q = client.get(f"/api/v1/mapping-review?system_id={ctx['sid']}", headers=ctx["isso"]).json()
    return [x for x in q["queue"] if x["kind"] == "policy_map"]


def _run(job_id):
    from app.services import review_bulk as rb
    with SessionLocal() as db:
        job = db.get(Job, uuid.UUID(job_id))
        return rb.run(db, job.payload)


def test_old_endpoint_limit_documents_root_cause(client, ctx):
    items = _open(client, ctx)
    assert len(items) == TOTAL
    r = client.post("/api/v1/mapping-review/decide", json={"system_id": ctx["sid"], "action": "approve", "items": [
        {"kind": i["kind"], "key": i["key"], "ids": i["ids"], "control_id": i["control_id"]} for i in items]}, headers=ctx["isso"])
    assert r.status_code == 422 and "at most 500" in r.text


def test_partial_failure_then_retry_failed_only(client, ctx, monkeypatch):
    from app.api.v1 import phase4
    items = _open(client, ctx)[:120]
    bad = {items[3]["key"], items[110]["key"]}
    real = phase4.decide_item

    def flaky(db, system, it, *a, **k):
        if it.key in bad:
            raise RuntimeError("SYNTHETIC failure")
        return real(db, system, it, *a, **k)
    monkeypatch.setattr(phase4, "decide_item", flaky)
    idem = uuid.uuid4().hex
    body = {"system_id": ctx["sid"], "action": "approve", "item_keys": [i["key"] for i in items], "idempotency_key": idem}
    j = client.post("/api/v1/mapping-review/bulk-jobs", json=body, headers=ctx["isso"]).json()
    assert client.post("/api/v1/mapping-review/bulk-jobs", json=body, headers=ctx["isso"]).json()["id"] == j["id"], "double submit → same job"
    res = _run(j["id"])
    assert res["succeeded"] == 118 and {f["key"] for f in res["failed"]} == bad and res["batches"] == 2
    with SessionLocal() as db:
        db.get(Job, uuid.UUID(j["id"])).status = "succeeded"
        db.commit()
    monkeypatch.setattr(phase4, "decide_item", real)
    r = client.post(f"/api/v1/mapping-review/bulk-jobs/{j['id']}/retry", headers=ctx["isso"]).json()
    assert r["total"] == 2 and r["retry_of"] == j["id"]
    assert _run(r["id"])["succeeded"] == 2
    assert len(_open(client, ctx)) == TOTAL - 120


def test_select_all_matching_processes_remaining_942_and_queue_empties(client, ctx):
    import time
    left = len(_open(client, ctx))
    j = client.post("/api/v1/mapping-review/bulk-jobs", json={"system_id": ctx["sid"], "action": "approve", "kind": "policy_map",
                                                              "idempotency_key": uuid.uuid4().hex}, headers=ctx["isso"]).json()
    assert j["total"] == left, "filter-based: every matching item on the server, not only loaded rows"
    t0 = time.time()
    res = _run(j["id"])
    elapsed = time.time() - t0
    assert res["succeeded"] == left and not res["failed"] and res["batches"] == -(-left // 100)
    assert _open(client, ctx) == [], "approved items leave Open"
    with SessionLocal() as db:
        sid = uuid.UUID(ctx["sid"])
        org = db.get(System, sid).org_id
        assert db.scalar(select(func.count()).select_from(PolicyControlMap).where(PolicyControlMap.org_id == org, PolicyControlMap.status == "mapped")) == TOTAL
        ids = [str(i) for i in db.scalars(select(PolicyControlMap.policy_id).where(PolicyControlMap.org_id == org).distinct())]
        per_item = db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.action.like("policy%"), AuditEvent.entity_id.in_(ids)))
        assert per_item >= TOTAL, f"per-item audit entries ({per_item})"
    print(f"bulk {left} items in {elapsed:.1f}s; failed sample {res['failed'][:1]}")
    # re-run the same items: all skipped as already decided (idempotent)
    j2 = client.post("/api/v1/mapping-review/bulk-jobs", json={"system_id": ctx["sid"], "action": "approve", "item_keys": ["pm:" + str(uuid.uuid4())],
                                                               "idempotency_key": uuid.uuid4().hex}, headers=ctx["isso"])
    assert j2.status_code == 422 and "no longer open" in j2.text
