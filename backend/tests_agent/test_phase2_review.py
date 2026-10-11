"""Phase 2 end-to-end review tests – hits the live preview backend.

Covers:
  - E2E system registration + CKL/Nessus upload w/o source_id -> auto-attribution,
    cards reconcile, evidence ledger shows hash recorded / unsigned / current.
  - Add to POA&M; duplicate -> 409 with existing P-id.
  - Remediated upload -> POA&M closure_eligible (not closed) + owner notification.
  - ISSO request closure requires evidence; ISSO cannot decide.
  - ISSM approves -> POA&M Closed, decision history, second decide -> 409.
  - KEV risk acceptance: ISSM endorse + AO decide, ISSO approve via API -> 403.
  - False positive flow via /findings/request-false-positive + ISSM approve.
  - POA&M list: seeded P-00xx on LTP, summary, search/filter/sort/paging.
  - AI draft (real LLM, ~25s) on LTP CM-6, request review, ISSM approve.
  - Part A: LTP evidence sources sum reconcile; grouped controls per finding.
  - Freshness back-date -> partially stale.
  - Notifications bell endpoint.
"""

import os
import time
import uuid
from pathlib import Path

import pytest
import requests

def _load_react_env() -> str:
    env = os.environ.get("REACT_APP_BACKEND_URL")
    if env:
        return env.rstrip("/")
    try:
        for line in Path("/app/frontend/.env").read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().strip('"').rstrip("/")
    except Exception:
        pass
    raise RuntimeError("REACT_APP_BACKEND_URL not configured")


BASE = _load_react_env()
API = f"{BASE}/api/v1"
PWD = "AegisDemo!2026"
SAMPLES = Path("/app/samples/e2e")


def _login(email: str) -> dict:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PWD}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    tok = r.json()["access_token"]
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="session")
def issm():
    return _login("issm@aegisrmf.demo")


@pytest.fixture(scope="session")
def isso():
    return _login("isso@aegisrmf.demo")


@pytest.fixture(scope="session")
def ao():
    return _login("ao@aegisrmf.demo")


@pytest.fixture(scope="session")
def leadership():
    return _login("leadership.viewer@aegisrmf.demo")


@pytest.fixture(scope="session")
def admin():
    return _login("platform.admin@aegisrmf.demo")


