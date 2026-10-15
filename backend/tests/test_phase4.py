import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select, update

from app.db import SessionLocal
from app.models import (ContentVersion, EmassChange, EmassRemoteRecord, Finding, FindingObservation, Job, Poam, ScheduledJob, System)
from tests.conftest import auth, demo_org_id


def _ltp(db):
    return db.scalar(select(System).where(System.acronym == "LTP", System.org_id == demo_org_id(db)))


def _ver(db, v):
    return db.scalar(select(ContentVersion).where(ContentVersion.content_type == "stig_benchmark", ContentVersion.version == v))


# ---------- Part A ----------
def test_part_a_fixes(client, token):
    isso, issm = auth(token("isso@aegisrmf.demo")), auth(token("issm@aegisrmf.demo"))
    with SessionLocal() as db:
        ltp = _ltp(db)
        sid = str(ltp.id)
        pf = db.scalar(select(Finding).join(System, System.id == Finding.system_id).where(Finding.source_type == "policy_audit", System.org_id == demo_org_id(db)).limit(1))
    if pf is not None:
        assert client.get(f"/api/v1/findings/{pf.id}/poam-match", headers=isso).json()["prefill"]["source_label"] == "Policy audit"
    res = client.get("/api/v1/search", params={"q": "ac-2", "system_id": sid}, headers=isso).json()
    ctl = [r for r in res if r["type"] == "control"]
    assert ctl and all(r["system_id"] == sid for r in ctl if r.get("system_id"))
    grouped = [r for r in client.get("/api/v1/search", params={"q": "ac-2"}, headers=isso).json() if r["type"] == "control"]
    assert all("·" in r["label"] for r in grouped if r.get("system_id"))
    wf = {s["stage"]: s for s in client.get(f"/api/v1/systems/{sid}/rmf-workflow", headers=isso).json()}
    queue = client.get(f"/api/v1/systems/{sid}/controls/ac-2", headers=isso).json()
    has_missing = any(r["code"] == "missing_implementation_statement" for r in (queue.get("assignment", queue).get("queue_reasons") or []))
    assert not (wf["4. Implement"]["state"] == "completed" and has_missing)
    c = client.get(f"/api/v1/systems/{sid}/inheritance", headers=isso).json()["cards"]
    assert (c["fully_inherited"], c["shared"], c["system_owned"], c["manual_attestation"]) == (61, 44, 186, 38)
    del issm


# ---------- STIG content update ----------
def test_stig_diff_impact_and_apply_preserves_history(client, token):
    isso, issm = auth(token("isso@aegisrmf.demo")), auth(token("issm@aegisrmf.demo"))
    with SessionLocal() as db:
        v1, v2 = _ver(db, "V1R1"), _ver(db, "V1R2")
        v1_id, v2_id = str(v1.id), str(v2.id)
        obs_before = {str(o.id): (o.observed_status, str(o.content_version_id)) for o in db.scalars(
            select(FindingObservation).join(Finding, Finding.id == FindingObservation.finding_id).where(Finding.benchmark == v1.meta["benchmark"]))}
        f118 = db.scalar(select(Finding).join(System, System.id == Finding.system_id).where(System.org_id == demo_org_id(db), Finding.vuln_id == "V-900118", Finding.current_state == "open"))
    assert obs_before and all(v[1] == v1_id for v in obs_before.values())
    ov = client.get("/api/v1/content-updates", headers=isso).json()
    stig = next(t for t in ov["types"] if t["content_type"] == "stig_benchmark")
    assert stig["installed"][0]["version"] == "V1R1" and stig["available"][0]["version"] == "V1R2"
    p = client.post(f"/api/v1/content-versions/{v2_id}/preview", headers=isso)
    assert p.status_code == 201
    up = p.json()
    assert up["diff_summary"] == {"added": 6, "removed": 3, "changed_requirement": 11, "changed_severity": 2}
    p27 = next(x for x in up["impact"]["poams"] if x["human_id"] == "P-0027")
    assert "severity CAT II → CAT I" in p27["impacts"] and p27["new_cat"] == "CAT I"
    assert up["impact"]["counts"]["assets"] >= 14 and up["impact"]["counts"]["controls"] > 0
    assert client.post(f"/api/v1/content-updates/{up['id']}/apply", json={"justification": "ISSO cannot apply content"}, headers=isso).status_code == 403
    r = client.post(f"/api/v1/content-updates/{up['id']}/apply", json={"justification": "Approved October STIG release after impact review"}, headers=issm)
    assert r.status_code == 200 and r.json()["result"]["observations_rewritten"] == 0
    with SessionLocal() as db:
        after = {str(o.id): (o.observed_status, str(o.content_version_id)) for o in db.scalars(select(FindingObservation).where(
            FindingObservation.id.in_([uuid.UUID(k) for k in obs_before])))}
        assert after == obs_before  # historical observations keep the content version used at the time
        f = db.get(Finding, f118.id)
        assert f.cat == "CAT I" and str(f.content_version_id) == v2_id
        p = db.scalar(select(Poam).where(Poam.human_id == "P-0027", Poam.org_id == demo_org_id(db)))
        assert p.content_impact["status"] == "pending_review" and p.cat == "CAT II"  # POA&M needs human impact review
        assert _ver(db, "V1R1").status == "superseded" and _ver(db, "V1R2").is_active
    hist = client.get("/api/v1/content-updates", headers=isso).json()["history"]
    assert hist[0]["status"] == "applied" and hist[0]["to_version"] == "V1R2"
    m = client.get(f"/api/v1/findings/{f118.id}/mappings", params={"as_of": v1_id}, headers=isso).json()
    assert m["mappings"] and m["current_content_version"] == "V1R2"
    ack = client.post(f"/api/v1/poams/{p.id}/content-impact/ack", json={"rationale": "Accept CAT I per V1R2", "apply_new_cat": True}, headers=isso)
    assert ack.status_code == 200 and ack.json()["cat"] == "CAT I"


