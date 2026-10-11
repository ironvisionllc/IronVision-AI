import os
import re
import uuid
from types import SimpleNamespace

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import AuditEvent, ControlAssignment, Finding, FindingControlMap, FindingObservation, IngestRun, System
from app.security.rbac import has_permission
from app.services.ingest.pipeline import process_run, receive_upload
from tests.conftest import auth

SAMPLES = os.environ.get("SAMPLES_DIR", "/app/samples")


def _sys(db, acr):
    return db.scalar(select(System).where(System.acronym == acr))


def test_register_moderate_system_assigns_baseline(client, token):
    body = {"name": "Pytest Moderate System", "acronym": "PTM", "baseline_key": "moderate",
            "confidentiality_impact": "Moderate", "integrity_impact": "Moderate", "availability_impact": "Low"}
    r = client.post("/api/v1/systems", json=body, headers=auth(token("issm@aegisrmf.demo")))
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    with SessionLocal() as db:
        n = db.scalar(select(func.count()).select_from(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(sid)))
        assert n == 287
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(sid), ControlAssignment.control_id == "ac-2"))
        assert a.assessment_status == "not_assessed" and a.implementation_status in ("planned", "inherited")
    seeded = client.get("/api/v1/systems", headers=auth(token("issm@aegisrmf.demo"))).json()
    assert any(s["acronym"] == "LTP" for s in seeded)


def test_leadership_cannot_register(client, token):
    r = client.post("/api/v1/systems", json={"name": "Nope", "baseline_key": "low"}, headers=auth(token("leadership.viewer@aegisrmf.demo")))
    assert r.status_code == 403


def test_stig_cci_mapping_has_provenance():
    with SessionLocal() as db:
        ltp = _sys(db, "LTP")
        maps = db.scalars(select(FindingControlMap).join(Finding).where(Finding.system_id == ltp.id, FindingControlMap.cci_id == "CCI-000366")).all()
        assert maps, "expected CCI-000366 mappings from STIG checklists"
        assert {m.control_id for m in maps} == {"cm-6"}
        m = maps[0]
        assert m.mapping_source == "stig_cci" and m.review_status and m.confidence and m.source


def test_duplicate_and_rescan_dedup():
    path = f"{SAMPLES}/stig/ltp_db-server-01.ckl"
    data = open(path, "rb").read()
    with SessionLocal() as db:
        ltp = _sys(db, "LTP")
        before_f = db.scalar(select(func.count()).select_from(Finding).where(Finding.system_id == ltp.id))
        dup = receive_upload(db, system_id=ltp.id, source_id=None, file_name="ltp_db-server-01.ckl", data=data)
        assert dup.status == "duplicate" and dup.duplicate_of_run_id
        before_o = db.scalar(select(func.count()).select_from(FindingObservation).join(Finding).where(Finding.system_id == ltp.id))
        rescan = data.replace(b"</CHECKLIST>", b"<!-- rescan --></CHECKLIST>")
        run = receive_upload(db, system_id=ltp.id, source_id=None, file_name="ltp_db-server-01_rescan.ckl", data=rescan)
        assert run.status == "queued"
        process_run(db, run.id)
        after_f = db.scalar(select(func.count()).select_from(Finding).where(Finding.system_id == ltp.id))
        after_o = db.scalar(select(func.count()).select_from(FindingObservation).join(Finding).where(Finding.system_id == ltp.id))
        assert after_f == before_f
        assert after_o > before_o
        db.rollback()


def test_acas_kev_maps_via_org_rule_and_queues_ra5(client, token):
    with SessionLocal() as db:
        ltp = _sys(db, "LTP")
        f = db.scalar(select(Finding).where(Finding.system_id == ltp.id, Finding.is_kev.is_(True)))
        assert f is not None
        cids = {m.control_id for m in db.scalars(select(FindingControlMap).where(FindingControlMap.finding_id == f.id))}
        assert {"ra-5", "si-2"} <= cids
        sid = str(ltp.id)
    q = client.get(f"/api/v1/systems/{sid}/workbench/controls", params={"queue": True}, headers=auth(token("isso@aegisrmf.demo"))).json()
    top = [a["control_id"] for a in q[:5]]
    assert "ra-5" in top
    ra5 = next(a for a in q if a["control_id"] == "ra-5")
    assert any(r["code"] == "kev" for r in ra5["reasons"])


