import os
import uuid
from datetime import date, timedelta

from sqlalchemy import select

from app.db import SessionLocal
from app.models import (Attestation, AuditEvent, ControlAssignment, Evidence, Finding, FindingControlMap, Notification, Policy, PolicyFinding,
                        System, User)
from tests.conftest import auth

POL = os.environ.get("SAMPLES_DIR", "/app/samples") + "/policies"


def _ltp(db):
    return db.scalar(select(System).where(System.acronym == "LTP"))


def test_inheritance_counts_reconcile(client, token):
    with SessionLocal() as db:
        sid = str(_ltp(db).id)
    d = client.get(f"/api/v1/systems/{sid}/inheritance", headers=auth(token("isso@aegisrmf.demo"))).json()
    c = d["cards"]
    assert c["fully_inherited"] + c["shared"] + c["system_owned"] == c["assigned"] == 291 and c["sum_check"]
    assert c["manual_attestation"] == 38 and c["attestation_overdue"] >= 1
    sh = {x["control_id"]: x for x in d["shared"]}
    assert {"cm-6", "ac-2", "sc-28"} <= set(sh) and sh["cm-6"]["system_responsibility"] and sh["cm-6"]["provider_responsibility"]
    assert sh["cm-6"]["system_part"]["open_findings"] > 0  # provider passing does not satisfy system portion


def test_attestation_owner_only_and_expiry_cascade(client, token):
    owner, isso, admin = auth(token("system.owner@aegisrmf.demo")), auth(token("isso@aegisrmf.demo")), auth(token("platform.admin@aegisrmf.demo"))
    with SessionLocal() as db:
        at = db.scalar(select(Attestation).where(Attestation.control_id == "at-2"))
        aid, sid = str(at.id), str(at.system_id)
    assert client.post(f"/api/v1/attestations/{aid}/attest", headers=owner).status_code == 422  # evidence first
    up = client.post(f"/api/v1/attestations/{aid}/evidence", files={"file": ("training_roster.txt", b"SYNTHETIC roster")}, headers=owner)
    assert up.status_code == 200 and len(up.json()["sha256"]) == 64
    assert client.post(f"/api/v1/attestations/{aid}/attest", headers=isso).status_code == 403
    r = client.post(f"/api/v1/attestations/{aid}/attest", headers=owner)
    assert r.status_code == 200 and r.json()["status"] == "signed" and "not CAC/PIV" in r.json()["signature"]
    with SessionLocal() as db:
        assert db.scalar(select(ControlAssignment.evidence_freshness_status).where(ControlAssignment.system_id == uuid.UUID(sid), ControlAssignment.control_id == "at-2")) == "current"
    assert client.post(f"/api/v1/demo/attestations/{aid}/expire", json={"days_ago": 2}, headers=isso).status_code == 403
    c = client.post(f"/api/v1/demo/attestations/{aid}/expire", json={"days_ago": 2}, headers=admin)
    assert c.status_code == 200 and c.json()["cascade"]["expired"] >= 1
    with SessionLocal() as db:
        at = db.get(Attestation, uuid.UUID(aid))
        assert at.status == "expired" and at.signed_at is not None  # signed record preserved
        assert db.get(Evidence, at.evidence_id).state == "expired"
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(sid), ControlAssignment.control_id == "at-2"))
        assert a.evidence_freshness_status in ("expired", "partially_stale") and any(x["code"] == "expired_evidence" for x in a.reasons)
        assert db.scalar(select(Notification.id).where(Notification.dedupe_key == f"att:{aid}:expired"))
    new = client.post(f"/api/v1/attestations/{aid}/renew", headers=owner)
    assert new.status_code == 201 and new.json()["version"] == 2
    hist = client.get(f"/api/v1/attestations/{aid}/history", headers=owner).json()
    assert [h["version"] for h in hist] == [2, 1] and hist[1]["signed_at"]


