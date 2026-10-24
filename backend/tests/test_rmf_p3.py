"""RMF Accuracy release – Phase 3: evidence actions (10)."""
import hashlib
import uuid

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent, ControlAssignment, Evidence, EvidenceControl, TrRow
from app.services.rmf import store_evidence
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401
from tests.test_tr import _import, _rows, populated, ws, _ap  # noqa: F401


def _make(ws, name="firewall_config.txt", data=b"SYNTHETIC v1 config"):  # noqa: F811
    with SessionLocal() as db:
        ev = store_evidence(db, uuid.UUID(ws["sid"]), name, data, "configuration", "isso@example.com", "test upload")
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(ws["sid"])).limit(1))
        db.add(EvidenceControl(evidence_id=ev.id, assignment_id=a.id))
        db.commit()
        return str(ev.id), a.control_id


def test_new_version_keeps_old_object_and_flags_dependents(client, ws):  # noqa: F811
    eid, ctl = _make(ws)
    c = ws["stig_ctl"]
    wid = _import(client, ws, populated([(_ap(c).split("(")[0], f"{_ap(c)}.1", ws["stig_cci"].replace("CCI-", ""))]), name="TR-ev.xlsx")
    rid = _rows(client, ws, wid)[7]["id"]
    with SessionLocal() as db:
        db.get(TrRow, uuid.UUID(rid)).sources = [{"kind": "evidence", "id": eid}]
        db.commit()
    isso = ws["role"]("isso")
    assert client.post(f"/api/v1/evidence/{eid}/versions", data={"reason": "x"}, files={"file": ("c.txt", b"v2")}, headers=isso).status_code == 422, "reason required"
    assert client.post(f"/api/v1/evidence/{eid}/versions", data={"reason": "Bad type"}, files={"file": ("c.exe", b"MZ")}, headers=isso).status_code == 415
    r = client.post(f"/api/v1/evidence/{eid}/versions", data={"reason": "Updated after the firewall change"}, files={"file": ("firewall_config_v2.txt", b"SYNTHETIC v2 config")}, headers=isso)
    assert r.status_code == 201, r.text
    m = r.json()
    assert m["version"] == 2 and m["sha256"] == hashlib.sha256(b"SYNTHETIC v2 config").hexdigest() and m["replacement_reason"].startswith("Updated")
    assert [v["version"] for v in m["versions"]] == [2, 1] and m["versions"][1]["sha256"] == hashlib.sha256(b"SYNTHETIC v1 config").hexdigest()
    assert m["flagged_for_revalidation"] == {"control_mappings": 1, "tr_rows": 1} and m["related_controls"][0]["needs_revalidation"]
    assert client.get(f"/api/v1/evidence/{eid}/download", params={"version": 1}, headers=isso).content == b"SYNTHETIC v1 config", "old object kept"
    assert client.get(f"/api/v1/evidence/{eid}/download", headers=isso).content == b"SYNTHETIC v2 config"
    with SessionLocal() as db:
        assert any("Evidence changed – re-review" in f and eid in f for f in db.get(TrRow, uuid.UUID(rid)).flags)
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "evidence.version_added", AuditEvent.entity_id == eid))


def test_unauthorized_replacement_and_history_visibility(client, ws):  # noqa: F811
    eid, _ = _make(ws, "scan_policy.txt", b"SYNTHETIC policy")
    lead = ws["role"]("leadership_viewer")
    assert client.post(f"/api/v1/evidence/{eid}/versions", data={"reason": "Not allowed to do this"}, files={"file": ("x.txt", b"x")}, headers=lead).status_code == 403
    assert "versions" not in client.get(f"/api/v1/evidence/{eid}", headers=lead).json(), "history only for authorized roles"
    other = auth(_signup(client, f"ev-{uuid.uuid4().hex[:6]}@example.com", "Other Evidence Org")["access_token"])
    assert client.get(f"/api/v1/evidence/{eid}", headers=other).status_code == 404
    assert client.post(f"/api/v1/evidence/{eid}/remove", json={"reason": "cross-tenant attempt"}, headers=other).status_code == 404


def test_logical_removal_legal_hold_and_references(client, ws):  # noqa: F811
    eid, ctl = _make(ws, "old_diagram.png", b"\x89PNG\r\n\x1a\nSYNTHETIC")
    isso, admin = ws["role"]("isso"), ws["role"]("platform_admin")
    assert client.post(f"/api/v1/evidence/{eid}/legal-hold", json={"on": True, "reason": "Litigation hold"}, headers=isso).status_code == 403
    assert client.post(f"/api/v1/evidence/{eid}/legal-hold", json={"on": True, "reason": "Litigation hold"}, headers=admin).status_code == 200
    assert client.post(f"/api/v1/evidence/{eid}/remove", json={"reason": "Superseded diagram"}, headers=isso).status_code == 423
    client.post(f"/api/v1/evidence/{eid}/legal-hold", json={"on": False, "reason": "Hold released"}, headers=admin)
    r = client.post(f"/api/v1/evidence/{eid}/remove", json={"reason": "Superseded diagram"}, headers=isso)
    assert r.status_code == 200 and r.json()["status"] == "removed" and r.json()["related_controls"][0]["removed"]
    ledger = client.get(f"/api/v1/systems/{ws['sid']}/evidence", headers=isso).json()
    assert eid not in {e["id"] for e in ledger} and eid in {e["id"] for e in client.get(f"/api/v1/systems/{ws['sid']}/evidence", params={"include_removed": True}, headers=isso).json()}
    assert client.get(f"/api/v1/evidence/{eid}", headers=isso).json()["versions"], "history still resolves"
    with SessionLocal() as db:
        ev = db.get(Evidence, uuid.UUID(eid))
        assert ev.removed_reason == "Superseded diagram" and db.scalar(select(EvidenceControl).where(EvidenceControl.evidence_id == ev.id)).removed_at
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "evidence.removed", AuditEvent.entity_id == eid))
    assert client.post(f"/api/v1/evidence/{eid}/versions", data={"reason": "Bring it back"}, files={"file": ("x.txt", b"x")}, headers=isso).status_code == 409
