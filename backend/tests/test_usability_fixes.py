"""Regression tests for the ISSO usability fix round (numbered items from the customer walkthrough)."""
from sqlalchemy import select

from app.db import SessionLocal
from app.models import System
from tests.conftest import auth, demo_org_id


def _sid(acr="LTP") -> str:
    """The demo tenant's system – sandbox orgs clone the demo acronyms, so the lookup must be scoped to the demo org."""
    with SessionLocal() as db:
        return str(db.scalar(select(System).where(System.acronym == acr, System.org_id == demo_org_id(db))).id)


def test_01_cross_screen_numbers_agree(client, token):
    isso, ao = auth(token("isso@aegisrmf.demo")), auth(token("ao@aegisrmf.demo"))
    sid = _sid()
    wb = client.get(f"/api/v1/systems/{sid}/workbench/summary", headers=isso).json()
    m = wb["metrics"]
    assert wb["with_current_evidence"] == m["controls_with_current_evidence"] and wb["total_assigned"] == m["assigned_controls"]
    assert m["control_evidence_coverage_pct"] == round(100 * m["controls_with_current_evidence"] / m["assigned_controls"], 1)
    wf = {s["stage"]: s for s in client.get(f"/api/v1/systems/{sid}/rmf-workflow", headers=isso).json()}
    assert f"{m['controls_with_current_evidence']} of {m['assigned_controls']}" in wf["7. Monitor"]["reason"]
    assert "evidence items within their freshness window" in wf["7. Monitor"]["reason"] and "Controls with current evidence:" in wf["7. Monitor"]["reason"]
    lead = {r["acronym"]: r for r in client.get("/api/v1/dashboard/leadership", headers=ao).json()["systems"]}["LTP"]
    for k in ("controls_with_current_evidence", "assigned_controls", "evidence_items_fresh_pct", "open_cat1", "kev_open", "overdue_poams", "open_poams"):
        assert lead[k] == m[k], k
    poams = client.get("/api/v1/poams", params={"system_id": sid, "status": ""}, headers=isso).json()
    assert poams["summary"]["overdue"] == m["overdue_poams"] and poams["summary"]["open"] == m["open_poams"]
    em = client.get(f"/api/v1/systems/{sid}/emass", headers=isso).json()
    assert em["pending_emass_sync"] == poams["summary"]["pending_emass_sync"] == m["pending_emass_sync"]