def test_sca_independence_and_only_path(client, token):
    with SessionLocal() as db:
        sid = str(_ltp(db).id)
    body = {"objectives": ["AC-03a"], "methods": ["examine", "test"], "result": "satisfied", "findings_text": "Verified"}
    assert client.post(f"/api/v1/systems/{sid}/controls/ac-3/assessments", json=body, headers=auth(token("isso@aegisrmf.demo"))).status_code == 403
    r = client.post(f"/api/v1/systems/{sid}/controls/ac-3/assessments", json=body, headers=auth(token("sca@aegisrmf.demo")))
    assert r.status_code == 201, r.text
    with SessionLocal() as db:
        assert db.scalar(select(ControlAssignment.assessment_status).where(ControlAssignment.system_id == uuid.UUID(sid), ControlAssignment.control_id == "ac-3")) == "satisfied"
        sca = db.scalar(select(User).where(User.email == "sca@aegisrmf.demo"))
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(sid), ControlAssignment.control_id == "ac-4"))
        from app.models import Implementation
        db.add(Implementation(assignment_id=a.id, version=99, narrative="SCA wrote this", implementation_status="implemented", author_id=sca.id))
        db.commit()
    d = client.post(f"/api/v1/systems/{sid}/controls/ac-4/assessments", json=body, headers=auth(token("sca@aegisrmf.demo")))
    assert d.status_code == 403 and "independence" in d.json()["detail"].lower()
    with SessionLocal() as db:
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.action == "authz.denied", AuditEvent.details["reason"].astext == "assessor_independence_violation"))


def test_authorization_decision_ao_only(client, token):
    with SessionLocal() as db:
        sid = str(_ltp(db).id)
    isso, issm, ao, admin = (auth(token(f"{u}@aegisrmf.demo")) for u in ("isso", "issm", "ao", "platform.admin"))
    rq = client.post(f"/api/v1/systems/{sid}/authorization/submit", json={"justification": "Annual package for reauthorization"}, headers=isso)
    assert rq.status_code == 201, rq.text
    rid = rq.json()["id"]
    body = {"request_id": rid, "decision": "ATO_with_conditions", "conditions": "Close P-0015 in 30 days", "expiration": str(date.today() + timedelta(days=365)),
            "rationale": "Residual risk acceptable with conditions"}
    for h in (isso, admin):
        assert client.post(f"/api/v1/systems/{sid}/authorization-decision", json=body, headers=h).status_code == 403
    assert client.post(f"/api/v1/systems/{sid}/authorization-decision", json=body, headers=ao).status_code == 403  # ISSM must endorse first
    assert client.post(f"/api/v1/reviews/{rid}/decisions", json={"action": "endorse", "rationale": "Package complete"}, headers=issm).status_code == 200
    r = client.post(f"/api/v1/systems/{sid}/authorization-decision", json=body, headers=ao)
    assert r.status_code == 200 and r.json()["authorization_status"] == "Authorized (ATO w/ conditions)"
    lead = client.get("/api/v1/dashboard/leadership", headers=auth(token("leadership.viewer@aegisrmf.demo"))).json()
    row = next(s for s in lead["systems"] if s["id"] == sid)
    assert row["authorization_status"] == "Authorized (ATO w/ conditions)" and row["days_to_expiration"] >= 364
    with SessionLocal() as db:
        den = db.scalars(select(AuditEvent.actor_email).where(AuditEvent.action == "authz.denied", AuditEvent.entity_id == sid)).all()
        assert {"isso@aegisrmf.demo", "platform.admin@aegisrmf.demo"} <= set(den)


def test_policy_audit_35_vs_90_confirm_and_dismiss(client, token):
    from worker.handlers import handle_policy_analyze

    isso = auth(token("isso@aegisrmf.demo"))
    with SessionLocal() as db:
        sid = str(_ltp(db).id)
    r = client.post("/api/v1/policies", data={"title": "Access Control Policy", "system_ids": sid, "policy_key": "access-control-policy"},
                    files={"file": ("access_control_policy.docx", open(f"{POL}/access_control_policy.docx", "rb").read())}, headers=isso)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    with SessionLocal() as db:
        handle_policy_analyze(db, {"policy_id": pid})
        db.commit()
        assert db.scalar(select(Policy.status).where(Policy.policy_key == "access-control-policy", Policy.version == 1)) == "superseded"
    d = client.get(f"/api/v1/policies/{pid}", headers=isso).json()
    pf = next(f for f in d["findings"] if f["finding_type"] == "policy_vs_config_difference" and f["control_id"] == "ac-2.3")
    assert pf["status"] == "proposed" and pf["policy_value"] == "35 days" and pf["observed_value"] == "90 days"
    assert any(v["result"] == "Mismatch" and v["control_id"] == "ac-2.3" for v in d["values"])
    assert any(v["result"] == "Match" and v["control_id"] == "ac-7" for v in d["values"])
    c = client.post(f"/api/v1/policy-findings/{pf['id']}/confirm", json={}, headers=isso)
    assert c.status_code == 200
    fid = c.json()["finding_id"]
    with SessionLocal() as db:
        assert set(db.scalars(select(FindingControlMap.control_id).where(FindingControlMap.finding_id == uuid.UUID(fid)))) == {"ac-2.3", "ac-2"}
    wb = client.get(f"/api/v1/systems/{sid}/workbench/controls/ac-2.3", headers=isso).json()
    assert any(f["id"] == fid for f in wb["open_findings"])
    q = client.get(f"/api/v1/systems/{sid}/workbench/controls", params={"queue": True}, headers=isso).json()
    assert any(a["control_id"] == "ac-2.3" for a in q)
    m = client.get(f"/api/v1/findings/{fid}/poam-match", headers=isso).json()
    assert "ac-2.3" in m["prefill"]["control_ids"]
    other = next(f for f in d["findings"] if f["finding_type"] == "possible_outdated_reference")
    assert client.post(f"/api/v1/policy-findings/{other['id']}/dismiss", json={"justification": "x"}, headers=isso).status_code == 422
    assert client.post(f"/api/v1/policy-findings/{other['id']}/dismiss", json={"justification": "Rev 4 citation updated in draft v3"}, headers=isso).status_code == 200
    with SessionLocal() as db:
        o = db.get(PolicyFinding, uuid.UUID(other["id"]))
        assert o.status == "dismissed" and o.justification and o.reviewer_id and o.decided_at and o.quote


