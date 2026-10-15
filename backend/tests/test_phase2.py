import os
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import (ApprovalRequest, AuditEvent, ControlAssignment, Evidence, Finding, FindingControlMap, Poam, PoamFinding, System)
from app.services.ingest.pipeline import process_run, receive_upload
from tests.conftest import auth, demo_org_id

E2E = os.environ.get("SAMPLES_DIR", "/app/samples") + "/e2e"


def _ingest(sid, name):
    with SessionLocal() as db:
        run = receive_upload(db, system_id=sid, source_id=None, file_name=name, data=open(f"{E2E}/{name}", "rb").read())
        if run.status == "queued":
            process_run(db, run.id)
        db.commit()
        return run.id, run.status


@pytest.fixture(scope="module")
def e2e(client, token):
    h = auth(token("isso@aegisrmf.demo"))
    r = client.post("/api/v1/systems", json={"name": "E2E Pytest System", "acronym": "E2EP", "baseline_key": "moderate",
                                             "confidentiality_impact": "Moderate", "integrity_impact": "Moderate", "availability_impact": "Low"}, headers=h)
    assert r.status_code == 201, r.text
    sid = uuid.UUID(r.json()["id"])
    _ingest(sid, "e2e-web-01.ckl")
    _ingest(sid, "e2e_scan.nessus")
    return sid


def _leader(client, token):
    return client.get("/api/v1/dashboard/leadership", headers=auth(token("leadership.viewer@aegisrmf.demo"))).json()


def test_new_upload_is_current_hash_recorded_unsigned(e2e):
    with SessionLocal() as db:
        evs = list(db.scalars(select(Evidence).where(Evidence.system_id == e2e)))
        assert evs and all(e.state == "current" and e.integrity_status == "hash_recorded" and e.signature_status == "unsigned" for e in evs)
        assert all(e.source_id for e in evs), "uploads without source must be auto-attributed"


def test_source_cards_reconcile_with_findings_and_ledger(client, token, e2e):
    h = auth(token("isso@aegisrmf.demo"))
    for sid in (str(e2e), None):
        if sid is None:
            with SessionLocal() as db:
                sid = str(db.scalar(select(System.id).where(System.acronym == "LTP", System.org_id == demo_org_id(db))))
        cards = client.get(f"/api/v1/systems/{sid}/sources", headers=h).json()
        ledger = client.get(f"/api/v1/systems/{sid}/evidence", headers=h).json()
        with SessionLocal() as db:
            total = db.scalar(select(func.count()).select_from(Finding).where(Finding.system_id == uuid.UUID(sid)))
        assert sum(c["findings_total"] for c in cards) == total
        assert all(c["mapped"] + c["unmapped"] == c["findings_total"] for c in cards)
        assert sum(c["evidence_count"] for c in cards) == len(ledger)


def test_grouped_mappings_no_repeated_controls(client, token, e2e):
    h = auth(token("isso@aegisrmf.demo"))
    runs = client.get(f"/api/v1/systems/{e2e}/ingest-runs", headers=h).json()
    d = client.get(f"/api/v1/ingest-runs/{runs[-1]['id']}", headers=h).json()
    for f in d["findings"]:
        ids = [c["control_id"] for c in f["controls"]]
        assert len(ids) == len(set(ids))


def test_partial_freshness_per_asset(client, token):
    with SessionLocal() as db:
        ltp = db.scalar(select(System).where(System.acronym == "LTP", System.org_id == demo_org_id(db)))
        ev = db.scalar(select(Evidence).where(Evidence.system_id == ltp.id, Evidence.file_name == "ltp_cache-node-06.ckl"))
        eid, sid = str(ev.id), str(ltp.id)
    r = client.post(f"/api/v1/demo/evidence/{eid}/collected-at", json={"days_ago": 60}, headers=auth(token("platform.admin@aegisrmf.demo")))
    assert r.status_code == 200
    with SessionLocal() as db:
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(sid), ControlAssignment.control_id == "cm-6"))
        assert a.evidence_freshness_status == "partially_stale"
        reason = next(x for x in a.reasons if x["code"] == "expired_evidence")
        assert reason["count"] >= 1 and reason["of"] > reason["count"] and "of" in reason["detail"]