def test_02_monitor_needs_attention_with_open_kev_or_cat1(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    sid = _sid()
    m = client.get(f"/api/v1/systems/{sid}/workbench/summary", headers=isso).json()["metrics"]
    mon = {s["stage"]: s for s in client.get(f"/api/v1/systems/{sid}/rmf-workflow", headers=isso).json()}["7. Monitor"]
    if m["kev_open"] or m["open_cat1"] or m["overdue_poams"]:
        assert mon["state"] == "needs_attention" and mon["blockers"]


def test_03_emass_state_derived_from_queue_history(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    sid = _sid()
    em = client.get(f"/api/v1/systems/{sid}/emass", headers=isso).json()
    states = {p["human_id"]: p for p in em["poam_states"]}
    synced = [p for p in states.values() if p["state"] == "synced"]
    assert synced and all(p["remote_id"] for p in synced)
    assert em["status"]["last_sync_at"] is not None, "synced items must have sync history and a last-sync timestamp"
    assert states["P-0022"]["state"] == "out_of_sync"
    pending = sum(1 for p in states.values() if p["state"] in ("not_sent", "out_of_sync", "queued", "retrying", "conflict", "failed"))
    assert em["pending_emass_sync"] == pending > 0
    rows = client.get("/api/v1/poams", params={"system_id": sid, "status": "", "page_size": 100}, headers=isso).json()["items"]
    assert all(r["emass"]["state"] == states[r["human_id"]]["state"] for r in rows)


def test_04_source_cards_count_same_records_as_ingest_table(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    sid = _sid()
    runs = client.get(f"/api/v1/systems/{sid}/ingest-runs", headers=isso).json()
    runs = runs if isinstance(runs, list) else runs["items"]
    for s in client.get(f"/api/v1/systems/{sid}/sources", headers=isso).json():
        mine = [r for r in runs if r["source_id"] == s["id"] and r["status"] == "completed"]
        if mine:
            latest = max(mine, key=lambda r: r["received_at"])
            assert s["results_latest_run"] == latest["total"], s["name"]


def test_05_queue_lanes_and_mine_toggle(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    sid = _sid()
    q = client.get(f"/api/v1/systems/{sid}/workbench/queue", headers=isso).json()
    na = q["lanes"]["needs_action"]
    assert q["counts"]["needs_action"] == len(na) > 0
    kinds = {i["kind"] for i in na}
    assert "poam" in kinds and "control" in kinds
    overdue_cat1 = [i for i in na if i["kind"] == "poam" and i["severity"] == "CAT I" and any(r["code"] == "overdue" for r in i["reasons"])]
    assert overdue_cat1 and all(i["control_link"] for i in overdue_cat1)
    assert [i["score"] for i in na] == sorted((i["score"] for i in na), reverse=True)
    assert not any(r["code"] in ("missing_implementation_statement",) for i in na if i["kind"] == "control" for r in i["reasons"]
                   if len(i["reasons"]) == 1)
    assert all(f["count"] == len(f["controls"]) for f in q["lanes"]["backlog"])
    mine = client.get(f"/api/v1/systems/{sid}/workbench/queue", params={"mine": True}, headers=isso).json()
    assert mine["counts"]["needs_action"] <= q["counts"]["needs_action"]


def test_06_poam_default_sort_is_risk(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    r = client.get("/api/v1/poams", params={"system_id": _sid(), "page_size": 100}, headers=isso).json()
    assert r["sort"] == "risk"
    scores = [i["risk_score"] for i in r["items"]]
    assert scores == sorted(scores, reverse=True)


def test_07_control_detail_policy_parameters_and_odp(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    d = client.get(f"/api/v1/systems/{_sid()}/workbench/controls/ac-2.3", headers=isso).json()
    p = next(x for x in d["policy_parameters"] if x["parameter"] == "inactivity_disable_days")
    assert p["odp_value"].startswith("35") and p["observed_value"].startswith("90") and p["result"] == "Mismatch"
    assert any(s.get("value", "") and s["value"].startswith("35") for s in d["statement_segments"])
    assert d["assignment"]["monitoring_status"] == "failing"


def test_08_policy_quotes_are_verbatim(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    pols = client.get("/api/v1/policies", headers=isso).json()
    pol = next(p for p in (pols["policies"]) if p["policy_key"] == "access-control-policy" and p["status"] != "superseded")
    d = client.get(f"/api/v1/policies/{pol['id']}", headers=isso).json()
    from app.models import Policy
    with SessionLocal() as db:
        text = db.get(Policy, __import__("uuid").UUID(pol["id"])).text_content
    vals = [v for v in d["values"] if v.get("quote")]
    assert vals and all(v["quote"] in text and v["quote_status"] == "verbatim" for v in vals)
    from app.services.rmf import verbatim_quote
    assert verbatim_quote(text, "totally unrelated paraphrase about cats")["quote_status"] == "paraphrase"


def test_09_policy_review_status_derived(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    pols = client.get("/api/v1/policies", headers=isso).json()
    items = pols["policies"]
    from datetime import date
    for p in items:
        due = date.fromisoformat(p["review_due"]) if p.get("review_due") else None
        if p["status"] == "current" and due and due < date.today():
            assert p["review_status"] == "review_overdue", p["title"]
        if p["review_status"] == "review_overdue":
            assert due and due < date.today()


def test_10_11_passing_results_excluded_and_grouped(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    m = client.get("/api/v1/mapping-review", params={"system_id": _sid()}, headers=isso).json()
    keys = [g["rule_key"] for g in m["unmapped"]]
    assert len(keys) == len(set(keys))
    assert all(g["host_count"] >= 1 and len(g["hosts"]) == len(g["finding_ids"]) for g in m["unmapped"])
    from app.models import Finding
    with SessionLocal() as db:
        passing = list(db.scalars(select(Finding).where(Finding.current_state.in_(("pass", "not_applicable"))).limit(20)))
        assert passing and all((f.priority_score or 0) == 0 for f in passing)
        ids = {str(f.id) for f in passing}
    assert not ids & {i for g in m["unmapped"] for i in g["finding_ids"]}


def test_12_manual_map_rule_action(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    sid = _sid()
    m = client.get("/api/v1/mapping-review", params={"system_id": sid}, headers=isso).json()
    if not m["unmapped"]:
        return
    g = m["unmapped"][0]
    bad = client.post("/api/v1/mapping-review/rule-action", json={"system_id": sid, "finding_ids": g["finding_ids"], "action": "map",
                                                                  "control_ids": [], "justification": "manual mapping test"}, headers=isso)
    assert bad.status_code == 422
    r = client.post("/api/v1/mapping-review/rule-action", json={"system_id": sid, "finding_ids": g["finding_ids"], "action": "map",
                                                                "control_ids": ["CM-6", "si-2"], "justification": "Rule checks configuration settings"}, headers=isso)
    assert r.status_code == 200 and r.json()["updated"] == len(g["finding_ids"])
    after = client.get("/api/v1/mapping-review", params={"system_id": sid}, headers=isso).json()
    assert g["rule_key"] not in {x["rule_key"] for x in after["unmapped"]}


def test_13_ai_provider_by_environment(monkeypatch):
    import types

    from app.services.ai import service
    real = service.get_settings()
    monkeypatch.setattr(service, "get_settings", lambda: types.SimpleNamespace(**{**{k: getattr(real, k) for k in dir(real) if not k.startswith("_")},
                                                                                 "environment": "development"}))
    assert service.build_provider("emergent") is not None
    monkeypatch.setattr(service, "get_settings", lambda: types.SimpleNamespace(environment="production"))
    try:
        service.build_provider("emergent")
        raise AssertionError("emergent must be refused in production")
    except ValueError:
        pass
    monkeypatch.undo()
    svc = service.AIService(None, "refused")
    assert svc.describe()["reason"] == "refused" and svc.describe()["configured"] is False


def test_14_template_draft_without_ai(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    r = client.post(f"/api/v1/systems/{_sid()}/workbench/controls/ra-5/ai-draft", params={"mode": "template"}, headers=isso).json()
    assert r["template"] is True and r["label"] == "TEMPLATE DRAFT (no AI)" and r["prompt_version"].startswith("impl-template")
    d = r["draft"]
    assert {"narrative", "verified_facts", "missing_information", "suggested_actions", "citations"} <= set(d)
    assert all(f"[EV:{c}]" in d["narrative"] for c in d["citations"])


def test_17_responsibility_matrix_and_crm_import(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    sid = _sid()
    inh = client.get(f"/api/v1/systems/{sid}/inheritance", headers=isso).json()
    shared = [x for x in inh["shared"] if x["responsibility"] == "shared"]
    assert shared and all(x["provider_responsibility"] and x["system_responsibility"] for x in shared)
    prov = inh["providers"][0]["id"]
    bad = client.post(f"/api/v1/providers/{prov}/responsibility-matrix", files={"file": ("crm.csv", b"a,b\n1,2\n")}, headers=isso)
    assert bad.status_code == 422
    csv_ = b"control_id,responsibility,provider_responsibility,customer_responsibility\nPE-3,inherited,Provider guards facilities,None\n"
    ok = client.post(f"/api/v1/providers/{prov}/responsibility-matrix", files={"file": ("crm.csv", csv_)}, headers=isso)
    assert ok.status_code == 200 and not ok.json()["errors"]


def test_19_linked_findings_show_poam(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    d = client.get(f"/api/v1/systems/{_sid()}/workbench/controls/ra-5", headers=isso).json()
    assert any(f.get("poam") for f in d["open_findings"])


def test_22_attestation_evidence_and_content_dates():
    from datetime import date

    from app.models import ContentVersion, Evidence, EvidenceSource
    from app.services.content_updates import content_date
    with SessionLocal() as db:
        for ev, src in db.execute(select(Evidence, EvidenceSource).join(EvidenceSource, EvidenceSource.id == Evidence.source_id)
                                  .where(Evidence.evidence_type == "attestation")):
            assert src.name == "Manual attestations"
            if "_attestation" in (ev.file_name or ""):
                assert "attestation record" in ev.name
        from app.models import FreshnessPolicy
        assert db.scalar(select(FreshnessPolicy.window_days).where(FreshnessPolicy.evidence_type == "attestation")) == 365
        assert all(cv.effective_date is None or cv.effective_date <= date.today() for cv in db.scalars(select(ContentVersion)))
    try:
        content_date(date(2999, 1, 1), False)
        raise AssertionError("future date accepted")
    except ValueError:
        pass


def test_23_decision_rules_non_overlapping(client, token):
    from app.models import DecisionRule
    from app.services import workflow as wf
    assert wf.REQUEST_TYPES["deadline_extension"] != wf.REQUEST_TYPES["waiver_extension"]
    with SessionLocal() as db:
        rules = list(db.scalars(select(DecisionRule)))
        assert wf.validate_rules(rules) == []
        dup = DecisionRule(org_id=rules[0].org_id, request_type=rules[0].request_type, version=99, steps=[], label="x", is_active=True)
        assert wf.validate_rules([r for r in rules if r.is_active] + [dup])


def test_24_audit_log_hides_system_events_by_default(client, token):
    admin = auth(token("platform.admin@aegisrmf.demo"))
    human = client.get("/api/v1/audit-log", params={"page_size": 200}, headers=admin).json()
    assert all(e["actor_user_id"] for e in human["items"])
    allv = client.get("/api/v1/audit-log", params={"include_system": True}, headers=admin).json()
    assert allv["total"] >= human["total"]


def test_26_xccdf_and_sarif_ingest(client, token):
    import pathlib
    import uuid as _u

    from app.models import Finding, IngestRun
    from app.services.ingest.pipeline import process_run
    isso = auth(token("isso@aegisrmf.demo"))
    sid = _sid()
    root = pathlib.Path(__file__).resolve().parents[2] / "samples"
    for rel, fmt in (("scap/demo_linux_xccdf_results_SYNTHETIC.xml", "xccdf"), ("sarif/demo_pipeline_sast_SYNTHETIC.sarif", "sarif")):
        p = root / rel
        r = client.post(f"/api/v1/systems/{sid}/uploads", files={"file": (p.name, p.read_bytes())}, headers=isso)
        assert r.status_code in (200, 201, 202), r.text
        with SessionLocal() as db:
            run = db.scalar(select(IngestRun).where(IngestRun.system_id == _u.UUID(sid), IngestRun.file_name == p.name).order_by(IngestRun.received_at.desc()))
            assert run.file_format == fmt
            if run.status != "completed":
                process_run(db, run.id)
                db.commit()
            db.refresh(run)
            assert run.status == "completed", run.errors
    with SessionLocal() as db:
        x = db.scalar(select(Finding).join(System, System.id == Finding.system_id).where(System.org_id == demo_org_id(db), Finding.vuln_id == "V-910002"))
        assert x.current_state == "open" and x.mapping_status == "mapped" and x.cat == "CAT I"
        assert db.scalar(select(Finding).join(System, System.id == Finding.system_id).where(System.org_id == demo_org_id(db), Finding.vuln_id == "V-910001")).current_state == "pass"
        assert db.scalar(select(Finding).where(Finding.rule_id == "DEMO-SQLI-001")).mapping_status == "mapped"
        assert db.scalar(select(Finding).where(Finding.rule_id == "DEMO-STYLE-003")).mapping_status == "unmapped"


def test_r2_client_ip_trusted_proxies(monkeypatch):
    from starlette.requests import Request

    from app.security.web import client_ip

    def req(peer, xff=None):
        h = [(b"x-forwarded-for", xff.encode())] if xff else []
        return Request({"type": "http", "headers": h, "client": (peer, 1234)})
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
    monkeypatch.setenv("TRUSTED_PROXIES", "10.0.0.0/8")
    assert client_ip(req("10.1.2.3", "203.0.113.9, 10.0.0.5")) == "203.0.113.9"
    assert client_ip(req("198.51.100.7", "203.0.113.9")) == "198.51.100.7"  # untrusted peer: XFF ignored (no spoofing)
    assert client_ip(req("10.1.2.3", "1.1.1.1, 203.0.113.9")) == "203.0.113.9"  # right-most untrusted hop
    monkeypatch.setenv("TRUSTED_PROXIES", "")
    assert client_ip(req("10.1.2.3", "203.0.113.9")) == "10.1.2.3"


def test_r2_signup_rate_limit_per_client_ip(client, monkeypatch):
    import uuid as _u

    from app.config import get_settings
    monkeypatch.setenv("ALLOW_SIGNUP", "true")
    monkeypatch.setenv("SIGNUP_RATE_LIMIT", "2/3600")
    monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.0/8,testclient")
    monkeypatch.setenv("SIGNUP_MIN_SECONDS", "0")
    get_settings.cache_clear()
    try:
        def go(ip):
            t = client.get("/api/v1/auth/signup/start").json()["form_token"]
            return client.post("/api/v1/auth/signup", headers={"X-Forwarded-For": ip},
                               json={"name": "Rate Test", "email": f"rl-{_u.uuid4().hex[:8]}@example.com", "password": "Sandbox!Pass-2026x",
                                     "form_token": t}).status_code
        assert go("203.0.113.50") == 201 and go("203.0.113.50") == 201
        assert go("203.0.113.50") == 429
        assert go("203.0.113.51") == 201  # different real client is not blocked by the shared proxy
    finally:
        monkeypatch.delenv("ALLOW_SIGNUP")
        get_settings.cache_clear()


def test_r2_out_of_scope_requires_decision_rule_approval(client, token):
    isso, issm = auth(token("isso@aegisrmf.demo")), auth(token("issm@aegisrmf.demo"))
    sid = _sid("MPP")
    m = client.get("/api/v1/mapping-review", params={"system_id": sid}, headers=isso).json()
    if not m["unmapped"]:
        sid = _sid()
        m = client.get("/api/v1/mapping-review", params={"system_id": sid}, headers=isso).json()
    g = m["unmapped"][0]
    r = client.post("/api/v1/mapping-review/rule-action", json={"system_id": sid, "finding_ids": g["finding_ids"], "action": "out_of_scope",
                                                                "justification": "Host decommissioned, outside boundary"}, headers=isso).json()
    assert r["pending_request"] and r["updated"] == 0
    still = {x["rule_key"]: x for x in client.get("/api/v1/mapping-review", params={"system_id": sid}, headers=isso).json()["unmapped"]}
    assert still[g["rule_key"]]["pending_disposition"] == r["pending_request"]
    ok = client.post(f"/api/v1/reviews/{r['request_id']}/decisions", json={"action": "approve", "rationale": "Agreed – out of boundary"}, headers=issm)
    assert ok.status_code == 200, ok.text
    after = {x["rule_key"] for x in client.get("/api/v1/mapping-review", params={"system_id": sid}, headers=isso).json()["unmapped"]}
    assert g["rule_key"] not in after


def test_r2_emass_last_sync_equals_history_max(client, token):
    isso = auth(token("isso@aegisrmf.demo"))
    em = client.get(f"/api/v1/systems/{_sid()}/emass", headers=isso).json()
    ok = [r["created_at"] for r in em["runs"] if r["status"] == "succeeded"]
    assert em["status"]["last_sync_at"] == max(ok)


def test_r3_decision_rule_installed_for_new_request_type(client, token):
    import uuid as _u

    from app.models import Organization
    from app.services import workflow as wf
    with SessionLocal() as db:
        org = Organization(name=f"rule-test-{_u.uuid4().hex[:6]}", slug=f"rule-test-{_u.uuid4().hex[:6]}")
        db.add(org)
        db.flush()
        r = wf.rule_for(db, org.id, "finding_out_of_scope")
        assert r.steps[0]["role"] == "issm" and r.version == 1
        db.rollback()
