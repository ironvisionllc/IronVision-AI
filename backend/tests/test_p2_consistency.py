"""P2: RA-5 requirement counts have one rule with scoped labels (base only vs including assigned enhancements, approved mappings only);
privacy state has one source per framework; policy links use the same PolicyControlMap source as coverage (proposed flagged, not "no policy")."""
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import ControlAssignment, Policy, PolicyControlMap, System
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401


@pytest.fixture(scope="module")
def ctx(client, signup_on):  # noqa: F811
    t = _signup(client, f"p2-{uuid.uuid4().hex[:6]}@example.com", "P2 Org")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "P2 System", "acronym": f"P2{uuid.uuid4().hex[:3]}", "baseline_key": "high",
                                                "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    isso = auth(client.post("/api/v1/sandbox/act-as", json={"role": "isso"}, headers=h).json()["access_token"])
    with SessionLocal() as db:
        s = db.get(System, uuid.UUID(sid))
        a = Policy(org_id=s.org_id, policy_key="SYN-RA", title="SYNTHETIC Risk Assessment Policy", version=1, status="current")
        b = Policy(org_id=s.org_id, policy_key="SYN-AC", title="SYNTHETIC Access Policy", version=1, status="current")
        db.add_all([a, b])
        db.flush()
        db.add(PolicyControlMap(policy_id=a.id, org_id=s.org_id, control_id="ra-5", status="mapped", source="statement_language", confidence="High",
                                basis="SYNTHETIC", snippets=["SYNTHETIC"]))
        db.add(PolicyControlMap(policy_id=b.id, org_id=s.org_id, control_id="ra-5", status="proposed", source="statement_language", confidence="Low",
                                basis="SYNTHETIC", snippets=["SYNTHETIC"]))
        db.commit()
    return {"sid": sid, "isso": isso, "h": h}


def test_ra5_counts_scoped_and_reconcile(client, ctx):
    r = client.get(f"/api/v1/systems/{ctx['sid']}/workbench/controls/RA-5/requirement-counts", headers=ctx["isso"]).json()
    assert r["base_only"]["ccis"] == 14 and r["base_only"]["objectives"] == 10 and r["base_only"]["requirements"] == 24
    inc = r["including_assigned_enhancements"]
    with SessionLocal() as db:
        assigned = sorted(c for c in db.scalars(select(ControlAssignment.control_id).where(ControlAssignment.system_id == uuid.UUID(ctx["sid"])))
                          if c == "ra-5" or c.startswith("ra-5."))
    assert inc["controls"] == assigned and inc["requirements"] == sum(p["requirements"] for p in r["per_control"])
    assert inc["requirements"] >= r["base_only"]["requirements"] and inc["ccis_unique"] >= 14
    base = next(p for p in r["per_control"] if p["control_id"] == "ra-5")
    assert len(base["policies"]) == 1 and len(base["proposed_policies"]) == 1  # proposed never counted as linked/met


def test_summary_line_states_scope():
    from app.services.policy_coverage import summary_line
    s = {"met": 3, "total": 24, "ccis": 14, "objectives": 10, "gaps": []}
    assert "base control only" in summary_line("ra-5", s) and "this enhancement only" in summary_line("ra-5.2", s)


def test_policy_link_same_source_as_coverage(ctx):
    from app.api.v1.workbench import _policies_for
    with SessionLocal() as db:
        out = _policies_for(db, uuid.UUID(ctx["sid"]), "ra-5")
    assert any("Risk Assessment Policy v1" in p and "proposed" not in p for p in out)
    assert any("Access Policy v1 (mapping proposed" in p for p in out)


def test_privacy_state_single_source(client, ctx):
    u = f"/api/v1/systems/{ctx['sid']}/select"
    with SessionLocal() as db:
        s = db.get(System, uuid.UUID(ctx["sid"]))
        s.processes_pii, s.include_privacy = True, True
        db.commit()
    d = client.get(u, headers=ctx["isso"]).json()
    assert d["privacy_state"] == {"applied": True, "source": "privacy_baseline", "overlay_key": None, "label": "Privacy baseline applied"}
    from app.api.v1.rmf_steps import privacy_state
    cn = type("S", (), {"categorization_mode": "cnssi1253", "overlay_keys": ["cnssi-privacy-low"], "include_privacy": False})()
    assert privacy_state(cn)["applied"] and privacy_state(cn)["source"] == "privacy_overlay"
    cn.overlay_keys = []
    assert not privacy_state(cn)["applied"]