def _e2e_finding(db, sid, **kw):
    q = select(Finding).where(Finding.system_id == sid)
    for k, v in kw.items():
        q = q.where(getattr(Finding, k) == v)
    return db.scalar(q)


def test_full_closure_flow_and_consistency(client, token, e2e):
    isso, issm = auth(token("isso@aegisrmf.demo")), auth(token("issm@aegisrmf.demo"))
    with SessionLocal() as db:
        f = _e2e_finding(db, e2e, vuln_id="V-900140")
        fid = str(f.id)
    m = client.get(f"/api/v1/findings/{fid}/poam-match", headers=isso).json()
    assert m["matches"] == [] and m["prefill"]["control_ids"]
    pre = m["prefill"]
    body = {k: pre[k] for k in ("system_id", "finding_ids", "control_ids", "weakness", "severity", "cat", "source_label")}
    body["due_date"] = str(date.today() - timedelta(days=3))
    r = client.post("/api/v1/poams", json=body, headers=isso)
    assert r.status_code == 201, r.text
    poam = r.json()
    assert poam["human_id"].startswith("P-") and poam["display_status"] == "overdue"
    again = client.post("/api/v1/poams", json=body, headers=isso)
    assert again.status_code == 409 and again.json()["detail"]["matches"][0]["human_id"] == poam["human_id"]
    assert client.get(f"/api/v1/findings/{fid}/poam-match", headers=isso).json()["matches"][0]["id"] == poam["id"]
    lead0 = _leader(client, token)
    e2e_row0 = next(s for s in lead0["systems"] if s["id"] == str(e2e))
    assert e2e_row0["overdue_poams"] == 1 and e2e_row0["open_cat1"] >= 1

    _ingest(e2e, "e2e-web-01_remediated.ckl")
    d = client.get(f"/api/v1/poams/{poam['id']}", headers=isso).json()
    assert d["poam"]["status"] == "closure_eligible"
    assert d["findings"][0]["remediation_status"] == "remediated_observed"
    with SessionLocal() as db:
        ce = db.scalar(select(AuditEvent).where(AuditEvent.action == "poam.closure_eligible", AuditEvent.entity_id == poam["id"]))
        assert ce.actor_email == "system" and ce.details["ingest_run_id"] and ce.details["observation_ids"]
    hist = d["history"]
    assert any(x["actor_name"] for x in hist)

    with SessionLocal() as db:
        ev = str(db.scalar(select(Evidence.id).where(Evidence.system_id == e2e, Evidence.file_name == "e2e-web-01_remediated.ckl")))
    assert client.post(f"/api/v1/poams/{poam['id']}/request-closure", json={"justification": "Rescan clean", "evidence_ids": []}, headers=isso).status_code == 422
    rq = client.post(f"/api/v1/poams/{poam['id']}/request-closure", json={"justification": "Rescan shows NotAFinding", "evidence_ids": [ev]}, headers=isso)
    assert rq.status_code == 201, rq.text
    req = rq.json()
    own = client.post(f"/api/v1/reviews/{req['id']}/decisions", json={"action": "approve", "rationale": "self approval attempt"}, headers=isso)
    assert own.status_code == 403
    with SessionLocal() as db:
        den = db.scalar(select(AuditEvent).where(AuditEvent.action == "authz.denied", AuditEvent.entity_id == req["id"]))
        assert den is not None and den.outcome == "denied" and den.details["reason"] == "requester_cannot_decide_own_request"
    assert client.post(f"/api/v1/reviews/{req['id']}/decisions", json={"action": "approve", "rationale": "short"}, headers=issm).status_code == 422
    ok = client.post(f"/api/v1/reviews/{req['id']}/decisions", json={"action": "approve", "rationale": "Verified rescan evidence, FIPS enabled"}, headers=issm)
    assert ok.status_code == 200 and ok.json()["status"] == "approved"
    assert client.post(f"/api/v1/reviews/{req['id']}/decisions", json={"action": "approve", "rationale": "Verified again twice"}, headers=issm).status_code == 409

    d = client.get(f"/api/v1/poams/{poam['id']}", headers=isso).json()
    assert d["poam"]["status"] == "closed" and d["poam"]["actual_completion"] == str(date.today())
    assert d["findings"][0]["remediation_status"] == "closed"
    fd = client.get(f"/api/v1/findings/{fid}", headers=isso).json()
    assert fd["poams"][0]["id"] == poam["id"] and fd["reviews"][0]["id"] == req["id"]
    assert ev in [e["id"] for e in fd["evidence"]]
    ctl = fd["controls"][0]["control_id"]
    wb = client.get(f"/api/v1/systems/{e2e}/workbench/controls/{ctl}", headers=isso).json()
    assert any(p["id"] == poam["id"] and p["status"] == "closed" for p in wb["poams"])
    lead1 = _leader(client, token)
    e2e_row1 = next(s for s in lead1["systems"] if s["id"] == str(e2e))
    assert e2e_row1["overdue_poams"] == 0 and e2e_row1["open_cat1"] < e2e_row0["open_cat1"]
    with SessionLocal() as db:
        acts = set(db.scalars(select(AuditEvent.action).where(AuditEvent.entity_id.in_([poam["id"], req["id"]]))))
        assert {"poam.created", "review.requested", "review.approve", "review.effect.poam_closure"} <= acts


