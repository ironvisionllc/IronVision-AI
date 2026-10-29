"""Cross-tenant isolation sweep: tenant B calls EVERY parameterless GET route and every {system_id}/{poam_id} GET route with tenant A's ids;
no response may contain tenant A's marker, email or ids (regression for the /audit-events leak)."""
import re
import uuid

import pytest

from app.main import app
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

SKIP = {"/api/v1/health", "/api/v1/auth/oidc/login", "/api/v1/auth/oidc/callback", "/api/v1/auth/logout"}


@pytest.fixture(scope="module")
def tenants(client, signup_on):  # noqa: F811
    mark = f"ZZMARK{uuid.uuid4().hex[:8]}"
    ea = f"{mark.lower()}@example.com"
    ta = _signup(client, ea, f"{mark} Org")
    ha = auth(ta["access_token"])
    sid = client.post("/api/v1/systems", json={"name": f"{mark} System", "acronym": f"Z{uuid.uuid4().hex[:4]}", "baseline_key": "low",
                                                "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=ha).json()["id"]
    isso_a = auth(client.post("/api/v1/sandbox/act-as", json={"role": "isso"}, headers=ha).json()["access_token"])
    pid = client.post("/api/v1/poams", json={"system_id": sid, "weakness": f"{mark} weakness", "control_ids": ["ac-2"]}, headers=isso_a).json()["id"]
    from app.services import (
        emass_migration as em,  # Import Center history / PPSM / migration report must not leak either
    )
    up = client.post("/api/v1/emass-imports", files={"file": (f"{mark}_ppsm.xlsx", em.sample("ppsm"))}, data={"system_id": sid}, headers=isso_a)
    assert up.status_code == 201, up.text
    client.post(f"/api/v1/systems/{sid}/uploads", files={"file": (f"{mark}.ckl", b'<?xml version="1.0"?><CHECKLIST><STIGS><iSTIG><VULN/></iSTIG></STIGS></CHECKLIST>')}, headers=isso_a)
    tb = _signup(client, f"iso-b-{uuid.uuid4().hex[:6]}@example.com", "Isolation B Org")
    hb = auth(tb["access_token"])
    personas = {r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=hb).json()["access_token"])
                for r in ("isso", "issm", "sca", "ao", "platform_admin")}
    return {"mark": mark, "email": ea, "sid": sid, "pid": pid, "b": personas, "a": {"isso": isso_a}}


def _routes():
    for path, ops in app.openapi()["paths"].items():
        if "get" in ops and path.startswith("/api/v1") and path not in SKIP and not path.endswith(("/download", "/export")):
            yield path


def _leaks(text: str, t: dict) -> list[str]:
    return [k for k in ("mark", "email", "sid", "pid") if t[k].lower() in text.lower()]


def test_parameterless_get_routes_do_not_leak(client, tenants):
    checked, leaks = [], []
    for path in _routes():
        if "{" in path:
            continue
        for role, h in tenants["b"].items():
            r = client.get(path, headers=h)
            checked.append(path)
            if r.status_code == 200 and (found := _leaks(r.text, tenants)):
                leaks.append((path, role, found))
    print(f"checked {len(set(checked))} parameterless GET routes × {len(tenants['b'])} personas")
    assert not leaks, leaks


def test_other_tenant_ids_are_refused(client, tenants):
    leaks = []
    n = 0
    for path in _routes():
        params = re.findall(r"{(\w+)}", path)
        if not params or set(params) - {"system_id", "poam_id", "id", "control_id"}:
            continue
        url = path.replace("{system_id}", tenants["sid"]).replace("{poam_id}", tenants["pid"]).replace("{id}", tenants["sid"]).replace("{control_id}", "ac-2")
        for role, h in tenants["b"].items():
            n += 1
            r = client.get(url, headers=h)
            if r.status_code == 200 and _leaks(r.text, tenants):
                leaks.append((path, role, r.status_code))
    print(f"checked {n} id-route calls")
    assert n > 50 and not leaks, leaks


def test_test_plan_export_cross_tenant_404(client, tenants):
    """/export routes are skipped by the generic id sweep (binary bodies) – Test Plan export is checked explicitly."""
    for role, h in tenants["b"].items():
        for path in (f"/api/v1/systems/{tenants['sid']}/test-plan/export", f"/api/v1/systems/{tenants['sid']}/test-plan/export/summary"):
            r = client.get(path, headers=h)
            assert r.status_code in (403, 404) and not _leaks(r.text, tenants), (path, role, r.status_code)
            if role in ("isso", "issm", "sca", "ao"):
                assert r.status_code == 404, (path, role, r.status_code)


def test_autosave_drafts_and_sessions_not_shared_across_tenants(client, tenants):
    """New auto-save endpoints: /drafts/{kind} and /autosave/close only ever touch the caller's own rows."""
    a, b = tenants["a"]["isso"], tenants["b"]["isso"]
    assert client.put("/api/v1/drafts/registration", json={"data": {"f": {"name": "TENANT-A-SECRET-DRAFT"}}}, headers=a).status_code == 200
    rb = client.get("/api/v1/drafts/registration", headers=b)
    assert rb.status_code in (200, 403) and "TENANT-A-SECRET-DRAFT" not in rb.text
    client.put(f"/api/v1/systems/{tenants['sid']}/iscm", json={"narrative": "A open session"}, headers={**a, "X-Autosave": "1"})
    from sqlalchemy import func as sfunc
    from sqlalchemy import select as sselect

    from app.db import SessionLocal
    from app.models import AutosaveSession
    with SessionLocal() as db:
        n_open = db.scalar(sselect(sfunc.count()).select_from(AutosaveSession).where(AutosaveSession.closed_at.is_(None)))
    client.post("/api/v1/autosave/close", json={}, headers=b)
    with SessionLocal() as db:
        assert db.scalar(sselect(sfunc.count()).select_from(AutosaveSession).where(AutosaveSession.closed_at.is_(None))) == n_open, "B cannot close A's sessions"
    client.post("/api/v1/autosave/close", json={}, headers=a)
    client.delete("/api/v1/drafts/registration", headers=a)


def test_audit_events_scoped(client, tenants):
    r = client.get("/api/v1/audit-events?limit=500", headers=tenants["b"]["isso"])
    # B's own authz.denied events legitimately echo the A ids B itself tried (earlier test) – A's identity/content must never appear
    assert r.status_code == 200 and not [k for k in _leaks(r.text, tenants) if k in ("mark", "email")]
    assert all(e.get("actor_email") is None or "zzmark" not in (e.get("actor_email") or "") for e in r.json())


def test_job_status_and_jobs_list_scoped(client, tenants):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Job, User
    with SessionLocal() as db:
        ua = db.scalar(select(User).where(User.email == tenants["email"]))
        j = Job(job_type="noop.test", payload={"system_id": tenants["sid"]}, status="succeeded", requested_by=ua.id)
        db.add(j)
        db.commit()
        jid = str(j.id)
    assert client.get(f"/api/v1/jobs/{jid}", headers=tenants["b"]["isso"]).status_code == 404
    assert jid not in client.get("/api/v1/jobs?limit=100", headers=tenants["b"]["issm"]).text