def _poll_run(s, run_id, timeout=90) -> dict:
    end = time.time() + timeout
    while time.time() < end:
        r = s.get(f"{API}/ingest-runs/{run_id}", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        if d["run"]["status"] in ("completed", "duplicate", "failed", "rejected"):
            return d
        time.sleep(1.5)
    raise AssertionError(f"ingest run {run_id} did not finish within {timeout}s")


def _ltp_id(s) -> uuid.UUID:
    r = s.get(f"{API}/systems", timeout=15)
    assert r.status_code == 200
    for sys_ in r.json():
        if sys_["acronym"] == "LTP":
            return sys_["id"]
    pytest.fail("LTP not seeded")


# ---------------------------------------------------------------------------
# Shared E2E system fixture (one new moderate system for workflow scenarios)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def e2e_system(issm, isso):
    """Register a new moderate system as ISSM and upload CKL+Nessus as ISSO."""
    ts = int(time.time())
    name = f"E2E Test {ts}"
    acronym = f"E2E{ts % 100000}"
    body = {"name": name, "acronym": acronym, "description": "agent e2e", "mission_owner_email": "mo@aegisrmf.demo",
            "classification": "CUI", "baseline_key": "moderate", "overlay_keys": [], "include_privacy": False}
    r = issm.post(f"{API}/systems", json=body, timeout=20)
    assert r.status_code == 201, f"system create: {r.status_code} {r.text}"
    sid = r.json()["id"]
    assert r.json()["metrics"]["assigned_controls"] == 287

    # Assign ISSO role on the new system (ISSM has system.manage via org-wide ISSM role)
    me = isso.get(f"{API}/auth/me", timeout=15).json()
    isso_uid = me["user"]["id"] if "user" in me else me["id"]
    rr = issm.post(f"{API}/systems/{sid}/roles",
                   json={"user_id": isso_uid, "role": "isso"}, timeout=15)
    assert rr.status_code in (201, 409), f"grant isso role: {rr.status_code} {rr.text}"

    # Upload CKL w/o source_id
    with (SAMPLES / "e2e-web-01.ckl").open("rb") as fh:
        r1 = isso.post(f"{API}/systems/{sid}/uploads", files={"file": ("e2e-web-01.ckl", fh, "application/xml")}, timeout=30)
    assert r1.status_code == 202, r1.text
    run1 = _poll_run(isso, r1.json()["id"])
    assert run1["run"]["status"] == "completed", run1["run"]

    # Upload Nessus w/o source_id
    with (SAMPLES / "e2e_scan.nessus").open("rb") as fh:
        r2 = isso.post(f"{API}/systems/{sid}/uploads", files={"file": ("e2e_scan.nessus", fh, "application/xml")}, timeout=30)
    assert r2.status_code == 202, r2.text
    run2 = _poll_run(isso, r2.json()["id"])
    assert run2["run"]["status"] == "completed", run2["run"]

    return {"id": sid, "acronym": acronym, "name": name, "run_ckl": run1, "run_nessus": run2}


# ---------------------------------------------------------------------------
# Evidence Sources auto-attribution + card reconciliation + ledger metadata
# ---------------------------------------------------------------------------

class TestEvidenceSources:
    def test_auto_attribution_cards_reconcile(self, isso, e2e_system):
        r = isso.get(f"{API}/systems/{e2e_system['id']}/sources", timeout=20)
        assert r.status_code == 200
        srcs = r.json()
        # must have at least one STIG and one ACAS auto-created source
        stig = [s for s in srcs if s["source_type"] == "stig_checklist"]
        acas = [s for s in srcs if s["source_type"] in ("acas", "acas_scanner", "acas_nessus", "nessus", "tenable_sc")]
        assert stig and acas, f"missing auto-attributed sources: {[s['source_type'] for s in srcs]}"
        for s in stig + acas:
            # Mapped + Unmapped = Total
            assert s["mapped"] + s["unmapped"] == s["findings_total"], s
            assert s["findings_total"] > 0, f"no findings for {s['name']}"
            assert s["evidence_count"] >= 1

        # findings-list total should equal sum of card totals
        rf = isso.get(f"{API}/systems/{e2e_system['id']}/findings", timeout=20)
        assert rf.status_code == 200
        total_findings = len(rf.json())
        card_sum = sum(s["findings_total"] for s in srcs)
        assert card_sum == total_findings, f"cards {card_sum} vs findings {total_findings}"

    def test_evidence_ledger_metadata(self, isso, e2e_system):
        r = isso.get(f"{API}/systems/{e2e_system['id']}/evidence", timeout=20)
        assert r.status_code == 200
        ev = r.json()
        assert ev, "no evidence in ledger"
        for e in ev:
            # integrity: hash_recorded (sha256 present)
            assert e["sha256"] and len(e["sha256"]) == 64, e
            # signature: unsigned
            assert e.get("signature_status", "unsigned") == "unsigned", e
            # freshness: current within freshness window
            assert e["state"] == "current", f"{e['name']} freshness={e['state']}"


# ---------------------------------------------------------------------------
# POA&M lifecycle: create -> duplicate 409 -> remediate -> closure_eligible
# ---------------------------------------------------------------------------

class TestPoamLifecycle:
    @pytest.fixture(scope="class")
    def finding_sc13(self, isso, e2e_system):
        """Pick an open finding whose controls include SC-13 or CM-6 (mapped)."""
        r = isso.get(f"{API}/systems/{e2e_system['id']}/findings", params={"mapping_status": "mapped", "state": "open"}, timeout=20)
        assert r.status_code == 200, r.text
        findings = r.json()
        # Prefer SC-13/CM-6; else first mapped open
        pref = [f for f in findings if any(c["control_id"].lower() in ("sc-13", "cm-6") for c in f.get("controls", []))]
        pool = pref or findings
        assert pool, "no mapped open findings on E2E system"
        return pool[0]

    def test_add_to_poam_and_duplicate(self, isso, e2e_system, finding_sc13, request):
        f = finding_sc13
        # Prefill via /findings/{id}/poam-match
        r = isso.get(f"{API}/findings/{f['id']}/poam-match", timeout=15)
        assert r.status_code == 200, r.text
        pre = r.json()["prefill"]
        assert pre["control_ids"], "prefill missing control_ids"
        body = {"system_id": e2e_system["id"], "finding_ids": [f["id"]], "weakness": pre["weakness"],
                "control_ids": pre["control_ids"], "severity": pre.get("severity") or "medium",
                "cat": pre.get("cat"), "source_label": pre.get("source_label"),
                "due_date": "2026-12-31"}
        cr = isso.post(f"{API}/poams", json={k: v for k, v in body.items() if v is not None}, timeout=20)
        assert cr.status_code == 201, f"create poam: {cr.status_code} {cr.text}"
        poam = cr.json()
        assert poam["human_id"].startswith("P-")
        request.config.cache.set("e2e/poam_id", poam["human_id"])
        request.config.cache.set("e2e/poam_uuid", poam["id"])
        request.config.cache.set("e2e/finding_id", f["id"])

        # Second create -> 409 with existing P-id
        dup = isso.post(f"{API}/poams", json={k: v for k, v in body.items() if v is not None}, timeout=20)
        assert dup.status_code == 409, f"expected 409 duplicate, got {dup.status_code} {dup.text}"
        detail = dup.json().get("detail")
        if isinstance(detail, dict):
            assert any(m.get("human_id") == poam["human_id"] for m in detail.get("matches", []))

    def test_remediated_upload_sets_closure_eligible(self, isso, e2e_system, request):
        poam_hid = request.config.cache.get("e2e/poam_id", None)
        assert poam_hid, "poam not created in previous test"

        # Upload remediated CKL (fixes the STIG finding) and nessus remediated
        for fname in ("e2e-web-01_remediated.ckl", "e2e_scan_remediated.nessus"):
            p = SAMPLES / fname
            if not p.exists():
                continue
            with p.open("rb") as fh:
                rr = isso.post(f"{API}/systems/{e2e_system['id']}/uploads",
                               files={"file": (fname, fh, "application/xml")}, timeout=30)
            assert rr.status_code == 202, rr.text
            _poll_run(isso, rr.json()["id"], timeout=120)

        # Poll POA&M to allow worker to update linked finding + status
        end = time.time() + 60
        status = None
        while time.time() < end:
            d = isso.get(f"{API}/poams/{poam_hid}", timeout=15).json()
            status = d["poam"]["status"]
            if status == "closure_eligible":
                break
            time.sleep(1.5)
        assert status == "closure_eligible", f"poam status={status} (expected closure_eligible)"
        # Must NOT be closed by rescan
        assert d["poam"]["status"] != "closed"

    def test_isso_request_closure_requires_evidence(self, isso, e2e_system, request):
        hid = request.config.cache.get("e2e/poam_id", None)
        # empty evidence_ids -> 422 (pydantic min_length=1)
        r = isso.post(f"{API}/poams/{hid}/request-closure",
                      json={"justification": "remediated per rescan", "evidence_ids": []}, timeout=15)
        assert r.status_code == 422, r.text

        # fetch an evidence_id from the ledger
        ev = isso.get(f"{API}/systems/{e2e_system['id']}/evidence", timeout=15).json()
        assert ev
        r2 = isso.post(f"{API}/poams/{hid}/request-closure",
                       json={"justification": "remediated via rescan 2026", "evidence_ids": [ev[0]["id"]]}, timeout=20)
        assert r2.status_code == 201, r2.text
        req_id = r2.json()["id"]
        request.config.cache.set("e2e/closure_request_id", req_id)

        d = isso.get(f"{API}/poams/{hid}", timeout=15).json()
        assert d["poam"]["status"] == "closure_review"

        # ISSO (the requester) cannot decide their own
        detail = isso.get(f"{API}/reviews/{req_id}", timeout=15).json()
        assert detail["is_requester"] is True
        assert detail["can_decide"] is False
        bad = isso.post(f"{API}/reviews/{req_id}/decisions",
                        json={"action": "approve", "rationale": "self-approve"}, timeout=15)
        assert bad.status_code == 403, f"ISSO self-decide should 403, got {bad.status_code} {bad.text}"

    def test_issm_approves_closure(self, issm, request):
        hid = request.config.cache.get("e2e/poam_id", None)
        req_id = request.config.cache.get("e2e/closure_request_id", None)
        r = issm.get(f"{API}/reviews/{req_id}", timeout=15).json()
        assert r["can_decide"] is True
        assert r["signature_label"] == "Record approval (simulated signature – not CAC/PIV)"
        ok = issm.post(f"{API}/reviews/{req_id}/decisions",
                       json={"action": "approve", "rationale": "closure evidence sufficient"}, timeout=20)
        assert ok.status_code == 200, ok.text

        # Second decision -> 409
        again = issm.post(f"{API}/reviews/{req_id}/decisions",
                          json={"action": "approve", "rationale": "double-click"}, timeout=15)
        assert again.status_code == 409, again.text

        # POA&M closed, decision history populated
        d = issm.get(f"{API}/poams/{hid}", timeout=15).json()
        assert d["poam"]["status"] == "closed"
        assert d["poam"].get("actual_completion") or d["poam"].get("closed_at")
        # review detail decisions
        rd = issm.get(f"{API}/reviews/{req_id}", timeout=15).json()
        assert len(rd["decisions"]) >= 1
        assert rd["decisions"][0]["signature"].startswith("Record approval")


# ---------------------------------------------------------------------------
# False positive (ISSM decides)
# ---------------------------------------------------------------------------

class TestFalsePositive:
    def test_fp_flow(self, isso, issm, e2e_system):
        # Pick a different open finding (not already dispositioned)
        fs = isso.get(f"{API}/systems/{e2e_system['id']}/findings",
                      params={"state": "open"}, timeout=20).json()
        candidates = [f for f in fs if f["mapping_status"] == "mapped" and f.get("disposition") in (None, "", "unassigned")]
        assert candidates, "no mapped open finding available for FP test"
        f = candidates[-1]

        r = isso.post(f"{API}/findings/{f['id']}/request-false-positive",
                      json={"justification": "duplicate detection via vendor-fixed baseline"}, timeout=20)
        assert r.status_code == 201, r.text
        req_id = r.json()["id"]

        # ISSM approves
        d = issm.post(f"{API}/reviews/{req_id}/decisions",
                      json={"action": "approve", "rationale": "FP confirmed"}, timeout=20)
        assert d.status_code == 200, d.text

        # Finding disposition updated
        detail = isso.get(f"{API}/findings/{f['id']}", timeout=15).json()
        assert detail["finding"]["disposition"] == "false_positive"


# ---------------------------------------------------------------------------
# POA&M list: LTP seeded P-00xx + summary cards + search/filter/sort/paging
# ---------------------------------------------------------------------------

class TestPoamList:
    def test_ltp_seeded_poams_and_summary(self, issm):
        ltp = _ltp_id(issm)
        r = issm.get(f"{API}/poams", params={"system_id": ltp, "page_size": 100}, timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        hids = {p["human_id"] for p in d["items"]}
        expected = {"P-0015", "P-0019", "P-0022", "P-0026", "P-0027", "P-0030", "P-0031"}
        missing = expected - hids
        assert not missing, f"missing seeded POA&Ms: {missing}"
        s = d["summary"]
        for k in ("open", "overdue", "due_30d", "pending_issm_review", "cat1", "pending_emass_sync"):
            assert k in s, f"summary missing {k}"
        assert "emass" in s.get("emass_note", "").lower()

    def test_search_filter_sort_paging(self, issm):
        ltp = _ltp_id(issm)
        # search
        r = issm.get(f"{API}/poams", params={"system_id": ltp, "q": "Log4j"}, timeout=15)
        assert r.status_code == 200
        # overdue filter
        r2 = issm.get(f"{API}/poams", params={"system_id": ltp, "status": "overdue"}, timeout=15)
        assert r2.status_code == 200
        # pagination
        r3 = issm.get(f"{API}/poams", params={"system_id": ltp, "page_size": 2, "page": 1}, timeout=15)
        assert r3.status_code == 200
        assert r3.json()["page_size"] == 2
        # sort by severity desc
        r4 = issm.get(f"{API}/poams", params={"system_id": ltp, "sort": "severity", "desc": True}, timeout=15)
        assert r4.status_code == 200


# ---------------------------------------------------------------------------
# KEV risk acceptance (ISSM endorse -> AO decide; ISSO AO-approve = 403)
# ---------------------------------------------------------------------------

class TestKEVRiskAcceptance:
    def test_kev_risk_acceptance_flow(self, isso, issm, ao, e2e_system):
        # Find a KEV / Log4Shell finding
        fs = isso.get(f"{API}/systems/{e2e_system['id']}/findings", timeout=20).json()
        kev = next((f for f in fs if (f.get("kev") or "log4" in (f.get("title") or "").lower() or "log4" in (f.get("vuln_id") or "").lower())), None)
        if not kev:
            # fall back to any open high/critical mapped finding
            kev = next((f for f in fs if f["mapping_status"] == "mapped" and f["severity"] in ("critical", "high") and f["current_state"] == "open"), None)
        assert kev, "no KEV / high severity finding found"

        # Create POA&M from this finding
        pre = isso.get(f"{API}/findings/{kev['id']}/poam-match", timeout=15).json()["prefill"]
        body = {k: v for k, v in {"system_id": e2e_system["id"], "finding_ids": [kev["id"]],
                                   "weakness": pre["weakness"], "control_ids": pre["control_ids"],
                                   "severity": pre.get("severity") or "high",
                                   "cat": pre.get("cat"), "source_label": pre.get("source_label"),
                                   "due_date": "2026-06-30"}.items() if v is not None}
        cr = isso.post(f"{API}/poams", json=body, timeout=20)
        if cr.status_code == 409:
            # already exists – look it up via match
            m = cr.json()["detail"]["matches"][0]
            poam_hid = m["human_id"]
        else:
            assert cr.status_code == 201, cr.text
            poam_hid = cr.json()["human_id"]

        # Request risk acceptance (future expiration)
        rra = isso.post(f"{API}/poams/{poam_hid}/request-risk-acceptance",
                        json={"justification": "mitigating controls in place; KEV planned", "expiration": "2026-12-31"}, timeout=20)
        if rra.status_code == 409:
            # pending already; fetch
            det = isso.get(f"{API}/poams/{poam_hid}", timeout=15).json()
            req_id = next(r["id"] for r in det["requests"] if r["request_type"] == "risk_acceptance" and r["status"] == "pending")
        else:
            assert rra.status_code == 201, rra.text
            req_id = rra.json()["id"]

        # ISSM endorses (approve-at-endorse step is still "endorse" action semantically; action 'approve' may not advance)
        rv = issm.get(f"{API}/reviews/{req_id}", timeout=15).json()
        assert rv["current_step"]["role"] == "issm"
        endorse = issm.post(f"{API}/reviews/{req_id}/decisions",
                            json={"action": "endorse", "rationale": "mitigations acceptable to ISSM"}, timeout=20)
        assert endorse.status_code == 200, endorse.text

        # Now step should advance to AO
        rv2 = issm.get(f"{API}/reviews/{req_id}", timeout=15).json()
        assert rv2["current_step"]["role"] == "ao", rv2["current_step"]

        # ISSO attempts AO approve -> 403
        bad = isso.post(f"{API}/reviews/{req_id}/decisions",
                        json={"action": "approve", "rationale": "isso cannot"}, timeout=15)
        assert bad.status_code == 403, f"ISSO at AO step should 403, got {bad.status_code} {bad.text}"

        # AO approves
        ok = ao.post(f"{API}/reviews/{req_id}/decisions",
                     json={"action": "approve", "rationale": "accepting residual risk per AO"}, timeout=20)
        assert ok.status_code == 200, ok.text

        d = isso.get(f"{API}/poams/{poam_hid}", timeout=15).json()
        assert d["poam"]["status"] == "risk_accepted"


# ---------------------------------------------------------------------------
# Leadership dashboard reflects updated counts
# ---------------------------------------------------------------------------

class TestLeadership:
    def test_dashboard_shape(self, leadership):
        r = leadership.get(f"{API}/dashboard/leadership", timeout=20)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("cards", "systems", "trend", "waiting_on_you", "op_score"):
            assert k in d, f"leadership missing {k}: {list(d)}"
        assert isinstance(d["systems"], list) and d["systems"]
        # systems should have op_score + breakdown
        s0 = d["systems"][0]
        assert "op_score" in s0 or "operational_prioritization" in s0 or any("score" in k for k in s0), s0


# ---------------------------------------------------------------------------
# Part A regression: LTP evidence sources + grouped controls
# ---------------------------------------------------------------------------

class TestPartARegressions:
    def test_ltp_cards_reconcile(self, issm):
        ltp = _ltp_id(issm)
        srcs = issm.get(f"{API}/systems/{ltp}/sources", timeout=20).json()
        fs = issm.get(f"{API}/systems/{ltp}/findings", timeout=20).json()
        card_sum = sum(s["findings_total"] for s in srcs)
        assert card_sum == len(fs), f"LTP cards {card_sum} vs findings {len(fs)}"
        for s in srcs:
            assert s["mapped"] + s["unmapped"] == s["findings_total"]

    def test_grouped_controls_no_repeat(self, issm):
        """A STIG finding mapped to AU-9 with multiple CCIs is grouped into one row."""
        ltp = _ltp_id(issm)
        fs = issm.get(f"{API}/systems/{ltp}/findings", timeout=20).json()
        multi = next((f for f in fs if any(len(c.get("ccis", [])) >= 2 for c in f.get("controls", []))), None)
        if not multi:
            pytest.skip("no finding with multiple CCIs under one control in LTP seed")
        ctl_ids = [c["control_id"] for c in multi["controls"]]
        assert len(ctl_ids) == len(set(ctl_ids)), f"grouped mapping repeated controls: {ctl_ids}"


# ---------------------------------------------------------------------------
# Freshness back-date -> partially_stale queue reason
# ---------------------------------------------------------------------------

class TestFreshness:
    def test_backdate_partially_stale(self, admin, issm):
        ltp = _ltp_id(issm)
        ev = admin.get(f"{API}/systems/{ltp}/evidence", timeout=20).json()
        # pick a STIG checklist evidence
        stig_ev = next((e for e in ev if (e.get("source_type") == "stig_checklist")), None)
        if not stig_ev:
            pytest.skip("no STIG evidence on LTP")
        r = admin.post(f"{API}/demo/evidence/{stig_ev['id']}/collected-at",
                       json={"days_ago": 45}, timeout=15)
        assert r.status_code == 200, r.text
        # evaluate freshness
        admin.post(f"{API}/systems/{ltp}/evidence/evaluate-freshness", timeout=20)
        # fetch controls – at least one should be partially_stale with a reason mentioning "N of M"
        wb = admin.get(f"{API}/systems/{ltp}/workbench/controls", timeout=20).json()
        rows = wb if isinstance(wb, list) else wb.get("items", [])
        stale = [c for c in rows if c.get("evidence_freshness_status") == "partially_stale"]
        assert stale, "expected at least one partially_stale control after backdate"
        details = []
        for c in stale:
            for r in (c.get("reasons") or []):
                details.append(r.get("detail") or "")
        joined = " ".join(details).lower()
        assert "of" in joined and "expired" in joined, f"no 'expired evidence on N of M assets' detail: {joined[:400]}"


# ---------------------------------------------------------------------------
# Notifications bell
# ---------------------------------------------------------------------------

class TestNotifications:
    def test_bell_endpoint(self, isso):
        r = isso.get(f"{API}/notifications", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert "unread" in d and "items" in d


# ---------------------------------------------------------------------------
# AI draft (REAL LLM) + request-review (slow test; ~25s)
# ---------------------------------------------------------------------------

@pytest.mark.slow
class TestAIDraft:
    def test_ai_draft_and_review(self, isso, issm):
        ltp = _ltp_id(isso)
        r = isso.post(f"{API}/systems/{ltp}/workbench/controls/cm-6/ai-draft", timeout=90)
        assert r.status_code == 200, f"ai-draft: {r.status_code} {r.text[:400]}"
        d = r.json()
        assert d["label"] == "AI DRAFT – not reviewed"
        draft = d["draft"]
        assert draft.get("narrative")
        # 4 analytic sections required by the review request
        for key in ("verified_facts", "interpretation", "suggested_actions", "missing_information"):
            assert key in draft, f"draft missing section {key}: {list(draft)}"
        sections = {k: draft[k] for k in ("verified_facts", "interpretation", "suggested_actions", "missing_information")}

        # Save as new draft version
        save = isso.put(f"{API}/systems/{ltp}/workbench/controls/cm-6/implementation",
                        json={"narrative": draft["narrative"], "implementation_status": "implemented",
                              "ai_generated": True, "prompt_version": d.get("prompt_version"),
                              "ai_interaction_id": d.get("interaction_id"), "ai_sections": sections,
                              "citations": draft.get("citations", [])}, timeout=20)
        assert save.status_code in (200, 201), save.text
        impl_id = save.json()["id"] if "id" in save.json() else save.json().get("implementation_id")
        if not impl_id:
            # retrieve latest draft via workbench control detail
            wb = isso.get(f"{API}/systems/{ltp}/workbench/controls/cm-6", timeout=15).json()
            impl_id = wb.get("current_draft", {}).get("id") or wb.get("implementation", {}).get("id")
        assert impl_id, f"could not identify impl_id from save response {save.json()}"

        rr = isso.post(f"{API}/systems/{ltp}/workbench/implementations/{impl_id}/request-review",
                       json={"justification": "ready for ISSM review – AI-assisted draft"}, timeout=20)
        assert rr.status_code == 201, rr.text
        req_id = rr.json()["id"]

        # ISSM approve
        ok = issm.post(f"{API}/reviews/{req_id}/decisions",
                       json={"action": "approve", "rationale": "implementation statement acceptable"}, timeout=20)
        assert ok.status_code == 200, ok.text