def test_unmapped_requires_justification_and_audits(client, token):
    with SessionLocal() as db:
        ltp = _sys(db, "LTP")
        f = db.scalar(select(Finding).where(Finding.system_id == ltp.id, Finding.mapping_status == "unmapped"))
        assert f is not None
        fid = str(f.id)
    h = auth(token("isso@aegisrmf.demo"))
    assert client.post(f"/api/v1/findings/{fid}/map", json={"control_id": "cm-6", "justification": "x"}, headers=h).status_code == 422
    assert client.post(f"/api/v1/findings/{fid}/map", json={"control_id": "cm-6"}, headers=h).status_code == 422
    r = client.post(f"/api/v1/findings/{fid}/map", json={"control_id": "cm-6", "justification": "Configuration setting deviation per ISSO review"}, headers=h)
    assert r.status_code == 200, r.text
    with SessionLocal() as db:
        assert db.get(Finding, uuid.UUID(fid)).mapping_status == "mapped"
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == "finding.mapped", AuditEvent.entity_id == fid))


def test_system_scoped_permission_unit():
    org, s1, s2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ra = [SimpleNamespace(role="isso", scope_type="system", scope_id=s1, org_id=org, revoked_at=None)]
    assert has_permission(ra, "ingest.upload", org, s1)
    assert not has_permission(ra, "ingest.upload", org, s2)


def test_system_role_grant_revoke_audited(client, token):
    with SessionLocal() as db:
        sid = str(_sys(db, "TRS").id)
    h = auth(token("platform.admin@aegisrmf.demo"))
    users = client.get("/api/v1/admin/users", headers=h)
    uid = next(u["id"] for u in users.json() if u["email"] == "sca@aegisrmf.demo") if users.status_code == 200 else None
    if uid is None:
        with SessionLocal() as db:
            from app.models import User
            uid = str(db.scalar(select(User.id).where(User.email == "sca@aegisrmf.demo")))
    r = client.post(f"/api/v1/systems/{sid}/roles", json={"user_id": uid, "role": "sca"}, headers=h)
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    assert client.delete(f"/api/v1/systems/{sid}/roles/{aid}", headers=h).status_code == 204
    assert client.post(f"/api/v1/systems/{sid}/roles", json={"user_id": uid, "role": "sca"},
                       headers=auth(token("leadership.viewer@aegisrmf.demo"))).status_code == 403
    with SessionLocal() as db:
        acts = set(db.scalars(select(AuditEvent.action).where(AuditEvent.entity_id == aid)))
        assert len(acts) >= 2


def test_leadership_cannot_upload(client, token):
    with SessionLocal() as db:
        sid = str(_sys(db, "LTP").id)
    r = client.post(f"/api/v1/systems/{sid}/uploads", files={"file": ("x.ckl", b"<CHECKLIST/>")},
                    headers=auth(token("leadership.viewer@aegisrmf.demo")))
    assert r.status_code == 403


def test_freshness_backdate_marks_stale(client, token):
    h = auth(token("platform.admin@aegisrmf.demo"))
    with SessionLocal() as db:
        ltp = _sys(db, "LTP")
        sid = str(ltp.id)
        run = db.scalar(select(IngestRun).where(IngestRun.system_id == ltp.id, IngestRun.file_name.like("ltp_web-server-03%"), IngestRun.status == "completed"))
        eid = str(run.evidence_id)
    r = client.post(f"/api/v1/demo/evidence/{eid}/collected-at", json={"days_ago": 45}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["state"] in ("stale", "expired")
    led = client.get(f"/api/v1/systems/{sid}/evidence", headers=h).json()
    assert next(e for e in led if e["id"] == eid)["state"] in ("stale", "expired")
    assert client.post(f"/api/v1/demo/evidence/{eid}/collected-at", json={"days_ago": 45},
                       headers=auth(token("isso@aegisrmf.demo"))).status_code == 403


def test_integrity_verification_detects_tamper():
    from app.models import Evidence
    from app.services.evaluation import verify_integrity
    from app.services.storage import get_storage
    with SessionLocal() as db:
        ev = db.scalar(select(Evidence).where(Evidence.file_name == "ltp_ntp-server-14.ckl"))
        get_storage().put(ev.storage_key, b"tampered", "application/octet-stream")
        res = verify_integrity(db, ev.system_id)
        db.refresh(ev)
        assert res["mismatched"] >= 1 and ev.integrity_status == "mismatch"
        db.rollback()


def test_no_real_ips_in_samples():
    import pathlib
    allowed = re.compile(r"^(192\.0\.2|198\.51\.100|203\.0\.113)\.")
    for p in pathlib.Path(SAMPLES).rglob("*.*"):
        for ip in re.findall(rb"\b\d{1,3}(?:\.\d{1,3}){3}\b", p.read_bytes()):
            ip = ip.decode()
            if ip.count(".") == 3 and not ip.startswith(("0.", "1.", "2.", "3.", "4.", "5.")):
                assert allowed.match(ip), f"{p.name}: {ip}"