def test_ai_use_case_disable_is_honored(client, token):
    admin = auth(token("platform.admin@aegisrmf.demo"))
    with SessionLocal() as db:
        sid = str(_ltp(db).id)
    assert client.put("/api/v1/admin/ai-settings", json={"use_cases": {"control.implementation_statement": False}}, headers=admin).status_code == 200
    r = client.post(f"/api/v1/systems/{sid}/workbench/controls/cm-6/ai-draft", headers=auth(token("isso@aegisrmf.demo")))
    assert r.status_code == 403 and "disabled" in r.json()["detail"]
    s = client.get("/api/v1/admin/ai-settings", headers=admin).json()
    assert s["human_approval_required"] is True and s["human_approval_locked"] is True
    client.put("/api/v1/admin/ai-settings", json={"use_cases": {"control.implementation_statement": True}}, headers=admin)


def test_search_rbac_filtering(client, token):
    lead = client.get("/api/v1/search", params={"q": "LTP"}, headers=auth(token("isso@aegisrmf.demo"))).json()
    assert any(r["type"] == "system" for r in lead)
    with SessionLocal() as db:
        u = User(org_id=_ltp(db).org_id, email="nobody@aegisrmf.demo", display_name="No Roles", is_active=True)
        db.add(u)
        db.commit()
        from app.security import sessions
        from app.security.tokens import create_access_token
        sess, _ = sessions.create(db, u.id, "dev_password", None, None)
        db.commit()
        tok = create_access_token(u.id, "dev_password", sess.id)[0]
    r = client.get("/api/v1/search", params={"q": "server"}, headers=auth(tok))
    assert r.status_code == 200 and all(x["type"] in ("control", "policy") for x in r.json())


def test_workflow_stages_and_notification_idempotency(client, token):
    from app.services.rmf import generate_deadline_notifications

    with SessionLocal() as db:
        sid = str(_ltp(db).id)
    st = client.get(f"/api/v1/systems/{sid}/rmf-workflow", headers=auth(token("isso@aegisrmf.demo"))).json()
    names = [s["stage"] for s in st]
    assert names[:7] == ["1. Prepare", "2. Categorize", "3. Select", "4. Implement", "5. Assess", "6. Authorize", "7. Monitor"]
    assert st[2]["state"] == "completed" and "291" in st[2]["reason"]
    assert any(s["stage"] == "Ongoing: Attestations" for s in st)
    with SessionLocal() as db:
        generate_deadline_notifications(db)
        db.commit()
        assert generate_deadline_notifications(db) == 0
        db.rollback()


def test_audit_log_filters_and_export(client, token):
    admin = auth(token("platform.admin@aegisrmf.demo"))
    d = client.get("/api/v1/audit-log", params={"action": "authz", "outcome": "denied"}, headers=admin).json()
    assert d["total"] >= 1 and all(e["outcome"] == "denied" for e in d["items"]) and d["chain"]["valid"] is True
    assert client.get("/api/v1/audit-log", params={"fmt": "csv"}, headers=admin).text.startswith("seq,")
    assert client.get("/api/v1/audit-log", headers=auth(token("leadership.viewer@aegisrmf.demo"))).status_code == 403


_ = Finding
