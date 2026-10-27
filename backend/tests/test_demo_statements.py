"""Item 6: the demo/sandbox seed fills SYNTHETIC implementation statements for a subset of base controls (so the demo SSP has content);
real (non-sandbox) orgs never get seeded statements; the SSP count of 'with statements' counts only non-empty narratives."""
import uuid

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import ControlAssignment, Implementation, System, User
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401


def _stmts(org_id):
    with SessionLocal() as db:
        q = (select(Implementation.narrative).join(ControlAssignment, ControlAssignment.id == Implementation.assignment_id)
             .join(System, System.id == ControlAssignment.system_id).where(System.org_id == org_id, func.length(func.trim(Implementation.narrative)) > 0))
        return list(db.scalars(q))


def test_demo_seed_has_synthetic_statements(client, signup_on):  # noqa: F811
    email = f"st-{uuid.uuid4().hex[:6]}@example.com"
    h = auth(_signup(client, email, "Statements Org")["access_token"])
    assert client.post("/api/v1/sandbox/demo-data", headers=h).status_code in (200, 201, 202)
    with SessionLocal() as db:
        org = db.scalar(select(User.org_id).where(User.email == email))
        ltp = db.scalar(select(System.id).where(System.org_id == org, System.acronym == "LTP"))
    st = _stmts(org)
    assert len(st) >= 40 and all(s.startswith("SYNTHETIC demo statement") for s in st)
    isso = auth(client.post("/api/v1/sandbox/act-as", json={"role": "isso"}, headers=h).json()["access_token"])
    chk = client.get(f"/api/v1/systems/{ltp}/documents/ssp/check", headers=isso).json()
    no_stmt = next(m for m in chk["missing"] if "no implementation statement" in m)
    total = int(no_stmt.split(" of ")[1].split()[0])
    assert int(no_stmt.split()[0]) < total  # some controls now have statements


def test_real_org_signup_without_demo_data_has_no_statements(client, signup_on):  # noqa: F811
    email = f"st0-{uuid.uuid4().hex[:6]}@example.com"
    _signup(client, email, "Clean Org")
    with SessionLocal() as db:
        org = db.scalar(select(User.org_id).where(User.email == email))
    assert _stmts(org) == []


def test_health_reports_running_code_version(client, monkeypatch):
    from app import build_info as bi
    bi.build_info.cache_clear()
    monkeypatch.setenv("BUILD_SHA", "abc123def4567890")
    monkeypatch.setenv("BUILD_TIME", "2026-10-27T11:00:00Z")
    b = client.get("/api/v1/health").json()["build"]
    assert b == {"git_sha": "abc123def4567890", "build_time": "2026-10-27T11:00:00Z", "source": "image build args"}
    bi.build_info.cache_clear()
    monkeypatch.delenv("BUILD_SHA")
    assert len(client.get("/api/v1/health").json()["build"]["git_sha"] or "") in (0, 40)
    bi.build_info.cache_clear()
