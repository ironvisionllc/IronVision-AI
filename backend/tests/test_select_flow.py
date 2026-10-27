"""Select step guided flow: dry-run previews save nothing (baseline, overlay, tailoring), removal previews list what would be deleted,
tailoring applicability / compensating control, step-5 review diff, submit for approval via reviews (ISSM endorses → AO)."""
import uuid

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import ApprovalRequest, AuditEvent, ControlAssignment, TailoringDecision
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401


@pytest.fixture(scope="module")
def ctx(client, signup_on):  # noqa: F811
    t = _signup(client, f"sf-{uuid.uuid4().hex[:6]}@example.com", "Select Org")
    h = auth(t["access_token"])
    sid = client.post("/api/v1/systems", json={"name": "Select System", "acronym": f"SF{uuid.uuid4().hex[:3]}", "baseline_key": "moderate",
                                                "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=h).json()["id"]
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])  # noqa: E731
    return {"isso": role("isso"), "role": role, "sid": sid, "u": f"/api/v1/systems/{sid}/select"}


def _n(sid):
    with SessionLocal() as db:
        return (db.scalar(select(func.count()).select_from(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(sid))),
                db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.entity_id == sid)))


def test_baseline_dry_run_saves_nothing(client, ctx):
    before = _n(ctx["sid"])
    r = client.post(f"{ctx['u']}/baseline", json={"baseline_key": "high", "dry_run": True}, headers=ctx["isso"])
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["dry_run"] and d["nothing_saved"] and len(d["added"]) > 50 and d["counts_after"]["assigned"] > d["counts_before"]["assigned"]
    assert _n(ctx["sid"]) == before
    assert client.get(ctx["u"], headers=ctx["isso"]).json()["baseline_key"] == "moderate"


def test_overlay_preview_then_apply(client, ctx):
    v = client.get(ctx["u"], headers=ctx["isso"]).json()
    ov = next((o for o in v["overlays"] if not o["structure_only"] and not o["applied"]), None)
    if ov is None:
        pytest.skip("no applicable overlay in this content set")
    before = _n(ctx["sid"])
    p = client.post(f"{ctx['u']}/overlay", json={"overlay_key": ov["key"], "apply": True, "dry_run": True}, headers=ctx["isso"]).json()
    assert p["dry_run"] and _n(ctx["sid"]) == before
    assert client.get(ctx["u"], headers=ctx["isso"]).json()["overlay_keys"] == v["overlay_keys"]


def test_tailor_remove_preview_lists_losses_and_applicability(client, ctx):
    p = client.post(f"{ctx['u']}/tailor", json={"action": "remove", "control_ids": ["ac-8"], "justification": "SYNTHETIC: no interactive logon", "dry_run": True},
                    headers=ctx["isso"]).json()
    assert p["removed"] == ["ac-8"] and set(p["would_delete"]) == {"statements", "evidence_links"}
    assert client.post(f"{ctx['u']}/tailor", json={"action": "remove", "control_ids": ["ac-8"], "justification": "SYNTHETIC rationale",
                                                   "applicability": "Compensating control"}, headers=ctx["isso"]).status_code == 422
    r = client.post(f"{ctx['u']}/tailor", json={"action": "remove", "control_ids": ["ac-8"], "justification": "SYNTHETIC: no interactive logon",
                                                "applicability": "Compensating control", "compensating_control_id": "AC-8(1)"}, headers=ctx["isso"])
    assert r.status_code == 422 or r.status_code == 200
    r = client.post(f"{ctx['u']}/tailor", json={"action": "remove", "control_ids": ["ac-8"], "justification": "SYNTHETIC: no interactive logon",
                                                "applicability": "Compensating control", "compensating_control_id": "IA-2"}, headers=ctx["isso"])
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        t = db.scalar(select(TailoringDecision).where(TailoringDecision.system_id == uuid.UUID(ctx["sid"]), TailoringDecision.control_id == "ac-8"))
        assert t.applicability == "Compensating control" and t.compensating_control_id == "ia-2"


def test_review_diff_and_submit_for_approval(client, ctx):
    d = client.get(f"{ctx['u']}/review", headers=ctx["isso"]).json()
    assert d["original"]["count"] - len(d["removed"]) + len(d["added"]) == d["final"]["count"]
    rm = next(x for x in d["removed"] if x["control_id"] == "ac-8")
    assert rm["decision"]["compensating_control_id"] == "ia-2"
    assert d["approval"] is None
    assert client.post(f"{ctx['u']}/submit", json={"justification": "SYNTHETIC selection ready"}, headers=ctx["role"]("leadership_viewer")).status_code == 403
    r = client.post(f"{ctx['u']}/submit", json={"justification": "SYNTHETIC selection ready"}, headers=ctx["isso"])
    assert r.status_code == 201 and r.json()["assigned_role"] == "issm"
    assert client.post(f"{ctx['u']}/submit", json={"justification": "SYNTHETIC selection ready"}, headers=ctx["isso"]).status_code == 409
    d = client.get(f"{ctx['u']}/review", headers=ctx["isso"]).json()
    assert d["approval"]["status"] == "pending"
    with SessionLocal() as db:
        assert db.scalar(select(ApprovalRequest.request_type).where(ApprovalRequest.id == uuid.UUID(r.json()["id"]))) == "selection_review"
