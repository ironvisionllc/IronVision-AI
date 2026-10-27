"""PII at registration: one Yes/No. Yes adds the privacy controls (FIPS: SP 800-53B privacy baseline; NSS: CNSSI 1253 Privacy Overlay
variant for the impact level); No adds nothing; toggling adds/removes with audit; existing systems are not changed."""
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent, System
from app.services import pii
from tests.conftest import auth
from tests.test_cnssi_params import _mk  # noqa: F401  (NSS helper)
from tests.test_sandbox import _signup, signup_on  # noqa: F401

FIPS = {"baseline_key": "moderate", "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}


@pytest.fixture(scope="module")
def org(client, signup_on):  # noqa: F811
    t = _signup(client, f"pii-{uuid.uuid4().hex[:6]}@example.com", "PII Org")
    h = auth(t["access_token"])
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])  # noqa: E731
    return {"h": h, "role": role}


def _new(client, org, name, **kw):
    r = client.post("/api/v1/systems", json={"name": name, "acronym": f"P{uuid.uuid4().hex[:4]}", **FIPS, **kw}, headers=org["h"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _ctl(client, org, sid):
    return {x["control_id"] for x in client.get(f"/api/v1/systems/{sid}/workbench/controls", params={"limit": 5000}, headers=org["h"]).json()}


def test_fips_yes_adds_privacy_baseline_with_previewed_count_no_adds_nothing(client, org):
    pre = client.get("/api/v1/privacy/preview", params={"mode": "fips199", "level": "moderate", "baseline_key": "moderate"}, headers=org["h"]).json()
    assert pre["count"] > 0 and "Privacy Overlay" in pre["note"] and f"({pre['count']} controls)" in pre["note"]
    yes, no = _new(client, org, "PII yes", processes_pii=True), _new(client, org, "PII no", processes_pii=False)
    added = _ctl(client, org, yes) - _ctl(client, org, no)
    assert len(added) == pre["count"] and "pt-2" in added
    v = client.get(f"/api/v1/systems/{yes}/pii", headers=org["h"]).json()
    assert v["answer"] == "yes" and v["applied"] == "privacy_baseline" and v["source"] == "registration"
    assert client.get(f"/api/v1/systems/{yes}/select", headers=org["h"]).json()["privacy_state"]["label"].startswith("Applied from registration (PII = Yes)")
    assert client.get(f"/api/v1/systems/{no}/pii", headers=org["h"]).json()["applied"] is None
    with SessionLocal() as db:
        ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "system.pii_answered", AuditEvent.entity_id == yes))
        assert ev and ev.after["processes_pii"] is True and ev.after["source"] == "registration"


def test_nss_yes_adds_privacy_overlay_variant_for_impact_level(client, org):
    with SessionLocal() as db:
        key, ids = pii.target_ids(db, "cnssi1253", "moderate")
    assert key == "cnssi-privacy-moderate" and ids
    sid = _mk(client, org)
    with SessionLocal() as db:
        s = db.get(System, uuid.UUID(sid))
        level = s.categorization
    before = _ctl(client, org, sid)
    want = client.get(f"/api/v1/systems/{sid}/pii", headers=org["h"]).json()["yes"]
    r = client.put(f"/api/v1/systems/{sid}/pii", json={"processes_pii": True}, headers=org["h"])
    assert r.status_code == 200, r.text
    assert r.json()["privacy"] == pii.overlay_key_for(level)
    assert len(_ctl(client, org, sid) - before) == want["count"] > 0


def test_toggle_adds_and_removes_with_audit_statements_kept(client, org):
    sid = _new(client, org, "PII toggle", processes_pii=False)
    base = _ctl(client, org, sid)
    v = client.get(f"/api/v1/systems/{sid}/pii", headers=org["h"]).json()
    assert client.put(f"/api/v1/systems/{sid}/pii", json={"processes_pii": True}, headers=org["h"]).json()["applied"] == "privacy_baseline"
    assert len(_ctl(client, org, sid) - base) == v["yes"]["count"]
    no = client.get(f"/api/v1/systems/{sid}/pii", headers=org["h"]).json()
    assert no["no_affects"] and "pt-2" in no["no_affects"]
    out = client.put(f"/api/v1/systems/{sid}/pii", json={"processes_pii": False}, headers=org["h"]).json()
    assert out["removed"] == "privacy_baseline" and out["privacy"] is None
    assert "pt-2" in _ctl(client, org, sid), "removal never deletes assignments (statements/evidence kept); flagged beyond baseline"
    with SessionLocal() as db:
        n = len(db.scalars(select(AuditEvent).where(AuditEvent.action == "system.pii_answered", AuditEvent.entity_id == sid)).all())
    assert n == 3
    assert client.put(f"/api/v1/systems/{sid}/pii", json={"processes_pii": True}, headers=org["role"]("leadership_viewer")).status_code == 403


def test_existing_systems_unchanged(client, org):
    sid = _new(client, org, "Legacy PTA")
    with SessionLocal() as db:
        s = db.get(System, uuid.UUID(sid))
        s.pta = {"pii_status": "unknown", "pii_types": "names"}
        db.commit()
    before = _ctl(client, org, sid)
    v = client.get(f"/api/v1/systems/{sid}/pii", headers=org["h"]).json()
    assert v["answer"] == "not_answered" and v["applied"] is None
    with SessionLocal() as db:
        s = db.get(System, uuid.UUID(sid))
        assert s.pta == {"pii_status": "unknown", "pii_types": "names"} and s.processes_pii is None
    assert _ctl(client, org, sid) == before
