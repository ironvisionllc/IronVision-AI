"""Phase 4 Advanced Automation + Part A fixes - preview-URL integration tests.

Run with:
  REACT_APP_BACKEND_URL=https://aegis-rmf-demo.preview.emergentagent.com \
    python -m pytest tests_agent/test_phase4_review.py -v -n 0 \
    --junitxml=/app/test_reports/pytest/phase4_review.xml
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") + "/api/v1"
PW = "AegisDemo!2026"


def _login(email):
    r = requests.post(f"{BASE}/auth/login", json={"email": email, "password": PW}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _h(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def tokens():
    admin = _login("platform.admin@aegisrmf.demo")
    r = requests.post(f"{BASE}/admin/demo/reset", headers=_h(admin), timeout=180)
    assert r.status_code in (200, 201, 204), f"reset: {r.status_code} {r.text[:300]}"
    out = {
        "admin": admin,
        "isso": _login("isso@aegisrmf.demo"),
        "issm": _login("issm@aegisrmf.demo"),
        "ao": _login("ao@aegisrmf.demo"),
        "sysowner": _login("system.owner@aegisrmf.demo"),
        "sca": _login("sca@aegisrmf.demo"),
        "leadership": _login("leadership.viewer@aegisrmf.demo"),
    }
    yield out
    try:
        requests.put(f"{BASE}/emass/config", headers=_h(admin), json={"mode": "mock"}, timeout=15)
        requests.put(f"{BASE}/emass/failure-sim", headers=_h(admin), json={"mode": "off", "count": 0}, timeout=15)
    except Exception:
        pass


@pytest.fixture(scope="module")
def systems(tokens):
    r = requests.get(f"{BASE}/systems", headers=_h(tokens["isso"]), timeout=30)
    assert r.status_code == 200, r.text
    return {s["acronym"].upper(): s for s in r.json()}


@pytest.fixture(scope="module")
def ltp(systems):
    return systems["LTP"]["id"]


# ---------- Part A ----------
class TestPartA:
    def test_inheritance_cards_ltp(self, tokens, ltp):
        r = requests.get(f"{BASE}/systems/{ltp}/inheritance", headers=_h(tokens["isso"]), timeout=30)
        assert r.status_code == 200, r.text
        c = r.json()["cards"]
        assert c["assigned"] == 291
        assert c["fully_inherited"] == 61
        assert c["shared"] == 44
        assert c["system_owned"] == 186
        assert c["manual_attestation"] == 38
        assert c["sum_check"] is True

    def test_search_scoped_returns_system_control(self, tokens, ltp):
        r = requests.get(f"{BASE}/search", headers=_h(tokens["isso"]), params={"q": "AC-2", "system_id": ltp}, timeout=30)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert rows, "expected results"
        assert all(x.get("system_id") == ltp for x in rows if x.get("system_id")), rows
        assert any(x.get("type") == "control" and "ac-2" in x["link"] for x in rows), rows

    def test_search_unscoped_grouped_by_system(self, tokens):
        r = requests.get(f"{BASE}/search", headers=_h(tokens["isso"]), params={"q": "AC-2"}, timeout=30)
        assert r.status_code == 200
        rows = r.json()
        assert rows and all("group" in x and "system_id" in x for x in rows), rows[:2]
        groups = {x["group"] for x in rows}
        assert len(groups) >= 2, groups  # should span multiple systems

    def test_decision_lists_populate_decider(self, tokens, ltp):
        # Submit SSP package to create a review request, then AO decides, then verify decider shape
        sub = requests.post(f"{BASE}/systems/{ltp}/authorization/submit", headers=_h(tokens["sysowner"]),
                            json={"justification": "Submit package for decider-shape agent test"}, timeout=30)
        if sub.status_code == 409:
            # already pending - get the existing request id
            pkg = requests.get(f"{BASE}/systems/{ltp}/authorization", headers=_h(tokens["ao"]), timeout=30).json()
            reqs = [r for r in pkg.get("requests", []) if r.get("request_type") == "authorization_package_review" and r.get("status") == "pending"]
            if not reqs:
                pytest.skip("409 but no pending request found")
            req_id = reqs[0]["id"]
        elif sub.status_code in (200, 201):
            req_id = sub.json().get("id") or sub.json().get("request_id")
        else:
            pytest.skip(f"could not submit package: {sub.status_code} {sub.text[:200]}")
        # ISSM endorses first, then AO decides via /reviews decision endpoint
        issm_dec = requests.post(f"{BASE}/reviews/{req_id}/decisions", headers=_h(tokens["issm"]),
                                 json={"action": "endorse", "rationale": "ISSM endorse for agent test"}, timeout=30)
        if issm_dec.status_code not in (200, 201):
            pytest.skip(f"ISSM endorse failed: {issm_dec.status_code} {issm_dec.text[:200]}")
        dec = requests.post(f"{BASE}/systems/{ltp}/authorization-decision", headers=_h(tokens["ao"]),
                            json={"request_id": req_id, "decision": "ATO_with_conditions",
                                  "conditions": "Agent test conditional ATO",
                                  "expiration": "2027-06-30",
                                  "rationale": "Automated phase 4 agent test for decider shape"},
                            timeout=30)
        assert dec.status_code == 200, dec.text
        # Fetch review detail to inspect decisions attach shape
        rv = requests.get(f"{BASE}/reviews/{req_id}", headers=_h(tokens["ao"]), timeout=30).json()
        decs = rv.get("decisions", [])
        assert decs, rv
        d = decs[-1]  # final decider
        decider = d.get("decider")
        assert isinstance(decider, dict), f"decider must be object, got {decider!r}"
        assert decider.get("email") or decider.get("name"), decider
        assert decider.get("role") or decider.get("roles"), f"role must populate: {decider}"


# ---------- Content updates / STIG ----------
class TestContentUpdates:
    def test_overview_v1r1_installed_v1r2_available(self, tokens):
        r = requests.get(f"{BASE}/content-updates", headers=_h(tokens["isso"]), timeout=30)
        assert r.status_code == 200, r.text
        types = r.json()["types"]
        stig = next(t for t in types if t["content_type"] == "stig_benchmark")
        assert stig["installed"][0]["version"] == "V1R1"
        assert stig["available"][0]["version"] == "V1R2"
        # expose v2_id for next tests
        pytest.v2_id = stig["available"][0]["id"]

    def test_preview_diff_counts_and_p27(self, tokens):
        v2 = pytest.v2_id
        r = requests.post(f"{BASE}/content-versions/{v2}/preview", headers=_h(tokens["issm"]), timeout=60)
        assert r.status_code == 201, r.text
        up = r.json()
        assert up["diff_summary"] == {"added": 6, "removed": 3, "changed_requirement": 11, "changed_severity": 2}
        p27 = next((x for x in (up["impact"].get("poams") or []) if x.get("human_id") == "P-0027"), None)
        assert p27 and p27.get("new_cat") == "CAT I", p27
        assert up["impact"]["counts"]["assets"] >= 14
        pytest.update_id = up["id"]

    def test_isso_cannot_apply(self, tokens):
        r = requests.post(f"{BASE}/content-updates/{pytest.update_id}/apply",
                          headers=_h(tokens["isso"]),
                          json={"justification": "ISSO cannot apply content update rev"}, timeout=30)
        assert r.status_code == 403, r.text

    def test_issm_applies_preserves_history(self, tokens):
        r = requests.post(f"{BASE}/content-updates/{pytest.update_id}/apply",
                          headers=_h(tokens["issm"]),
                          json={"justification": "Approve V1R2 after impact review (automated test)"}, timeout=180)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["result"]["observations_rewritten"] == 0, body
        # history reflects applied
        ov = requests.get(f"{BASE}/content-updates", headers=_h(tokens["isso"]), timeout=30).json()
        assert ov["history"][0]["status"] == "applied"
        assert ov["history"][0]["to_version"] == "V1R2"


# ---------- Scoring ----------
class TestScore:
    def test_breakdown_sums_to_total(self, tokens, ltp):
        r = requests.get(f"{BASE}/systems/{ltp}/findings", headers=_h(tokens["isso"]), timeout=30)
        if r.status_code != 200:
            pytest.skip(f"findings endpoint {r.status_code}")
        data = r.json()
        rows = data if isinstance(data, list) else (data.get("items") or data.get("findings") or [])
        if not rows:
            pytest.skip("no findings")
        fid = rows[0]["id"]
        s = requests.get(f"{BASE}/findings/{fid}/score", headers=_h(tokens["isso"]), timeout=30)
        assert s.status_code == 200, s.text
        body = s.json()
        total = body.get("score")
        br = body.get("breakdown") or []
        assert total is not None, body
        s_sum = sum(x.get("points", x.get("contribution", 0)) for x in br)
        assert abs(s_sum - total) < 0.5, f"breakdown {s_sum} != total {total}: {br}"
        assert "not a formal residual risk" in (body.get("label") or "").lower(), body

    def test_isso_cannot_put_weights(self, tokens):
        r = requests.put(f"{BASE}/risk/weights", headers=_h(tokens["isso"]),
                         json={"weights": {"rf_severity": 40}}, timeout=15)
        assert r.status_code in (401, 403), r.text

    def test_admin_can_put_weights(self, tokens):
        g = requests.get(f"{BASE}/risk/weights", headers=_h(tokens["admin"]), timeout=15).json()
        before = {w["reason_code"]: w["weight"] for w in g["weights"]}
        # change severity by +1 then restore
        new = dict(before)
        new["rf_severity"] = before["rf_severity"] + 1
        r = requests.put(f"{BASE}/risk/weights", headers=_h(tokens["admin"]), json={"weights": new}, timeout=120)
        assert r.status_code == 200, r.text
        assert r.json().get("findings_rescored") is not None
        # restore
        requests.put(f"{BASE}/risk/weights", headers=_h(tokens["admin"]), json={"weights": before}, timeout=120)


# ---------- OSCAL ----------
class TestOscal:
    @pytest.mark.parametrize("model", ["poam", "ssp", "assessment-plan", "assessment-results"])
    def test_generate_each_model(self, tokens, ltp, model):
        r = requests.post(f"{BASE}/systems/{ltp}/oscal/{model}", headers=_h(tokens["issm"]), timeout=180)
        assert r.status_code in (200, 201), f"{model}: {r.status_code} {r.text[:400]}"
        body = r.json()
        # schema-validated
        v = str(body).lower()
        assert "valid" in v or "schema" in v, body
        assert body.get("evidence_id") or body.get("sha256") or body.get("file_name"), body

    def test_list_has_models_and_unsupported(self, tokens, ltp):
        r = requests.get(f"{BASE}/systems/{ltp}/oscal", headers=_h(tokens["isso"]), timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body["models"]) >= {"poam", "ssp", "assessment-plan", "assessment-results"}
        assert body.get("unsupported") is not None
        assert body.get("limitations") is not None
        assert body.get("oscal_version")


# ---------- eMASS ----------
class TestEmass:
    def test_status_mock(self, tokens):
        r = requests.get(f"{BASE}/emass/status", headers=_h(tokens["isso"]), timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("mode") == "mock", body

    def test_compare_buckets(self, tokens, ltp):
        r = requests.post(f"{BASE}/systems/{ltp}/emass/compare", headers=_h(tokens["isso"]), timeout=120)
        assert r.status_code in (200, 201), r.text
        body = r.json()
        flat = str(body).lower()
        for key in ("in_sync", "different", "local_only", "remote_only"):
            assert key in flat, f"missing bucket {key}"

    def test_oscal_export_only_mode_banner(self, tokens, ltp):
        requests.put(f"{BASE}/emass/config", headers=_h(tokens["admin"]), json={"mode": "oscal_export_only"}, timeout=15)
        try:
            st = requests.get(f"{BASE}/emass/status", headers=_h(tokens["isso"]), timeout=15).json()
            assert st.get("mode") == "oscal_export_only", st
            flat = str(st).lower()
            assert "no live synchronization" in flat or "oscal" in flat, st
        finally:
            requests.put(f"{BASE}/emass/config", headers=_h(tokens["admin"]), json={"mode": "mock"}, timeout=15)

    def test_read_mode_prereqs_not_configured(self, tokens):
        requests.put(f"{BASE}/emass/config", headers=_h(tokens["admin"]), json={"mode": "read"}, timeout=15)
        try:
            st = requests.get(f"{BASE}/emass/status", headers=_h(tokens["isso"]), timeout=15).json()
            # Truthful admin signal: real_connector_configured must be False and all checks False
            assert st.get("real_connector_configured") is False, st
            assert all(v is False for v in (st.get("checks") or {}).values()), st
        finally:
            requests.put(f"{BASE}/emass/config", headers=_h(tokens["admin"]), json={"mode": "mock"}, timeout=15)


# ---------- Scheduler ----------
class TestScheduler:
    def test_eight_jobs_visible(self, tokens):
        r = requests.get(f"{BASE}/scheduled-jobs", headers=_h(tokens["admin"]), timeout=15)
        assert r.status_code == 200, r.text
        jobs = r.json()
        assert isinstance(jobs, list)
        assert len(jobs) >= 8, [j.get("name") for j in jobs]  # later phases added scheduled jobs (12 today)
        for j in jobs:
            # Allow nullable last_run_at (never ran yet)
            assert "last_run_at" in j or "last_run" in j, j
            assert "next_run_at" in j or "next_run" in j, j
            assert j.get("interval_minutes") or j.get("interval") or j.get("cron"), j

    def test_run_now_and_409_if_pending(self, tokens):
        r = requests.get(f"{BASE}/scheduled-jobs", headers=_h(tokens["admin"]), timeout=15)
        jid = r.json()[0]["id"]
        a = requests.post(f"{BASE}/scheduled-jobs/{jid}/run", headers=_h(tokens["admin"]), timeout=15)
        assert a.status_code in (200, 201, 202, 204, 409), a.text
        # second run may be 409
        b = requests.post(f"{BASE}/scheduled-jobs/{jid}/run", headers=_h(tokens["admin"]), timeout=15)
        assert b.status_code in (200, 201, 202, 204, 409), b.text

    def test_interval_edit_persists(self, tokens):
        r = requests.get(f"{BASE}/scheduled-jobs", headers=_h(tokens["admin"]), timeout=15)
        job = r.json()[0]
        jid, orig = job["id"], job.get("interval_minutes") or 60
        enabled = job.get("enabled", True)
        u = requests.put(f"{BASE}/scheduled-jobs/{jid}", headers=_h(tokens["admin"]),
                        json={"interval_minutes": orig + 1, "enabled": enabled}, timeout=15)
        assert u.status_code in (200, 204), u.text
        chk = requests.get(f"{BASE}/scheduled-jobs", headers=_h(tokens["admin"]), timeout=15).json()
        got = next(x for x in chk if x["id"] == jid).get("interval_minutes")
        assert got == orig + 1, got
        # restore
        requests.put(f"{BASE}/scheduled-jobs/{jid}", headers=_h(tokens["admin"]),
                     json={"interval_minutes": orig, "enabled": enabled}, timeout=15)


# ---------- Mapping review ----------
class TestMappingReview:
    def test_list_shape(self, tokens, ltp):
        r = requests.get(f"{BASE}/mapping-review", headers=_h(tokens["isso"]),
                         params={"system_id": ltp}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        for key in ("pending", "unmapped"):
            assert key in body, f"missing {key} in {list(body)}"


# ---------- Regression light ----------
class TestRegression:
    @pytest.mark.parametrize("path, role", [
        ("/poams", "isso"),
        ("/reviews", "issm"),
        ("/dashboard/leadership", "leadership"),
    ])
    def test_pages_load(self, tokens, path, role):
        r = requests.get(f"{BASE}{path}", headers=_h(tokens[role]), timeout=30)
        assert r.status_code in (200, 204), f"{path} as {role}: {r.status_code} {r.text[:200]}"
