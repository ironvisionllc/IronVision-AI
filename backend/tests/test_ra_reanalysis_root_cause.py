"""RA re-analysis root cause: a non-AI coverage run must never say "language not present" and stale/keyword-only results are flagged."""
import uuid

import pytest

from app.db import SessionLocal
from app.services import policy_coverage as pc


@pytest.fixture()
def db_session():
    db = SessionLocal()
    yield db
    db.rollback()
    db.close()


def test_keyword_only_label_never_missing(db_session):
    """Every deterministic (no-AI) non-xx-1 row that is not met is 'partial' + Low confidence + the keyword-only label."""
    from app.models import PolicyRequirementCoverage
    rows = db_session.query(PolicyRequirementCoverage).filter(PolicyRequirementCoverage.source == "deterministic",
                                                              PolicyRequirementCoverage.reason.like(pc.KEYWORD_ONLY + "%")).limit(50).all()
    for r in rows:
        assert r.status == "partial" and r.confidence == "Low"


def test_analyze_without_ai_labels_keyword_only(db_session):
    from app.models import Policy
    p = db_session.query(Policy).filter(Policy.analysis_status == "analyzed", Policy.text_content.isnot(None)).first()
    if p is None:
        pytest.skip("no analysed policy in this database")
    an = dict(p.analysis or {})
    p.analysis = {**an, "analyzer": "deterministic", "coverage_version": "coverage-old"}  # forces a full non-AI recompute (nothing kept)
    out = pc.analyze(db_session, p)
    bad = [(r.control_id, r.requirement_id) for r in out if r.source == "deterministic" and not pc.is_xx1(r.control_id) and r.status == "missing"]
    assert not bad, bad
    kw = [r for r in out if r.source == "deterministic" and not pc.is_xx1(r.control_id) and r.status != "met"]
    assert all(r.reason.startswith(pc.KEYWORD_ONLY) for r in kw)
    st = pc.auditor_status(db_session, p)
    assert st["stale"] is True and st["est_cost_usd"] > 0
    db_session.rollback()


from tests.test_sandbox import signup_on  # noqa: E402,F401


def test_reanalyze_latest_role_and_tenant(client, signup_on):  # noqa: F811
    from tests.conftest import auth
    from tests.test_sandbox import _signup
    t = _signup(client, f"ra-{uuid.uuid4().hex[:6]}@example.com", "RA Root Cause Org")
    h = auth(t["access_token"])
    ao = auth(client.post("/api/v1/sandbox/act-as", json={"role": "ao"}, headers=h).json()["access_token"])
    assert client.post(f"/api/v1/policies/{uuid.uuid4()}/reanalyze?latest=true", headers=h).status_code == 404
    pols = client.get("/api/v1/policies", headers=h).json()
    items = pols if isinstance(pols, list) else pols.get("items", [])
    if not items:
        pytest.skip("sandbox has no policies")
    assert client.post(f"/api/v1/policies/{items[0]['id']}/reanalyze?latest=true", headers=ao).status_code == 403
