"""Policy Auditor v2: sections/retrieval, batching + validation, tenant-scoped cache (no cross-tenant hit), incremental reuse, not-examined
labelling, and no open transaction / no idle-in-transaction session during or after the AI stage. AI is faked here (no network)."""
import json
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select, text

from app.db import SessionLocal, get_engine
from app.models import Organization, PolicyAiCache
from app.services import policy_analyzer_v2 as v2

DOC = """SYNTHETIC Access Control Policy

--- Page 1 ---

## AC-2 Account Management
The organization ensures that account managers are assigned for every information system account. Accounts are reviewed every 90 days.

## AC-17 Remote Access
The organization ensures that remote access is authorized prior to allowing such connections.

--- Page 2 ---

## Travel
Employees book economy airfare.
"""
TODO = [("ac-2", [{"id": "ac-2_obj.d", "text": "account managers are assigned"}, {"id": "ac-2_obj.j", "text": "accounts are reviewed for compliance with account management requirements"}],
         [("c", {"status": "missing"}), ("c", {"status": "missing"})]),
        ("ac-17", [{"id": "ac-17_obj.b", "text": "remote access is authorized prior to allowing such connections"}], [("c", {"status": "missing"})]),
        ("ia-5", [{"id": "ia-5_obj.zz", "text": "quantum lattice escrow attestation"}], [("c", {"status": "missing"})])]


class FakeSvc:
    def __init__(self):
        self.calls, self.provider = [], SimpleNamespace(model="fake/model")

    async def run(self, pid, ver, vars, max_tokens=None):
        assert (pid, ver) == v2.PROMPT
        reqs = json.loads(vars["requirements"])
        self.calls.append([r["requirement_id"] for r in reqs])
        items = []
        for r in reqs:
            q = "account managers are assigned for every information system account" if r["requirement_id"] == "ac-2_obj.d" else ""
            items.append(SimpleNamespace(control_id=r["control_id"], requirement_id=r["requirement_id"], status="met" if q else "missing",
                                         quote=q, section="S1", rationale="Stated." if q else "Not stated."))
        items.append(SimpleNamespace(control_id="zz-9", requirement_id="bogus", status="met", quote="x", section="S1", rationale=""))  # invalid
        return SimpleNamespace(output=SimpleNamespace(items=items), model="fake/model")


def _org(db, name):
    o = Organization(name=name, slug=f"v2-{uuid.uuid4().hex[:8]}", is_synthetic=True, is_sandbox=True)
    db.add(o)
    db.commit()
    return o.id


@pytest.fixture
def fake(monkeypatch):
    f = FakeSvc()
    monkeypatch.setattr("app.services.ai.service.get_ai_service", lambda: f)
    monkeypatch.setenv("POLICY_AI_VERIFY_FRACTION", "1.0")
    monkeypatch.setenv("POLICY_AI_MIN_BATCH", "1")
    return f


def test_sections_keep_heading_page_offsets_hash():
    s = v2.sections(DOC)
    h = {x["heading"]: x for x in s}
    assert h["AC-17 Remote Access"]["page"] == 1 and h["Travel"]["page"] == 2
    a = h["AC-2 Account Management"]
    assert DOC[a["start"]:a["end"]] == a["text"] and len(a["hash"]) == 16


def test_batched_validated_and_not_examined(fake):
    with SessionLocal() as db:
        org = _org(db, "V2 A")
    out, st = v2.analyze_ai(DOC, uuid.uuid4(), org, TODO, {"ac-2": "Account Management", "ac-17": "Remote Access", "ia-5": "Authenticator Management"}, "cat")
    assert out["ac-2"]["ac-2_obj.d"]["status"] == "met" and out["ac-2"]["ac-2_obj.d"]["section"] == "AC-2 Account Management"
    assert out["ac-2"]["ac-2_obj.d"]["page"] == 1 and out["ac-2"]["ac-2_obj.d"]["offset"] > 0
    assert st["invalid_items"] >= 1 and "zz-9" not in out, "IDs that were not requested are dropped"
    assert st["requirements"] == 4 and st["verification_sample"] == 1 and st["examined"] == 3, st
    asked = [r for c in fake.calls for r in c]
    assert sorted(asked) == sorted(set(asked)), "every requirement asked exactly once"


def test_cache_tenant_scoped_and_incremental(fake):
    with SessionLocal() as db:
        a, b = _org(db, "V2 cache A"), _org(db, "V2 cache B")
    titles = {"ac-2": "Account Management", "ac-17": "Remote Access"}
    todo = TODO[:2]
    v2.analyze_ai(DOC, uuid.uuid4(), a, todo, titles, "cat")
    n1 = len(fake.calls)
    _, st = v2.analyze_ai(DOC, uuid.uuid4(), a, todo, titles, "cat")
    assert len(fake.calls) == n1 and st["cache_hits"] == st["batches"], "unchanged repeat is served from tenant A's cache"
    _, stb = v2.analyze_ai(DOC, uuid.uuid4(), b, todo, titles, "cat")
    assert stb["cache_hits"] == 0 and len(fake.calls) > n1, "identical document in tenant B never hits tenant A's cache"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PolicyAiCache).where(PolicyAiCache.org_id == b)) >= 1
    n2 = len(fake.calls)
    edited = DOC.replace("Remote Access\nThe organization", "Remote Access\nRemote sessions are logged. The organization")
    _, sti = v2.analyze_ai(edited, uuid.uuid4(), a, todo, titles, "cat")
    assert sti["cache_hits"] >= 1 and 0 < len(fake.calls) - n2 < sti["batches"] + 1, "only batches touching the edited section re-run"


def test_no_transaction_during_ai_and_no_idle_in_transaction_after(fake, monkeypatch):
    """No pooled connection is checked out (so none can idle in a transaction) while an AI call runs; the pool returns to baseline.
    (pg_stat_activity is shared with other processes, so the check uses this process's pool.)"""
    monkeypatch.setenv("POLICY_AI_WORKERS", "1")
    pool = get_engine().pool
    seen = []
    orig = fake.run

    async def spy(*a, **k):
        seen.append(pool.checkedout())
        return await orig(*a, **k)
    monkeypatch.setattr(fake, "run", spy)
    with SessionLocal() as db:
        org = _org(db, "V2 idle")
    before = pool.checkedout()
    v2.analyze_ai(DOC, uuid.uuid4(), org, TODO, {}, "cat")
    assert seen and max(seen) == before, f"connections checked out during AI calls: {seen} (baseline {before})"
    assert pool.checkedout() == before, "pool back to baseline"
    with get_engine().connect() as c:
        mine = c.execute(text("select count(*) from pg_stat_activity where pid = pg_backend_pid() and state like 'idle in transaction%'")).scalar()
    assert mine == 0