def test_kev_flow_remediation_then_isso_cannot_accept_risk(client, token, e2e):
    isso, ao, issm = auth(token("isso@aegisrmf.demo")), auth(token("ao@aegisrmf.demo")), auth(token("issm@aegisrmf.demo"))
    with SessionLocal() as db:
        f = _e2e_finding(db, e2e, is_kev=True)
        assert {"ra-5", "si-2"} <= set(db.scalars(select(FindingControlMap.control_id).where(FindingControlMap.finding_id == f.id)))
        fid = str(f.id)
    pre = client.get(f"/api/v1/findings/{fid}/poam-match", headers=isso).json()["prefill"]
    poam = client.post("/api/v1/poams", json={k: pre[k] for k in ("system_id", "finding_ids", "control_ids", "weakness", "severity", "source_label")},
                       headers=isso).json()
    rq = client.post(f"/api/v1/poams/{poam['id']}/request-risk-acceptance",
                     json={"justification": "Compensating WAF rule in place", "expiration": str(date.today() + timedelta(days=90))}, headers=isso).json()
    assert client.post(f"/api/v1/reviews/{rq['id']}/decisions", json={"action": "approve", "rationale": "ISSM trying to approve"}, headers=issm).status_code == 422
    assert client.post(f"/api/v1/reviews/{rq['id']}/decisions", json={"action": "approve", "rationale": "AO before endorsement"}, headers=ao).status_code == 403
    with SessionLocal() as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action == "authz.denied", AuditEvent.entity_id == rq["id"],
                                                  AuditEvent.actor_email == "ao@aegisrmf.demo"))
    assert client.post(f"/api/v1/reviews/{rq['id']}/decisions", json={"action": "endorse", "rationale": "ISSO cannot endorse own"}, headers=isso).status_code == 403
    assert client.post(f"/api/v1/reviews/{rq['id']}/decisions", json={"action": "endorse", "rationale": "WAF verified by ISSM"}, headers=issm).status_code == 200
    assert client.post(f"/api/v1/reviews/{rq['id']}/decisions", json={"action": "approve", "rationale": "ISSO posing as AO"}, headers=isso).status_code == 403
    assert client.post(f"/api/v1/reviews/{rq['id']}/decisions", json={"action": "return", "rationale": "Need WAF rule export"}, headers=ao).status_code == 200
    d = client.get(f"/api/v1/poams/{poam['id']}", headers=isso).json()
    assert d["poam"]["status"] != "risk_accepted"
    n = client.get("/api/v1/notifications", headers=isso).json()
    assert any(x["kind"] == "returned" for x in n["items"])
    _ingest(e2e, "e2e_scan_remediated.nessus")
    d = client.get(f"/api/v1/poams/{poam['id']}", headers=isso).json()
    assert d["poam"]["status"] == "closure_eligible"


