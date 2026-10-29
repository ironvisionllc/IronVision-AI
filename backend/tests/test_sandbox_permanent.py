"""Platform-admin "Make permanent" for self-signup sandboxes: protected sandboxes are skipped by inactivity expiry (no countdown),
sandbox personas / non-admins get 403, real tenants and unknown ids 404, undo makes it purgeable again; audited both ways."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent, Organization, User
from app.services import sandbox as sbx
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401


def _real_admin():
    """A real (non-persona) platform admin in a NON-sandbox org."""
    from tests.test_sod import _real_user
    with SessionLocal() as db:
        tag = uuid.uuid4().hex[:6]
        org = Organization(name=f"Platform ops {tag}", slug=f"platform-ops-{tag}", is_sandbox=False)
        db.add(org)
        db.commit()
        oid = org.id
    return _real_user(oid, "platform_admin")


@pytest.fixture(scope="module")
def sb(client, signup_on):  # noqa: F811
    t = _signup(client, f"perm-{uuid.uuid4().hex[:6]}@example.com", "Permanent Trial Org")
    me = client.get("/api/v1/sandbox/status", headers=auth(t["access_token"])).json()
    with SessionLocal() as db:
        org = db.scalar(select(Organization).join(User, User.org_id == Organization.id).where(User.email == me["operator"]["email"]))
        return {"h": auth(t["access_token"]), "org": org.id}


def _age(org_id, days):
    with SessionLocal() as db:
        o = db.get(Organization, org_id)
        o.last_activity_at = sbx.now() - timedelta(days=days)
        db.commit()


def test_rbac_and_isolation(client, sb):
    admin_persona = auth(client.post("/api/v1/sandbox/act-as", json={"role": "platform_admin"}, headers=sb["h"]).json()["access_token"])
    assert client.get("/api/v1/admin/sandboxes", headers=admin_persona).status_code == 403, "a sandbox Admin persona is not a platform admin"
    assert client.post(f"/api/v1/admin/sandboxes/{sb['org']}/permanence", json={"permanent": True, "confirm": True}, headers=sb["h"]).status_code == 403
    adm = _real_admin()
    assert client.post(f"/api/v1/admin/sandboxes/{uuid.uuid4()}/permanence", json={"permanent": True, "confirm": True}, headers=adm).status_code == 404
    with SessionLocal() as db:
        real = db.scalar(select(Organization).where(Organization.is_sandbox.is_(False)))
    assert client.post(f"/api/v1/admin/sandboxes/{real.id}/permanence", json={"permanent": True, "confirm": True}, headers=adm).status_code == 404, "real tenants are not managed here"
    assert client.post(f"/api/v1/admin/sandboxes/{sb['org']}/permanence", json={"permanent": True}, headers=adm).status_code == 422, "confirm required"


def test_make_permanent_skips_purge_and_undo_restores(client, sb):
    adm = _real_admin()
    _age(sb["org"], sbx.inactivity_days() - 3)
    row = next(o for o in client.get("/api/v1/admin/sandboxes", headers=adm).json()["items"] if o["id"] == str(sb["org"]))
    assert row["days_until_deletion"] == 3 and row["last_activity_at"] and not row["permanent"]
    r = client.post(f"/api/v1/admin/sandboxes/{sb['org']}/permanence", json={"permanent": True, "confirm": True}, headers=adm)
    assert r.status_code == 200 and r.json()["permanent"] and r.json()["days_until_deletion"] is None
    st = client.get("/api/v1/sandbox/status", headers=sb["h"]).json()
    assert st["permanent"] is True and st["expiry"] is None and st["sandbox"] is True, "still a sandbox, no countdown"
    _age(sb["org"], sbx.inactivity_days() + 5)
    with SessionLocal() as db:
        sbx.run_expiry(db)
        db.commit()
        assert db.get(Organization, sb["org"]).sandbox_status != "purged"
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "org.made_permanent", AuditEvent.entity_id == str(sb["org"])))
    u = client.post(f"/api/v1/admin/sandboxes/{sb['org']}/permanence", json={"permanent": False, "confirm": True}, headers=adm)
    assert u.status_code == 200 and not u.json()["permanent"]
    with SessionLocal() as db:
        org = db.get(Organization, sb["org"])
        assert sbx.purge_refusal(db, org) is None, "purge-eligible again"
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "org.made_expirable", AuditEvent.entity_id == str(sb["org"])))
    assert client.get("/api/v1/auth/provider").json().get("sandbox_inactivity_days") == sbx.inactivity_days()
