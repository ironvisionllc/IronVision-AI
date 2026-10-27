# Live regression (public URL) for iteration 21: P1 bulk jobs + SCA lifecycle, P4 documents, P6 POA&M risk, P2 requirement counts
import os
import time
import uuid

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") + "/api/v1"
pytestmark = pytest.mark.skipif(not os.environ.get("REACT_APP_BACKEND_URL"), reason="live only")


def _demo():
    r = requests.post(f"{BASE}/auth/demo-login", timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _act(tok, role):
    r = requests.post(f"{BASE}/sandbox/act-as", json={"role": role}, headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="module")
def tok():
    return _demo()


@pytest.fixture(scope="module")
def sid(tok):
    s = requests.get(f"{BASE}/systems", headers={"Authorization": f"Bearer {tok}"}, timeout=30).json()
    s = s if isinstance(s, list) else s.get("items", [])
    return next(x["id"] for x in s if x.get("acronym") == "LTP")


@pytest.fixture(scope="module")
def isso(tok):
    return _act(tok, "isso")


@pytest.fixture(scope="module")
def sca(tok):
    return _act(tok, "sca")


@pytest.fixture(scope="module")
def owner(tok):
    return _act(tok, "system_owner")


@pytest.fixture(scope="module")
def viewer(tok):
    return _act(tok, "leadership_viewer")


def _queue(h, sid):
    r = requests.get(f"{BASE}/mapping-review", params={"system_id": sid}, headers=h, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()["queue"]


def _poll(h, jid, limit=90):
    for _ in range(limit):
        j = requests.get(f"{BASE}/mapping-review/bulk-jobs/{jid}", headers=h, timeout=30).json()
        if j["status"] in ("succeeded", "failed"):
            return j
        time.sleep(1)
    pytest.fail(f"bulk job {jid} did not finish: {j}")


STATE: dict = {}


# --- P1 bulk job: idempotency, progress, ISSO approve → awaiting SCA ---
class TestBulkAndSca:
    def test_isso_bulk_approve_idempotent(self, isso, sid):
        q = [x for x in _queue(isso, sid) if x["kind"] == "status" and not x.get("awaiting_sca")]
        assert len(q) >= 3, "need ≥3 open status suggestions"
        keys = [x["key"] for x in q[:3]]
        STATE["keys"] = keys
        idem = f"t21-{uuid.uuid4().hex}"
        body = {"system_id": sid, "action": "approve", "justification": "", "item_keys": keys, "awaiting_sca": False, "idempotency_key": idem}
        r1 = requests.post(f"{BASE}/mapping-review/bulk-jobs", json=body, headers=isso, timeout=60)
        assert r1.status_code == 202, r1.text
        r2 = requests.post(f"{BASE}/mapping-review/bulk-jobs", json=body, headers=isso, timeout=60)
        assert r2.status_code == 202 and r2.json()["id"] == r1.json()["id"], "same idempotency key must return same job"
        assert r1.json()["total"] == 3
        j = _poll(isso, r1.json()["id"])
        print("job", j)
        assert j["status"] == "succeeded" and j["succeeded"] == 3 and j["processed"] == 3 and not j["failed"]
        STATE["job"] = j["id"]

    def test_items_now_awaiting_sca(self, isso, sid):
        q = {x["key"]: x for x in _queue(isso, sid)}
        for k in STATE["keys"]:
            assert k in q and q[k]["awaiting_sca"] is True, f"{k} should be awaiting SCA"
            assert "SCA" in q[k]["next_actor"]

    def test_retry_nothing_failed_409(self, isso):
        r = requests.post(f"{BASE}/mapping-review/bulk-jobs/{STATE['job']}/retry", headers=isso, timeout=30)
        assert r.status_code == 409, r.text

    def test_isso_cannot_approve_awaiting(self, isso, sid):
        q = {x["key"]: x for x in _queue(isso, sid)}
        it = q[STATE["keys"][0]]
        r = requests.post(f"{BASE}/mapping-review/decide", headers=isso, timeout=30, json={
            "system_id": sid, "action": "approve", "justification": "",
            "items": [{"kind": it["kind"], "ids": it["ids"], "control_id": it["control_id"], "evidence_fp": it.get("evidence_fp")}]})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "separation_of_duties", r.text

    def test_isso_bulk_awaiting_403(self, isso, sid):
        r = requests.post(f"{BASE}/mapping-review/bulk-jobs", headers=isso, timeout=30, json={
            "system_id": sid, "action": "approve", "awaiting_sca": True, "idempotency_key": f"t21-{uuid.uuid4().hex}"})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "separation_of_duties", r.text

    def test_owner_cannot_approve_awaiting(self, owner, sid):
        q = {x["key"]: x for x in _queue(owner, sid)}
        it = q[STATE["keys"][0]]
        r = requests.post(f"{BASE}/mapping-review/decide", headers=owner, timeout=30, json={
            "system_id": sid, "action": "approve", "justification": "",
            "items": [{"kind": it["kind"], "ids": it["ids"], "control_id": it["control_id"], "evidence_fp": it.get("evidence_fp")}]})
        print("owner", r.status_code, r.text[:200])
        assert r.status_code == 403

    def test_sca_cannot_approve_open_impl(self, sca, sid):
        q = [x for x in _queue(sca, sid) if x["kind"] == "status" and not x.get("awaiting_sca")]
        r = requests.post(f"{BASE}/mapping-review/bulk-jobs", headers=sca, timeout=30, json={
            "system_id": sid, "action": "approve", "item_keys": [q[0]["key"]], "idempotency_key": f"t21-{uuid.uuid4().hex}"})
        assert r.status_code == 403 and r.json()["detail"]["code"] == "separation_of_duties", r.text

    def test_sca_bulk_confirms_satisfied(self, sca, sid):
        k = STATE["keys"][0]
        r = requests.post(f"{BASE}/mapping-review/bulk-jobs", headers=sca, timeout=30, json={
            "system_id": sid, "action": "approve", "item_keys": [k], "awaiting_sca": True, "idempotency_key": f"t21-{uuid.uuid4().hex}"})
        assert r.status_code == 202, r.text
        j = _poll(sca, r.json()["id"])
        assert j["succeeded"] == 1, j
        assert k not in {x["key"] for x in _queue(sca, sid)}, "satisfied item must leave queue"
        ctl = k.split(":", 1)[1]
        a = requests.get(f"{BASE}/systems/{sid}/workbench/controls/{ctl}", headers=sca, timeout=30).json()["assignment"]
        assert a["implementation_status"] == "implemented" and a["assessment_status"] == "satisfied", a
        STATE["sca_job"] = j["id"]

    def test_sca_retry_permission(self, sca):
        # retry endpoint requires finding.map – SCA (assessment.perform only) cannot retry its own jobs; 409 expected (nothing failed)
        r = requests.post(f"{BASE}/mapping-review/bulk-jobs/{STATE['sca_job']}/retry", headers=sca, timeout=30)
        print("sca retry", r.status_code, r.text[:200])
        assert r.status_code == 409, f"SCA retry of own job gives {r.status_code} (expected 409 nothing-failed, not 403)"

    def test_unknown_job_404(self, isso):
        r = requests.get(f"{BASE}/mapping-review/bulk-jobs/{uuid.uuid4()}", headers=isso, timeout=30)
        assert r.status_code == 404

    def test_reject_requires_reason(self, isso, sid):
        q = [x for x in _queue(isso, sid) if x["kind"] == "status" and not x.get("awaiting_sca")]
        r = requests.post(f"{BASE}/mapping-review/bulk-jobs", headers=isso, timeout=30, json={
            "system_id": sid, "action": "reject", "justification": "short", "item_keys": [q[0]["key"]], "idempotency_key": f"t21-{uuid.uuid4().hex}"})
        assert r.status_code == 422, r.text

    def test_viewer_forbidden(self, viewer, sid):
        r = requests.post(f"{BASE}/mapping-review/bulk-jobs", headers=viewer, timeout=30, json={
            "system_id": sid, "action": "approve", "kind": "status", "idempotency_key": f"t21-{uuid.uuid4().hex}"})
        assert r.status_code == 403, r.text


# --- P4 documents ---
class TestDocuments:
    @pytest.mark.parametrize("kind", ["ssp", "sar", "rar"])
    def test_check_and_download(self, isso, sid, kind):
        c = requests.get(f"{BASE}/systems/{sid}/documents/{kind}/check", headers=isso, timeout=60).json()
        assert c["status"] in ("DRAFT", "DRAFT – INCOMPLETE") and isinstance(c["missing"], list)
        for fmt, sig in (("docx", b"PK"), ("pdf", b"%PDF")):
            r = requests.get(f"{BASE}/systems/{sid}/documents/{kind}", params={"format": fmt}, headers=isso, timeout=90)
            assert r.status_code == 200 and r.content[:len(sig)] == sig, (kind, fmt, r.status_code)
            assert f"_{kind.upper()}_" in r.headers["content-disposition"]

    def test_bad_kind(self, isso, sid):
        assert requests.get(f"{BASE}/systems/{sid}/documents/xyz/check", headers=isso, timeout=30).status_code == 422


# --- P6 POA&M risk ---
class TestPoamRisk:
    def _pid(self, h, sid):
        p = requests.get(f"{BASE}/poams", params={"system_id": sid}, headers=h, timeout=30).json()
        p = p if isinstance(p, list) else p.get("items", [])
        return next(x["id"] for x in p if x.get("status") not in ("closed", "risk_accepted", "closure_review", "risk_acceptance_review"))

    def test_risk_view_and_patch(self, isso, sid):
        pid = self._pid(isso, sid)
        v = requests.get(f"{BASE}/poams/{pid}/risk", headers=isso, timeout=30).json()
        assert v["scale"] == ["Very Low", "Low", "Moderate", "High", "Very High"] and "severity" in v["technical"]
        r = requests.patch(f"{BASE}/poams/{pid}", json={"likelihood": "High", "impact": "Moderate"}, headers=isso, timeout=30)
        assert r.status_code == 200, r.text
        v = requests.get(f"{BASE}/poams/{pid}/risk", headers=isso, timeout=30).json()
        assert v["emass"]["likelihood"] == "High" and v["source"].get("likelihood") == "manual"

    def test_invalid_scale_422(self, isso, sid):
        pid = self._pid(isso, sid)
        r = requests.patch(f"{BASE}/poams/{pid}", json={"likelihood": "Critical"}, headers=isso, timeout=30)
        assert r.status_code == 422

    def test_viewer_cannot_patch(self, viewer, sid):
        pid = self._pid(viewer, sid)
        r = requests.patch(f"{BASE}/poams/{pid}", json={"likelihood": "Low"}, headers=viewer, timeout=30)
        assert r.status_code == 403

    def test_from_control_without_values_422(self, isso, sid):
        pid = self._pid(isso, sid)
        v = requests.get(f"{BASE}/poams/{pid}/risk", headers=isso, timeout=30).json()
        empty = [c for c in v["control_risk_assessments"] if not c["values"]]
        if not empty:
            pytest.skip("all controls have risk values")
        r = requests.post(f"{BASE}/poams/{pid}/risk/from-control", json={"control_id": empty[0]["control_id"]}, headers=isso, timeout=30)
        assert r.status_code == 422


# --- P2 requirement counts ---
def test_ra5_requirement_counts(isso, sid):
    d = requests.get(f"{BASE}/systems/{sid}/workbench/controls/ra-5/requirement-counts", headers=isso, timeout=60).json()
    assert d["base_only"]["ccis"] == 14 and d["base_only"]["objectives"] == 10 and d["base_only"]["requirements"] == 24
    assert d["including_assigned_enhancements"]["requirements"] >= 24
