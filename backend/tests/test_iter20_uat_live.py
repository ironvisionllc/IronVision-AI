# Live regression (public URL) for iteration 20: Import Test Plan, ISCM strategy, Select guided flow, SLCM due
import os
import pytest
import requests

from tests.live_ids import system_id as live_system_id

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") + "/api/v1"
SID = live_system_id(BASE, "LTP", "3630fca0-4fb1-45d5-b020-a93156344bb4")
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "test_plan")
pytestmark = pytest.mark.skipif(not os.environ.get("REACT_APP_BACKEND_URL"), reason="live only")


def _login():
    r = requests.post(f"{BASE}/auth/login", json={"email": "demo@ironvision.ai", "password": "IronVisionDemo!2026"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _act(tok, role):
    r = requests.post(f"{BASE}/sandbox/act-as", json={"role": role}, headers={"Authorization": f"Bearer {tok}"}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def base_tok():
    return _login()


@pytest.fixture(scope="module")
def isso(base_tok):
    return {"Authorization": f"Bearer {_act(base_tok, 'isso')}"}


@pytest.fixture(scope="module")
def issm(base_tok):
    return {"Authorization": f"Bearer {_act(base_tok, 'issm')}"}


@pytest.fixture(scope="module")
def viewer(base_tok):
    return {"Authorization": f"Bearer {_act(base_tok, 'leadership_viewer')}"}


def _up(h, kind, name):
    with open(os.path.join(FIX, name), "rb") as f:
        return requests.post(f"{BASE}/systems/{SID}/tr/test-plan/{kind}", headers=h, files={"file": (name, f.read())}, timeout=60)


# --- Import Test Plan ---
class TestTestPlan:
    def test_valid_xlsx_preview(self, isso):
        before = len(requests.get(f"{BASE}/systems/{SID}/tr/workbooks", headers=isso, timeout=30).json())
        r = _up(isso, "preview", "SYNTHETIC_TestPlan_valid.xlsx")
        assert r.status_code == 200, r.text
        d = r.json()
        print("valid xlsx counts", d["counts"], "rejected", d["rejected"])
        assert d["counts"]["rows"] >= 1
        assert all(a["ap_acronym"] and a["cci"].startswith("CCI-") for a in d["accepted"] + d["rejected"] if a.get("cci"))
        after = len(requests.get(f"{BASE}/systems/{SID}/tr/workbooks", headers=isso, timeout=30).json())
        assert before == after, "preview must not save"

    def test_valid_csv_preview(self, isso):
        r = _up(isso, "preview", "SYNTHETIC_TestPlan_valid.csv")
        assert r.status_code == 200, r.text
        print("csv counts", r.json()["counts"], r.json()["format"])

    def test_invalid_rows(self, isso):
        r = _up(isso, "preview", "INVALID_TestPlan_rows.xlsx")
        assert r.status_code == 200, r.text
        rej = r.json()["rejected"]
        for x in rej:
            print("rejected", x["row"], x["reason"])
        assert {3, 4, 5, 6, 7, 8} <= {x["row"] for x in rej}
        assert all(x["reason"] for x in rej)

    def test_missing_columns(self, isso):
        r = _up(isso, "preview", "INVALID_TestPlan_missing_columns.xlsx")
        assert r.status_code == 422
        det = r.json()["detail"]
        print(det)
        assert "Missing required column(s): AP Acronym, CCI" in det["message"]
        assert det["found_columns"]

    def test_docx(self, isso):
        r = _up(isso, "preview", "INVALID_TestPlan.docx")
        assert r.status_code == 422 and "Unsupported format .docx" in str(r.json()["detail"])

    def test_corrupt(self, isso):
        r = _up(isso, "preview", "INVALID_TestPlan_corrupt.xlsx")
        print(r.status_code, r.text[:200])
        assert r.status_code == 422

    def test_viewer_403(self, viewer):
        for k in ("preview", "import"):
            r = _up(viewer, k, "SYNTHETIC_TestPlan_valid.xlsx")
            assert r.status_code == 403
            assert "ingest.upload" in r.json()["detail"]["message"]

    def test_import_csv(self, isso):
        r = _up(isso, "import", "SYNTHETIC_TestPlan_valid.csv")
        print(r.status_code, r.text[:400])
        if r.status_code in (409, 422):
            pytest.skip("all rows already imported (unchanged against existing)")
        assert r.status_code == 201
        wb = r.json()
        ws = requests.get(f"{BASE}/systems/{SID}/tr/workbooks", headers=isso, timeout=30).json()
        assert any(w["id"] == wb["id"] for w in ws)
        print("workbook status", wb.get("status"), {k: wb.get(k) for k in wb if "count" in k or "approv" in k})
        # re-preview: now all unchanged against existing (not errors)
        d = _up(isso, "preview", "SYNTHETIC_TestPlan_valid.csv").json()
        assert d["counts"]["accepted"] == 0
        assert all("Already in Test Results workbook" in x["reason"] for x in d["unchanged"])


# --- Continuous Monitoring Strategy ---
class TestIscm:
    def test_get(self, isso):
        r = requests.get(f"{BASE}/systems/{SID}/iscm", headers=isso, timeout=30)
        assert r.status_code == 200
        d = r.json()
        print("strategy", d["strategy"]["status"], d["strategy"]["version"], d["feeds"])
        assert d["strategy"]["approved_snapshot"]
        assert d["feeds"]["total"] > 0

    def test_draft_submit_approve(self, isso, issm):
        v = requests.get(f"{BASE}/systems/{SID}/iscm", headers=isso, timeout=30).json()["strategy"]
        snap_before = v["approved_snapshot"]
        body = {k: v[k] for k in ("narrative", "scope", "reporting", "review_activities", "evidence_requirements")}
        body["defaults"] = {**(v["defaults"] or {}), "slcm_comments": "TEST_iter20 draft"}
        body["profiles"] = [{k: p[k] for k in ("name", "match_type", "match_value", "values")} for p in v["profiles"]]
        r = requests.put(f"{BASE}/systems/{SID}/iscm", headers=isso, json=body, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()["strategy"]
        assert d["status"] == "draft" and d["approved_snapshot"] == snap_before
        r = requests.post(f"{BASE}/systems/{SID}/iscm/submit", headers=isso, timeout=30)
        assert r.status_code == 200 and r.json()["strategy"]["status"] == "pending_approval"
        r = requests.post(f"{BASE}/systems/{SID}/iscm/decision", headers=isso, json={"approve": True}, timeout=30)
        assert r.status_code == 403, r.text
        r = requests.post(f"{BASE}/systems/{SID}/iscm/decision", headers=issm, json={"approve": True, "comment": "ok"}, timeout=30)
        assert r.status_code == 200, r.text
        s = r.json()["strategy"]
        assert s["status"] == "approved" and s["approved_snapshot"]["defaults"].get("slcm_comments") == "TEST_iter20 draft"
        print("approved version", s["version"])
        # restore original defaults (drop TEST_ comment) so demo data is not polluted
        orig = {k: val for k, val in (v["defaults"] or {}).items() if not str(val).startswith("TEST_")}
        requests.put(f"{BASE}/systems/{SID}/iscm", headers=isso, json={**body, "defaults": orig}, timeout=30)
        requests.post(f"{BASE}/systems/{SID}/iscm/submit", headers=isso, timeout=30)
        r = requests.post(f"{BASE}/systems/{SID}/iscm/decision", headers=issm, json={"approve": True, "comment": "restore"}, timeout=30)
        assert r.status_code == 200 and "slcm_comments" not in r.json()["strategy"]["approved_snapshot"]["defaults"]

    def test_promote_preview(self, isso):
        r = requests.get(f"{BASE}/systems/{SID}/iscm/promote-preview", headers=isso, timeout=30)
        assert r.status_code == 200
        print("promote items", r.json()["items"][:3])

    def test_due(self, isso):
        r = requests.get(f"{BASE}/systems/{SID}/iscm/due", headers=isso, timeout=30)
        assert r.status_code == 200
        print("due counts", r.json()["counts"])

    def test_viewer_cannot_save(self, viewer):
        r = requests.put(f"{BASE}/systems/{SID}/iscm", headers=viewer, json={"defaults": {}}, timeout=30)
        assert r.status_code == 403


# --- Select guided flow ---
class TestSelect:
    def test_review(self, isso):
        r = requests.get(f"{BASE}/systems/{SID}/select/review", headers=isso, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        print("review", d["original"], d["final"], d["counts"], d["reconciliation"], d["needs_decision"], d["approval"])

    def test_tailor_dry_run(self, isso):
        before = requests.get(f"{BASE}/systems/{SID}/select/review", headers=isso, timeout=30).json()["final"]["count"]
        r = requests.post(f"{BASE}/systems/{SID}/select/tailor", headers=isso, timeout=30,
                          json={"action": "remove", "control_ids": ["au-2"], "justification": "TEST dry run rationale", "applicability": "Not Applicable", "dry_run": True})
        assert r.status_code == 200, r.text
        d = r.json()
        print("dry", d["removed"], d["would_delete"])
        assert d["nothing_saved"] and "au-2" in d["removed"]
        after = requests.get(f"{BASE}/systems/{SID}/select/review", headers=isso, timeout=30).json()["final"]["count"]
        assert before == after

    def test_baseline_dry_run(self, isso):
        r = requests.post(f"{BASE}/systems/{SID}/select/baseline", headers=isso, timeout=30,
                          json={"baseline_key": "high", "dry_run": True})
        print(r.status_code, r.text[:300])
        assert r.status_code in (200, 409, 422)
