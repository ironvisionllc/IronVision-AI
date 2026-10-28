"""Large policies: a truncated or timed-out AI batch never yields "missing" and never drops a requirement – the row falls back to the
checklist result, which the coverage stage shows as needs manual review (partial / Low). AI is faked, zero cost."""
import uuid
from types import SimpleNamespace

import pytest

from app.db import SessionLocal
from app.models import Organization
from app.services import policy_analyzer_v2 as v2
from app.services.ai.service import AIOutputTruncatedError
from tests.test_policy_v2 import DOC, TODO
from tests.test_sandbox import signup_on  # noqa: F401

TITLES = {"ac-2": "Account Management", "ac-17": "Remote Access", "ia-5": "Authenticator Management"}


class BrokenSvc:
    """ac-2 batches are always cut off (even single items); ia-5 batches always time out; others answer 'met'."""

    def __init__(self):
        self.provider, self.calls, self.configured = SimpleNamespace(model="fake/model"), 0, True

    async def run(self, pid, ver, vars, max_tokens=None, cache_prefix_var=None):
        import json
        self.calls += 1
        reqs = json.loads(vars["requirements"])
        ctls = {r["control_id"] for r in reqs}
        if "ac-2" in ctls:
            raise AIOutputTruncatedError("reply cut off at max_tokens (finish_reason=length)")
        if "ia-5" in ctls:
            raise RuntimeError("openrouter: request timed out after 60s (AI_TIMEOUT_SECONDS)")
        items = [SimpleNamespace(control_id=r["control_id"], requirement_id=r["requirement_id"], status="partial", quote="", section="S1",
                                 rationale="Generic.") for r in reqs]
        return SimpleNamespace(output=SimpleNamespace(items=items), model="fake/model", usage={})


@pytest.fixture
def broken(monkeypatch):
    f = BrokenSvc()
    monkeypatch.setattr("app.services.ai.service.get_ai_service", lambda: f)
    monkeypatch.setattr(v2.time, "sleep", lambda s: None)
    monkeypatch.setenv("POLICY_AI_CACHE", "0")
    return f


@pytest.mark.parametrize("whole", ["1", "0"])
def test_truncated_and_timed_out_batches_never_missing_never_dropped(broken, monkeypatch, whole):
    monkeypatch.setenv("POLICY_AI_WHOLE_DOC", whole)
    with SessionLocal() as db:
        o = Organization(name=f"FB {uuid.uuid4().hex[:8]}", slug=f"fb-{uuid.uuid4().hex[:8]}", is_synthetic=True, is_sandbox=True)
        db.add(o)
        db.commit()
        oid = o.id
    out, st = v2.analyze_ai(DOC, uuid.uuid4(), oid, TODO, TITLES, "cat")
    assert st["truncated"] >= 1 and st["failed_batches"] >= 1 and st["retries"] >= 1
    for cid in ("ac-2", "ia-5"):
        assert all(v is None or v.get("status") != "missing" for v in (out.get(cid) or {}).values())


def test_full_analysis_with_failed_batches_writes_every_row_as_review_not_missing(client, signup_on, broken, monkeypatch):  # noqa: F811
    from pathlib import Path

    from sqlalchemy import select

    from app.models import ControlAssignment, Policy, PolicyControlMap, System
    from app.services import policy_coverage as pc
    from tests.conftest import auth
    from tests.test_sandbox import _signup
    monkeypatch.setenv("POLICY_ANALYZER", "v2")
    t = _signup(client, f"fb-{uuid.uuid4().hex[:6]}@example.com", "Failed Batch Org")
    sid = client.post("/api/v1/systems", json={"name": "FB", "acronym": f"FB{uuid.uuid4().hex[:3]}", "baseline_key": "moderate",
                                                "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]},
                      headers=auth(t["access_token"])).json()["id"]
    text = (Path(__file__).resolve().parents[2] / "samples/policies/access_control_policy.txt").read_text()
    with SessionLocal() as db:
        s = db.get(System, uuid.UUID(sid))
        ids = set(db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == s.id)))
        ctl = [c for c in ("ac-2", "ia-5", "ac-1") if c in ids]
        p = Policy(org_id=s.org_id, policy_key="SYN-FB", title="SYNTHETIC", version=1, status="current", text_content=text, analysis_status="analyzed")
        db.add(p)
        db.flush()
        for c in ctl:
            db.add(PolicyControlMap(policy_id=p.id, org_id=s.org_id, control_id=c, status="mapped", source="statement_language",
                                    confidence="High", basis="SYNTHETIC", snippets=["SYNTHETIC"]))
        db.commit()
        pre = pc.prefetch_ai(db, p, ctl)
        rows = pc.analyze(db, p, use_ai=True, ai_prefetched=pre)
        assert len(rows) == pc.in_scope_requirements(db, ctl), "a cut-off / timed-out batch must not drop requirements"
        bad = [r for r in rows if r.control_id in ("ac-2", "ia-5") and r.status == "missing"]
        assert not bad, [(r.requirement_id, r.reason[:80]) for r in bad]
        review = [r for r in rows if r.control_id in ("ac-2", "ia-5") and r.status != "met"]
        assert review and all(r.status == "partial" and r.confidence == "Low" for r in review)
        db.rollback()