def test_false_positive_review_removes_from_open_counts(client, token, e2e):
    isso, issm = auth(token("isso@aegisrmf.demo")), auth(token("issm@aegisrmf.demo"))
    with SessionLocal() as db:
        f = db.scalar(select(Finding).where(Finding.system_id == e2e, Finding.current_state == "open", Finding.source_type == "acas"))
        if f is None:
            pytest.skip("no open ACAS finding left")
        fid = str(f.id)
    before = next(s for s in _leader(client, token)["systems"] if s["id"] == str(e2e))["open_findings"]
    rq = client.post(f"/api/v1/findings/{fid}/request-false-positive", json={"justification": "Scanner misidentified banner"}, headers=isso).json()
    assert client.post(f"/api/v1/reviews/{rq['id']}/decisions", json={"action": "approve", "rationale": "Confirmed false positive"}, headers=issm).status_code == 200
    after = next(s for s in _leader(client, token)["systems"] if s["id"] == str(e2e))["open_findings"]
    assert after == before - 1
    with SessionLocal() as db:
        assert db.get(Finding, uuid.UUID(fid)).disposition == "false_positive"


def test_ai_draft_strips_unknown_citations(client, token, e2e, monkeypatch):
    from app.services.ai import service as svc
    from app.services.ai.prompts import ImplementationStatementOutput

    with SessionLocal() as db:
        real = str(db.scalar(select(Evidence.id).join(ControlAssignment, ControlAssignment.system_id == Evidence.system_id)
                            .where(Evidence.system_id == e2e, Evidence.file_name == "e2e-web-01.ckl")))
    fake = str(uuid.uuid4())

    class FakeSvc:
        configured = True

        async def run(self, *a, **k):
            from app.models import AIInteraction
            iid = uuid.uuid4()
            with SessionLocal() as db:
                db.add(AIInteraction(id=iid, provider="fake", prompt_id="control.implementation_statement", prompt_version="1.0.0",
                                     input_sha256="0" * 64, validation_status="valid", status="succeeded"))
                db.commit()
            out = ImplementationStatementOutput(narrative=f"The system enforces SSH config [EV:{real}] and more [EV:{fake}].",
                                                citations=[real, fake], verified_facts=["x"], interpretation=["y"],
                                                suggested_actions=["z"], missing_information=["w"])
            return svc.AIResult(output=out, provider="fake", model="fake", latency_ms=1, interaction_id=iid)

    monkeypatch.setattr(svc, "get_ai_service", lambda: FakeSvc())
    h = auth(token("isso@aegisrmf.demo"))
    r = client.post(f"/api/v1/systems/{e2e}/workbench/controls/cm-6/ai-draft", headers=h)
    assert r.status_code == 200, r.text
    d = r.json()
    assert fake in d["stripped_citations"] and d["draft"]["citations"] == [real]
    assert fake not in d["draft"]["narrative"] and d["label"] == "AI DRAFT – not reviewed"
    save = client.put(f"/api/v1/systems/{e2e}/workbench/controls/cm-6/implementation",
                      json={"narrative": d["draft"]["narrative"], "implementation_status": "partially_implemented", "ai_generated": True,
                            "prompt_version": "control.implementation_statement@1.0.0", "citations": [real, fake]}, headers=h)
    assert save.status_code == 422, "AI version without interaction_id must be rejected"
    save = client.put(f"/api/v1/systems/{e2e}/workbench/controls/cm-6/implementation",
                      json={"narrative": d["draft"]["narrative"], "implementation_status": "partially_implemented", "ai_generated": True,
                            "interaction_id": d["interaction_id"], "prompt_version": "control.implementation_statement@1.0.0",
                            "citations": [real, fake]}, headers=h)
    assert save.status_code == 200 and save.json()["ai_interaction_id"] == d["interaction_id"]
    assert save.status_code == 200 and save.json()["citations"] == [real] and save.json()["review_status"] == "draft"
    rv = client.post(f"/api/v1/systems/{e2e}/workbench/implementations/{save.json()['id']}/request-review", json={"justification": "Please review AI draft"}, headers=h)
    assert rv.status_code == 201
    with SessionLocal() as db:
        assert db.get(ApprovalRequest, uuid.UUID(rv.json()["id"])).assigned_role == "issm"
    ok = client.post(f"/api/v1/reviews/{rv.json()['id']}/decisions", json={"action": "approve", "rationale": "Statement matches evidence"},
                     headers=auth(token("issm@aegisrmf.demo")))
    assert ok.status_code == 200, ok.text
    wb = client.get(f"/api/v1/systems/{e2e}/workbench/controls/cm-6", headers=h).json()
    assert wb["approved_implementation"]["id"] == save.json()["id"]
    v = next(i for i in wb["implementations"] if i["id"] == save.json()["id"])
    assert v["author_name"] and "isso" in v["author_roles"]
    rd = client.get(f"/api/v1/reviews/{rv.json()['id']}", headers=h).json()
    assert rd["decisions"][0]["decider_name"] and "issm" in rd["decisions"][0]["decider_roles"]


