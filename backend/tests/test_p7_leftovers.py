"""P7 leftovers: selection_review approval freezes the approved control list (no auto-apply, drift visible); SLCM due notifications."""
import uuid

from sqlalchemy import select

from app.db import SessionLocal
from app.models import ApprovalRequest, Notification, System
from tests.test_sandbox import signup_on  # noqa: F401
from tests.test_select_flow import ctx  # noqa: F401


def test_selection_review_approval_records_selection_and_shows_drift(client, ctx):  # noqa: F811
    r = client.post(f"{ctx['u']}/submit", json={"justification": "SYNTHETIC selection ready"}, headers=ctx["isso"])
    assert r.status_code in (201, 409), r.text
    with SessionLocal() as db:
        rid = db.scalar(select(ApprovalRequest.id).where(ApprovalRequest.system_id == uuid.UUID(ctx["sid"]),
                                                         ApprovalRequest.request_type == "selection_review", ApprovalRequest.status == "pending"))
    for role, action in (("issm", "endorse"), ("ao", "approve")):
        d = client.post(f"/api/v1/reviews/{rid}/decisions", json={"action": action, "rationale": "SYNTHETIC selection reviewed"}, headers=ctx["role"](role))
        assert d.status_code == 200, d.text
    a = client.get(f"{ctx['u']}/review", headers=ctx["isso"]).json()
    assert a["approval"]["status"] == "approved" and a["approval"]["approved_count"] == a["final"]["count"]
    assert a["approval"]["changed_since_approval"] is False
    with SessionLocal() as db:
        req = db.get(ApprovalRequest, rid)
        assert len(req.payload["approved_control_ids"]) == a["final"]["count"]
    # a later tailoring change is visible as drift (nothing is silently re-approved)
    assert client.post(f"{ctx['u']}/tailor", json={"action": "remove", "control_ids": ["pe-8"], "justification": "SYNTHETIC: no visitor logs"},
                       headers=ctx["isso"]).status_code == 200
    assert client.get(f"{ctx['u']}/review", headers=ctx["isso"]).json()["approval"]["changed_since_approval"] is True


def test_slcm_due_notifies_isso_and_issm_once():
    from datetime import date
    from app.services import iscm
    with SessionLocal() as db:
        s = db.scalar(select(System).limit(1))
        items = [{"control_id": "au-2", "status": "overdue"}, {"control_id": "ac-2", "status": "due_soon"}]
        c = {"overdue": 1, "due_soon": 1, "never_monitored": 0}
        from app.services.rmf import role_users
        users = {u for r in ("isso", "issm") for u in role_users(db, s.org_id, s.id, r)}
        n1 = iscm.notify_due(db, s, items, c)
        db.flush()
        n2 = iscm.notify_due(db, s, items, c)
        key = f"slcm_due:{s.id}:{date.today().isoformat()}:1:1"
        rows = db.scalars(select(Notification).where(Notification.dedupe_key == key)).all()
        assert n1 == len(users) and n2 == 0 and len(rows) == len(users)
        assert all("SLCM" in r.title and "AU-2" in (r.body or "") for r in rows)
        assert iscm.notify_due(db, s, [], {"overdue": 0, "due_soon": 0, "never_monitored": 3}) == 0
        db.rollback()