def test_kev_enrichment_from_pinned_file(client, token):
    from app.services.kev import is_kev, kev_catalog, reevaluate
    with SessionLocal() as db:
        cat = kev_catalog(db)
        assert cat["count"] > 1000 and len(cat["sha256"]) == 64 and cat["content_version_id"]
        assert is_kev(["CVE-2021-44228"], db) and not is_kev(["CVE-1999-99999"], db)
        for f in db.scalars(select(Finding).where(Finding.cves.is_not(None))):
            assert f.is_kev == any(c in cat["cves"] for c in f.cves)
        assert reevaluate(db)["changed"] == 0
        db.rollback()


# ---------- OSCAL ----------
def test_oscal_exports_schema_valid(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    with SessionLocal() as db:
        sid = str(_ltp(db).id)
    for model in ("poam", "ssp", "assessment-results", "assessment-plan"):
        r = client.post(f"/api/v1/systems/{sid}/oscal/{model}", headers=isso)
        assert r.status_code == 201, r.text
        v = r.json()["validation"]
        assert v["valid"] is True and v["error_count"] == 0 and v["oscal_version"] == "1.2.2", v["errors"][:3]
        assert r.json()["label"].startswith("Valid OSCAL") and len(r.json()["sha256"]) == 64
    poam = r = client.post(f"/api/v1/systems/{sid}/oscal/poam", headers=isso).json()
    assert poam["document"]["plan-of-action-and-milestones"]["poam-items"]
    from app.services.oscal_export import validate
    bad = poam["document"]
    del bad["plan-of-action-and-milestones"]["metadata"]
    assert validate("poam", bad)["valid"] is False
    lst = client.get(f"/api/v1/systems/{sid}/oscal", headers=isso).json()
    assert lst["unsupported"] and lst["exports"][0]["validation"]["valid"] is True
    d = client.get(f"/api/v1/oscal-exports/{lst['exports'][0]['evidence_id']}/download", headers=isso)
    assert d.status_code == 200 and d.headers["x-content-sha256"] == lst["exports"][0]["sha256"]


# ---------- eMASS ----------
def _approve(client, isso, issm, cid):
    r = client.post(f"/api/v1/emass/changes/{cid}/request-approval", json={"justification": "Sync POA&M update to eMASS"}, headers=isso)
    assert r.status_code == 200, r.text
    d = client.post(f"/api/v1/reviews/{r.json()['request_id']}/decisions", json={"action": "approve", "rationale": "Reviewed diff"}, headers=issm)
    assert d.status_code == 200, d.text


def test_emass_failure_retry_conflict_and_export_only(client, token):
    isso, issm, admin = (auth(token(e)) for e in ("isso@aegisrmf.demo", "issm@aegisrmf.demo", "platform.admin@aegisrmf.demo"))
    with SessionLocal() as db:
        ltp = _ltp(db)
        sid = str(ltp.id)
        p19 = db.scalar(select(Poam).where(Poam.human_id == "P-0019", Poam.org_id == demo_org_id(db)))
        p26 = db.scalar(select(Poam).where(Poam.human_id == "P-0026", Poam.org_id == demo_org_id(db)))
        before19 = (p19.weakness, p19.status, p19.due_date)
    assert client.get("/api/v1/emass/status", headers=isso).json()["mode"] == "mock"
    cmp_ = client.post(f"/api/v1/systems/{sid}/emass/compare", headers=isso).json()
    assert cmp_["summary"]["different"] >= 1 and cmp_["summary"]["remote_only"] >= 1
    ch = client.post(f"/api/v1/systems/{sid}/emass/changes", json={"entity_type": "poam", "entity_id": str(p19.id)}, headers=isso).json()
    assert client.post(f"/api/v1/emass/changes/{ch['id']}/submit", headers=isso).status_code == 409  # not approved yet
    _approve(client, isso, issm, ch["id"])
    assert client.put("/api/v1/emass/failure-sim", json={"mode": "500", "remaining": 1}, headers=isso).status_code == 403
    assert client.put("/api/v1/emass/failure-sim", json={"mode": "500", "remaining": 1}, headers=admin).status_code == 200
    r = client.post(f"/api/v1/emass/changes/{ch['id']}/submit", headers=isso).json()
    assert r["status"] == "pending_retry" and r["attempts"] == 1 and r["final_status"] is None
    with SessionLocal() as db:
        p = db.get(Poam, p19.id)
        assert (p.weakness, p.status, p.due_date) == before19 and p.emass_status != "synced"  # local change preserved, never claimed synced
    pm = client.get("/api/v1/poams", params={"system_id": sid, "q": "P-0019"}, headers=isso).json()
    assert pm["items"][0]["emass_queue_status"] == "pending_retry" and pm["summary"]["pending_emass_sync"] >= 1
    client.put("/api/v1/emass/failure-sim", json={"mode": "off", "remaining": 0}, headers=admin)
    with SessionLocal() as db:
        db.execute(update(EmassChange).where(EmassChange.id == uuid.UUID(ch["id"])).values(next_retry_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        db.commit()
        from app.services.emass import retry_due
        assert retry_due(db)["succeeded"] == 1
        db.commit()
        c = db.get(EmassChange, uuid.UUID(ch["id"]))
        assert c.status == "succeeded" and c.attempts == 2 and len([h for h in c.history if h["event"] == "submit_failed"]) == 1
        assert db.get(Poam, p19.id).emass_status == "synced"
    # conflict: remote changed after our base version
    c2 = client.post(f"/api/v1/systems/{sid}/emass/changes", json={"entity_type": "poam", "entity_id": str(p26.id)}, headers=isso).json()
    _approve(client, isso, issm, c2["id"])
    with SessionLocal() as db:
        db.execute(update(EmassRemoteRecord).where(EmassRemoteRecord.remote_id == p26.emass_remote_id).values(remote_version=EmassRemoteRecord.remote_version + 1))
        db.commit()
    r = client.post(f"/api/v1/emass/changes/{c2['id']}/submit", headers=isso).json()
    assert r["status"] == "conflict"
    assert client.post(f"/api/v1/emass/changes/{c2['id']}/resolve", json={"choice": "keep_local", "rationale": "Local is authoritative"}, headers=isso).json()["status"] == "proposed"
    assert client.post(f"/api/v1/emass/changes/{c2['id']}/submit", headers=isso).status_code == 409  # keep_local needs a fresh approval
    _approve(client, isso, issm, c2["id"])
    assert client.post(f"/api/v1/emass/changes/{c2['id']}/submit", headers=isso).json()["status"] == "succeeded"
    # export-only mode never claims a sync
    client.put("/api/v1/emass/config", json={"mode": "oscal_export_only"}, headers=admin)
    st = client.get("/api/v1/emass/status", headers=isso).json()
    assert "No live synchronization occurred" in st["notice"] and st["capabilities"]["live_sync"] is False
    c3 = client.post(f"/api/v1/systems/{sid}/emass/changes", json={"entity_type": "control", "entity_id": "ac-2"}, headers=isso).json()
    _approve(client, isso, issm, c3["id"])
    s = client.post(f"/api/v1/emass/changes/{c3['id']}/submit", headers=isso)
    assert s.status_code == 409 and "No live synchronization occurred" in s.json()["detail"]
    # read mode without configuration is truthful
    st = client.put("/api/v1/emass/config", json={"mode": "read"}, headers=admin).json()
    assert st["real_connector_configured"] is False and not any(st["checks"].values())
    client.put("/api/v1/emass/config", json={"mode": "mock"}, headers=admin)


# ---------- scheduler / risk ----------
def test_scheduler_idempotent_tick(client, token):
    from app.services import scheduler
    admin = auth(token("platform.admin@aegisrmf.demo"))
    jobs = client.get("/api/v1/scheduled-jobs", headers=admin).json()
    assert {"evidence.evaluate_freshness", "connectors.collect", "emass.retry", "kev.reevaluate", "risk.snapshot"} <= {j["job_type"] for j in jobs}
    with SessionLocal() as db:
        db.execute(update(ScheduledJob).values(next_run_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
        db.commit()
        first = scheduler.tick(db)
        db.execute(update(ScheduledJob).values(next_run_at=datetime.now(timezone.utc) - timedelta(minutes=1)))
        db.commit()
        second = scheduler.tick(db)
        assert "kev.reevaluate" in first and "kev.reevaluate" not in second  # still pending -> not enqueued twice
        assert db.scalar(select(func.count()).select_from(Job).where(Job.job_type == "kev.reevaluate", Job.status.in_(("queued", "running")))) == 1
        sj = db.scalar(select(ScheduledJob).where(ScheduledJob.job_type == "kev.reevaluate"))
        assert sj.last_status == "skipped_already_pending" and sj.next_run_at > datetime.now(timezone.utc)
        from worker.main import run_once
        while run_once():
            pass
        db.expire_all()
        sj = db.scalar(select(ScheduledJob).where(ScheduledJob.job_type == "kev.reevaluate"))
        assert sj.last_status == "succeeded" and sj.last_run_at and sj.last_result["changed"] == 0
    assert client.post(f"/api/v1/scheduled-jobs/{sj.id}/run", headers=auth(token("isso@aegisrmf.demo"))).status_code == 403


def test_risk_score_explanation_sums(client, token):
    isso, admin = auth(token("isso@aegisrmf.demo")), auth(token("platform.admin@aegisrmf.demo"))
    with SessionLocal() as db:
        mine = select(Finding).join(System, System.id == Finding.system_id).where(System.org_id == demo_org_id(db))
        f = db.scalar(mine.where(Finding.is_kev.is_(True)).limit(1)) or db.scalar(mine.limit(1))
    s = client.get(f"/api/v1/findings/{f.id}/score", headers=isso).json()
    assert "not a formal residual risk determination" in s["label"]
    assert round(sum(x["points"] for x in s["breakdown"]), 1) == s["score"]
    assert {x["factor"] for x in s["breakdown"]} >= {"rf_severity", "rf_kev", "rf_epss", "rf_exposure", "rf_evidence_confidence"}
    assert next(x for x in s["breakdown"] if x["factor"] == "rf_epss")["basis"] == "not loaded"
    assert client.put("/api/v1/risk/weights", json={"weights": {"rf_kev": 50}}, headers=isso).status_code == 403
    assert client.put("/api/v1/risk/weights", json={"weights": {"rf_kev": 50}}, headers=admin).status_code == 200
    s2 = client.get(f"/api/v1/findings/{f.id}/score", headers=isso).json()
    assert round(sum(x["points"] for x in s2["breakdown"]), 1) == s2["score"]
    client.put("/api/v1/risk/weights", json={"weights": {"rf_kev": 25}}, headers=admin)