def test_seeded_poams_exist():
    with SessionLocal() as db:
        ids = set(db.scalars(select(Poam.human_id)))
        assert {"P-0015", "P-0019", "P-0022", "P-0026", "P-0027", "P-0030", "P-0031"} <= ids
        p27 = db.scalar(select(Poam).where(Poam.human_id == "P-0027", Poam.org_id == demo_org_id(db)))
        assert db.scalar(select(func.count()).select_from(PoamFinding).where(PoamFinding.poam_id == p27.id)) == 2


def test_cat_derivation_persisted_and_counts_agree(client, token):
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Finding).where(Finding.severity == "critical", Finding.cat.is_(None))) == 0
        assert db.scalar(select(func.count()).select_from(Finding).where(Finding.source_type == "acas", Finding.severity == "high",
                                                                         Finding.cat != "CAT I")) == 0
        ltp = db.scalar(select(System).where(System.acronym == "LTP", System.org_id == demo_org_id(db)))
        n = db.scalar(select(func.count()).select_from(Finding).where(Finding.system_id == ltp.id, Finding.cat == "CAT I",
                                                                      Finding.disposition.is_distinct_from("false_positive"),
                                                                      (Finding.current_state == "open") | (Finding.remediation_status == "remediated_observed")))
        sid = str(ltp.id)
        assert db.scalar(select(Poam.cat).where(Poam.human_id == "P-0015")) == "CAT I"
    row = next(s for s in _leader(client, token)["systems"] if s["id"] == sid)
    assert row["open_cat1"] == n


def test_audit_log_has_actor_names(client, token):
    ev = client.get("/api/v1/audit-events", params={"limit": 50}, headers=auth(token("platform.admin@aegisrmf.demo"))).json()
    assert any(e["actor_name"] and e["actor_roles"] for e in ev)


def test_poam_status_filter_uses_display_status(client, token):
    from app.db import SessionLocal
    from app.models import Poam
    from datetime import date, timedelta
    h = auth(token("isso@aegisrmf.demo"))
    with SessionLocal() as db:
        p = db.query(Poam).filter(Poam.status == "new").first()
        p.due_date = date.today() - timedelta(days=3)
        db.commit()
        hid = p.human_id
    def get(st): return client.get(f"/api/v1/poams?status={st}&page_size=100", headers=h).json()
    def ids(st): return {r["human_id"]: r["display_status"] for r in get(st)["items"]}
    assert hid not in ids("new") and all(v == "new" for v in ids("new").values())
    assert all(v == "in_progress" for v in ids("in_progress").values())
    over = get("overdue")
    assert over["items"] and {r["human_id"]: r["display_status"] for r in over["items"]}.get(hid) == "overdue"
    assert over["summary"]["overdue"] == over["total"]
