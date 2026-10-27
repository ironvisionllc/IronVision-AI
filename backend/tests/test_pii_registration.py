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


def _counts(client, org, sid):
    c = client.get(f"/api/v1/systems/{sid}/select", headers=org["h"]).json()["counts"]
    return c


def _stmt(sid, cid, text):
    from app.models import ControlAssignment, Implementation
    with SessionLocal() as db:
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(sid), ControlAssignment.control_id == cid))
        rows = list(db.scalars(select(Implementation).where(Implementation.assignment_id == a.id)))
        for i in rows:
            i.narrative = text
        if not rows:
            db.add(Implementation(assignment_id=a.id, version=1, narrative=text, implementation_status="implemented"))
        db.commit()


def _narr(sid, cid):
    from app.models import ControlAssignment, Implementation
    with SessionLocal() as db:
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(sid), ControlAssignment.control_id == cid))
        return sorted({(i.narrative, i.needs_reconsideration) for i in db.scalars(select(Implementation).where(Implementation.assignment_id == a.id))}) if a else None


def test_toggle_fips_add_remove_readd_counts_consistent_statements_retained(client, org):
    sid = _new(client, org, "PII toggle", processes_pii=False)
    base, c0 = _ctl(client, org, sid), _counts(client, org, sid)
    v = client.get(f"/api/v1/systems/{sid}/pii", headers=org["h"]).json()
    assert client.put(f"/api/v1/systems/{sid}/pii", json={"processes_pii": True}, headers=org["h"]).json()["applied"] == "privacy_baseline"
    added = _ctl(client, org, sid) - base
    assert len(added) == v["yes"]["count"] > 0 and "pt-2" in added
    c1 = _counts(client, org, sid)
    _stmt(sid, "pt-2", "SYNTHETIC PT-2 statement")
    out = client.put(f"/api/v1/systems/{sid}/pii", json={"processes_pii": False}, headers=org["h"]).json()
    assert out["removed"] == "privacy_baseline" and out["privacy"] is None and len(out["removed_ids"]) == len(added)
    assert "pt-2" in out["retained"]
    assert _ctl(client, org, sid) == base, "the privacy-baseline controls are removed from the assignment"
    c2 = out["counts"]
    assert c2 == _counts(client, org, sid) == c0 and all(not isinstance(x, int) or x >= 0 for x in c2.values())
    assert client.get(f"/api/v1/systems/{sid}/pii", headers=org["h"]).json()["no_affects"] == []
    with SessionLocal() as db:
        ev = db.scalar(select(AuditEvent).where(AuditEvent.action == "system.privacy_controls_retained", AuditEvent.entity_id == sid))
        assert "pt-2" in ev.after["controls"] and ev.after["retained"]["pt-2"]["implementations"][0]["narrative"] == "SYNTHETIC PT-2 statement"
    back = client.put(f"/api/v1/systems/{sid}/pii", json={"processes_pii": True}, headers=org["h"]).json()
    assert _ctl(client, org, sid) - base == added and _counts(client, org, sid) == c1, "add → remove → re-add returns to the same counts"
    assert "pt-2" in back["restored_statements"] and _narr(sid, "pt-2") == [("SYNTHETIC PT-2 statement", True)], "restored, flagged for review"
    with SessionLocal() as db:
        n = len(db.scalars(select(AuditEvent).where(AuditEvent.action == "system.pii_answered", AuditEvent.entity_id == sid)).all())
    assert n == 4
    assert client.put(f"/api/v1/systems/{sid}/pii", json={"processes_pii": True}, headers=org["role"]("leadership_viewer")).status_code == 403


def test_toggle_nss_add_remove_readd(client, org):
    sid = _mk(client, org)
    base, c0 = _ctl(client, org, sid), _counts(client, org, sid)
    on = client.put(f"/api/v1/systems/{sid}/pii", json={"processes_pii": True}, headers=org["h"]).json()
    assert on["privacy"].startswith("cnssi-privacy-")
    added, c1 = _ctl(client, org, sid) - base, _counts(client, org, sid)
    assert added
    cid = sorted(added)[0]
    _stmt(sid, cid, "SYNTHETIC NSS privacy statement")
    off = client.put(f"/api/v1/systems/{sid}/pii", json={"processes_pii": False}, headers=org["h"]).json()
    assert off["removed"] == on["privacy"] and cid in off["retained"]
    assert _ctl(client, org, sid) == base and _counts(client, org, sid) == c0
    back = client.put(f"/api/v1/systems/{sid}/pii", json={"processes_pii": True}, headers=org["h"]).json()
    assert _ctl(client, org, sid) - base == added and _counts(client, org, sid) == c1
    assert cid in back["restored_statements"] and _narr(sid, cid) == [("SYNTHETIC NSS privacy statement", True)]


def test_registration_preview_needs_baseline_and_uses_it(client, org):
    none = client.get("/api/v1/privacy/preview", params={"mode": "fips199", "level": "moderate"}, headers=org["h"]).json()
    assert none["count"] is None and "Select a baseline" in none["note"]
    mod = client.get("/api/v1/privacy/preview", params={"mode": "fips199", "level": "moderate", "baseline_key": "moderate"}, headers=org["h"]).json()
    sid = _new(client, org, "Preview check", processes_pii=True)
    assert len(_ctl(client, org, sid) - _ctl(client, org, _new(client, org, "Preview none", processes_pii=False))) == mod["count"]
    nss = client.get("/api/v1/privacy/preview", params={"mode": "cnssi1253", "level": "moderate", "trigraph": "M-M-M"}, headers=org["h"]).json()
    assert nss["count"] is not None and nss["count"] > 0
    assert client.get("/api/v1/privacy/preview", params={"mode": "cnssi1253", "trigraph": "X-1"}, headers=org["h"]).status_code == 422


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
