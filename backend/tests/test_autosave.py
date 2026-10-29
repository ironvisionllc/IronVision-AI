"""Auto-save: drafts persist, no workflow state change, locked items 423, SoD confirm 428, conflicts 409, ONE coalesced audit event per
editing session (closed on leave / explicit action / 5 min idle), registration draft is not a system, drafts are per user and tenant."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import (
    AuditEvent,
    AutosaveSession,
    ControlAssignment,
    Implementation,
    System,
)
from app.services import autosave as asv
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

SYS = {"baseline_key": "low", "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}
AS = {"X-Autosave": "1"}


@pytest.fixture(scope="module")
def ctx(client, signup_on):  # noqa: F811
    t = _signup(client, f"as-{uuid.uuid4().hex[:6]}@example.com", "AS Org")
    h = auth(t["access_token"])
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])  # noqa: E731
    isso = role("isso")
    sid = client.post("/api/v1/systems", json={"name": "Autosave Sys", "acronym": "ASV", **SYS}, headers=isso).json()["id"]
    with SessionLocal() as db:
        ctl = db.scalar(select(ControlAssignment.control_id).where(ControlAssignment.system_id == uuid.UUID(sid)).order_by(ControlAssignment.control_id))
    return {"sid": sid, "isso": isso, "role": role, "ctl": ctl}


def _h(ctx, base=None, extra=None, who="isso"):
    return {**ctx[who], **AS, **({"X-Base-Version": base} if base else {}), **(extra or {})}


def _events(entity_id, action=None):
    with SessionLocal() as db:
        q = select(AuditEvent).where(AuditEvent.entity_id == str(entity_id))
        if action:
            q = q.where(AuditEvent.action == action)
        return list(db.scalars(q.order_by(AuditEvent.occurred_at)))


def _close(client, ctx, who="isso"):
    return client.post("/api/v1/autosave/close", json={}, headers=ctx[who]).json()["closed"]


def test_implementation_draft_in_place_coalesced_and_locked(client, ctx):
    url = f"/api/v1/systems/{ctx['sid']}/workbench/controls/{ctx['ctl']}/implementation"
    r = client.put(url, json={"narrative": "First words", "implementation_status": "planned"}, headers=_h(ctx))
    assert r.status_code == 200, r.text
    v = r.json()
    for i, text in enumerate(["First words and more", "First words and more text"]):
        r = client.put(url, json={"narrative": text, "implementation_status": "planned"}, headers=_h(ctx, v["updated_at"]))
        assert r.status_code == 200, r.text
        assert r.json()["version"] == v["version"] and r.json()["review_status"] == "draft", "same draft version – no new version, no review routing"
        v = r.json()
    aid = v["assignment_id"]
    assert _events(aid, "implementation.saved") == [], "nothing audited while the session is open"
    stale = client.put(url, json={"narrative": "theirs?", "implementation_status": "planned"}, headers=_h(ctx, "2020-01-01T00:00:00+00:00"))
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "conflict" and stale.json()["detail"]["theirs"]["narrative"] == "First words and more text"
    assert _close(client, ctx) >= 1
    ev = _events(aid, "implementation.saved")
    assert len(ev) == 1 and ev[0].details["autosave"] is True and ev[0].details["saves"] == 3 and ev[0].details["closed_by"] == "left_record"
    assert ev[0].after["narrative"] == "First words and more text"
    with SessionLocal() as db:  # version history keeps the final value
        cur = db.scalar(select(Implementation).where(Implementation.assignment_id == uuid.UUID(aid), Implementation.is_current.is_(True)))
        assert cur.narrative == "First words and more text" and cur.version == 1
        cur.review_status = "approved"
        db.commit()
    locked = client.put(url, json={"narrative": "edit approved", "implementation_status": "planned"}, headers=_h(ctx))
    assert locked.status_code == 423 and locked.json()["detail"]["code"] == "locked"
    manual = client.put(url, json={"narrative": "edit approved", "implementation_status": "planned"}, headers=ctx["isso"])
    assert manual.status_code == 200 and manual.json()["version"] == 2, "the explicit Save still starts a new version"


def test_iscm_draft_autosave_locked_when_pending_and_explicit_submit_closes_session(client, ctx):
    url = f"/api/v1/systems/{ctx['sid']}/iscm"
    r = client.put(url, json={"narrative": "Monitor monthly", "scope": "All"}, headers=_h(ctx))
    assert r.status_code == 200, r.text
    ver = r.json()["version"]
    r = client.put(url, json={"narrative": "Monitor monthly and quarterly", "scope": "All"}, headers=_h(ctx, ver))
    assert r.status_code == 200 and r.json()["strategy"]["status"] == "draft"
    assert client.put(url, json={"narrative": "x", "scope": "All"}, headers=_h(ctx, ver)).status_code == 409
    sub = client.post(f"{url}/submit", headers=ctx["isso"])
    assert sub.status_code == 200, sub.text
    st_id = sub.json()["strategy"]["id"] if "strategy" in sub.json() else None
    with SessionLocal() as db:
        evs = list(db.scalars(select(AuditEvent).where(AuditEvent.action.in_(["iscm.strategy_saved", "iscm.strategy_submitted"]),
                                                       AuditEvent.occurred_at >= func.now() - timedelta(minutes=2)).order_by(AuditEvent.seq)))
    evs = [e for e in evs if st_id is None or e.entity_id == st_id]
    saved = [e for e in evs if e.action == "iscm.strategy_saved" and (e.details or {}).get("autosave")]
    assert len(saved) == 1 and saved[0].details["saves"] == 2 and saved[0].details["closed_by"] == "explicit_action"
    assert [e.action for e in evs][-2:] == ["iscm.strategy_saved", "iscm.strategy_submitted"], "the coalesced save precedes the explicit submit"
    pend = client.put(url, json={"narrative": "edit while pending", "scope": "All"}, headers=_h(ctx))
    assert pend.status_code == 423, "pending ISSM approval → not auto-saved"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(AutosaveSession).where(AutosaveSession.entity_type.like("%iscm%"), AutosaveSession.closed_at.is_(None))) == 0


def test_poam_and_milestone_autosave_no_status_change(client, ctx):
    p = client.post("/api/v1/poams", json={"system_id": ctx["sid"], "weakness": "Autosave weakness", "control_ids": [ctx["ctl"]]}, headers=ctx["isso"])
    assert p.status_code == 201, p.text
    p = p.json()
    r = client.patch(f"/api/v1/poams/{p['id']}", json={"remediation_plan": "Patch the hosts"}, headers=_h(ctx, p["updated_at"]))
    assert r.status_code == 200 and r.json()["status"] == p["status"]
    r = client.patch(f"/api/v1/poams/{p['id']}", json={"remediation_plan": "Patch the hosts, then rescan"}, headers=_h(ctx, r.json()["updated_at"]))
    assert r.status_code == 200
    assert client.patch(f"/api/v1/poams/{p['id']}", json={"status": "in_progress"}, headers=_h(ctx)).status_code == 422, "status is explicit"
    assert client.patch(f"/api/v1/poams/{p['id']}", json={"root_cause": "x"}, headers=_h(ctx, p["updated_at"])).status_code == 409
    m = client.post(f"/api/v1/poams/{p['id']}/milestones", json={"title": "Milestone one"}, headers=ctx["isso"]).json()
    mid = client.get(f"/api/v1/poams/{p['id']}", headers=ctx["isso"]).json()["milestones"][0]["id"]
    for t in ("Milestone one renamed", "Milestone one renamed again"):
        r = client.patch(f"/api/v1/poam-milestones/{mid}", json={"title": t}, headers=_h(ctx))
        assert r.status_code == 200 and r.json()["status"] != "completed"
    assert client.patch(f"/api/v1/poam-milestones/{mid}", json={"status": "completed"}, headers=_h(ctx)).status_code == 422
    _close(client, ctx)
    ev = _events(p["id"], "poam.updated")
    assert len(ev) == 1 and ev[0].details["saves"] == 2 and ev[0].after["remediation_plan"] == "Patch the hosts, then rescan"
    hist = client.get(f"/api/v1/poams/{p['id']}", headers=ctx["isso"]).json()["history"]
    assert sum(1 for h in hist if h["action"] == "updated") == 1 and sum(1 for h in hist if h["action"] == "milestone_updated") == 1, "history coalesced too"
    assert m is not None
    with SessionLocal() as db:  # locked while in review
        from app.models import Poam
        db.get(Poam, uuid.UUID(p["id"])).status = "closure_review"
        db.commit()
    assert client.patch(f"/api/v1/poams/{p['id']}", json={"root_cause": "y"}, headers=_h(ctx)).status_code == 423
    assert client.patch(f"/api/v1/poam-milestones/{mid}", json={"title": "Locked milestone"}, headers=_h(ctx)).status_code == 423


def test_emass_plan_risk_autosave_partial_and_conflict(client, ctx):
    url = f"/api/v1/systems/{ctx['sid']}/workbench/controls/{ctx['ctl']}/emass"
    v = client.get(url, headers=ctx["isso"]).json()
    r = client.put(f"{url}/plan", json={"implementation_status": "Planned", "responsible_entities": "Ops team"}, headers=_h(ctx, v.get("updated_at")))
    assert r.status_code == 200, r.text  # required eMASS fields may still be missing – auto-save keeps the partial draft
    ver = r.json()["emass"]["updated_at"]
    r = client.put(f"{url}/risk", json={"likelihood": "Low"}, headers=_h(ctx, ver))
    assert r.status_code == 200, r.text
    assert client.put(f"{url}/risk", json={"likelihood": "High"}, headers=_h(ctx, ver)).status_code == 409
    _close(client, ctx)


def test_tr_row_autosave_sod_confirm_and_lock(client, ctx):
    exp = client.get(f"/api/v1/systems/{ctx['sid']}/test-plan/export", headers=ctx["isso"]).content
    wb = client.post(f"/api/v1/systems/{ctx['sid']}/tr/test-plan/import", files={"file": ("plan.xlsx", exp)}, headers=ctx["isso"]).json()
    rows = client.get(f"/api/v1/tr/workbooks/{wb['id']}/rows", headers=ctx["isso"]).json()["items"]
    r0 = rows[0]
    url = f"/api/v1/tr/workbooks/{wb['id']}/decide"
    body = {"action": "edit", "row_ids": [r0["id"]], "values": {"test_results": "Examined the account list"}, "justification": ""}
    sca = ctx["role"]("sca")
    r = client.post(url, json=body, headers={**sca, **AS, "X-Base-Version": r0["updated_at"]})
    assert r.status_code == 428 and r.json()["detail"]["code"] == "sod_confirm_required", "approver must confirm before the first auto-save"
    r = client.post(url, json=body, headers={**sca, **AS, "X-Base-Version": r0["updated_at"], "X-Sod-Confirmed": "1"})
    assert r.status_code == 200, r.text
    ver = r.json()["versions"][r0["id"]]
    assert client.post(url, json={**body, "values": {"compliance_status": "Compliant"}}, headers={**sca, **AS, "X-Sod-Confirmed": "1"}).status_code == 422
    assert client.post(url, json=body, headers={**sca, **AS, "X-Base-Version": r0["updated_at"], "X-Sod-Confirmed": "1"}).status_code == 409
    row = next(x for x in client.get(f"/api/v1/tr/workbooks/{wb['id']}/rows", headers=ctx["isso"]).json()["items"] if x["id"] == r0["id"])
    assert row["state"] != "approved" and ver
    with SessionLocal() as db:
        from app.models import TrRow
        db.get(TrRow, uuid.UUID(r0["id"])).state = "approved"
        db.commit()
    assert client.post(url, json=body, headers={**sca, **AS, "X-Sod-Confirmed": "1"}).status_code == 423
    _close(client, ctx, "isso")


def test_asset_autosave_conflict_and_single_event(client, ctx):
    a = client.post(f"/api/v1/systems/{ctx['sid']}/assets", json={"name": "web-01"}, headers=ctx["isso"]).json()
    url = f"/api/v1/systems/{ctx['sid']}/assets/{a['id']}"
    v = a["updated_at"]
    for os_ in ("RHEL 8", "RHEL 9"):
        r = client.patch(url, json={"name": "web-01", "os": os_}, headers=_h(ctx, v))
        assert r.status_code == 200, r.text
        v = r.json()["updated_at"]
    assert client.patch(url, json={"name": "web-01", "os": "Win"}, headers=_h(ctx, a["updated_at"])).status_code == 409
    _close(client, ctx)
    ev = [e for e in _events(a["id"]) if e.details and e.details.get("autosave")]
    assert len(ev) == 1 and ev[0].details["saves"] == 2 and ev[0].after["os"] == "RHEL 9"


def test_categorization_autosave_keeps_one_draft_revision_and_locks_after_approval(client, ctx):
    url = f"/api/v1/systems/{ctx['sid']}/categorization"
    g = client.get(url, headers=ctx["isso"]).json()
    body = {"mode": "fips199", "information_types": [{"id": "D.16.3"}], "rationale": "draft one"}
    if g.get("record_status") not in (None, "draft"):
        assert client.put(url, json=body, headers=_h(ctx)).status_code == 423
        return
    r1 = client.put(url, json=body, headers=_h(ctx, g.get("record_version")))
    assert r1.status_code == 200, r1.text
    r2 = client.put(url, json={**body, "rationale": "draft two"}, headers=_h(ctx, r1.json()["version"]))
    assert r2.status_code == 200 and r2.json()["calculation"]["revision"] == r1.json()["calculation"]["revision"], "same draft revision"
    assert r2.json()["calculation"]["record_status"] == "draft", "still needs AO approval"


def test_idle_close_writes_one_event(client, ctx):
    url = f"/api/v1/systems/{ctx['sid']}/iscm"
    with SessionLocal() as db:
        u = db.scalar(select(AutosaveSession.user_id).limit(1))
        s = AutosaveSession(user_id=u, entity_type="test_entity", entity_id="idle-1", action="test.autosaved", before={"a": 1}, after={"a": 2}, saves=4,
                            started_at=asv._now() - timedelta(minutes=9), last_at=asv._now() - timedelta(minutes=6))
        db.add(s)
        db.commit()
        assert asv.close_idle(db)["closed"] >= 1
    ev = _events("idle-1", "test.autosaved")
    assert len(ev) == 1 and ev[0].details["closed_by"] == "idle" and ev[0].before == {"a": 1} and ev[0].after == {"a": 2}
    assert url


def test_registration_draft_is_private_and_not_a_system(client, ctx, signup_on):  # noqa: F811
    with SessionLocal() as db:
        n0 = db.scalar(select(func.count()).select_from(System))
    r = client.put("/api/v1/drafts/registration", json={"data": {"f": {"name": "Not yet registered"}}}, headers=ctx["isso"])
    assert r.status_code == 200 and r.json()["data"]["f"]["name"] == "Not yet registered"
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(System)) == n0
    assert client.get("/api/v1/drafts/registration", headers=ctx["role"]("issm")).json()["data"] is None, "per user"
    other = _signup(client, f"as-b-{uuid.uuid4().hex[:6]}@example.com", "AS Other")
    hb = auth(client.post("/api/v1/sandbox/act-as", json={"role": "isso"}, headers=auth(other["access_token"])).json()["access_token"])
    assert client.get("/api/v1/drafts/registration", headers=hb).json()["data"] is None, "per tenant"
    assert client.get("/api/v1/drafts/registration", headers=ctx["role"]("leadership_viewer")).status_code == 403
    assert client.get("/api/v1/drafts/unknown", headers=ctx["isso"]).status_code == 404
    assert client.delete("/api/v1/drafts/registration", headers=ctx["isso"]).status_code == 204
    assert client.get("/api/v1/drafts/registration", headers=ctx["isso"]).json()["data"] is None


def test_preference_stored(client, ctx):
    r = client.put("/api/v1/me/preferences", json={"autosave": False}, headers=ctx["isso"])
    assert r.status_code == 200 and r.json().get("autosave") is False
    client.put("/api/v1/me/preferences", json={"autosave": True}, headers=ctx["isso"])
