"""Live preview API checks for SME Section-1 against REACT_APP_BACKEND_URL."""
import os, io, time
import pytest, requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
pytestmark = pytest.mark.skipif(not BASE, reason="live preview check: set REACT_APP_BACKEND_URL to run")
FRESH_EMAIL = "sme-fresh-97c795@example.com"
FRESH_PWD = "Sme-Fresh-2026!x"
DEMO_EMAIL = "sme-fresh-d64e62@example.com"
DEMO_PWD = "Sme-Fresh-2026!x"
RA_POLICY_ID = "9dc6b55b-a85d-4777-aec0-4a305ba0cc8e"
DEMO_SYSTEM_ID = "192424e1-c3b1-48cf-b6d3-b6250119c4b5"


def _login(email, pwd):
    r = requests.post(f"{BASE}/api/v1/auth/login", json={"email": email, "password": pwd}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def fresh_tok():
    return _login(FRESH_EMAIL, FRESH_PWD)


@pytest.fixture(scope="module")
def demo_tok():
    return _login(DEMO_EMAIL, DEMO_PWD)


def _H(t):
    return {"Authorization": f"Bearer {t}"}


def test_content_counts_reconciliation(fresh_tok):
    r = requests.get(f"{BASE}/api/v1/content/counts", headers=_H(fresh_tok), timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["base_controls"] == 324
    assert d["enhancements"] == 872
    assert d["rev5_total"] == 1196
    assert d["selectable"] == 1014
    assert "324" in d["labels"]["rev5_total"] and "872" in d["labels"]["rev5_total"] and "1,196" in d["labels"]["rev5_total"]
    assert "1,014" in d["labels"]["selectable"]


def test_fresh_signup_has_no_systems(fresh_tok):
    r = requests.get(f"{BASE}/api/v1/systems", headers=_H(fresh_tok), timeout=30)
    assert r.status_code == 200
    body = r.json()
    items = body.get("items", body) if isinstance(body, dict) else body
    assert len(items) == 0, f"fresh account should be empty, got {len(items)}"


def test_sandbox_load_demo_data_idempotent(fresh_tok):
    r1 = requests.post(f"{BASE}/api/v1/sandbox/demo-data", headers=_H(fresh_tok), timeout=60)
    assert r1.status_code in (200, 201, 202), r1.text
    r2 = requests.post(f"{BASE}/api/v1/sandbox/demo-data", headers=_H(fresh_tok), timeout=60)
    assert r2.status_code in (200, 201, 202), r2.text
    time.sleep(1)
    r = requests.get(f"{BASE}/api/v1/systems", headers=_H(fresh_tok), timeout=30)
    body = r.json()
    items = body.get("items", body) if isinstance(body, dict) else body
    assert len(items) >= 4, f"expected >=4 synthetic systems, got {len(items)}"


def test_sandbox_clear_removes_demo(fresh_tok):
    r = requests.post(f"{BASE}/api/v1/sandbox/reset", headers=_H(fresh_tok), timeout=60)
    assert r.status_code in (200, 202), r.text
    time.sleep(1)
    r = requests.get(f"{BASE}/api/v1/systems", headers=_H(fresh_tok), timeout=30)
    body = r.json()
    items = body.get("items", body) if isinstance(body, dict) else body
    assert len(items) == 0


def test_workbench_has_evidence_filter_matches_summary(demo_tok):
    s = requests.get(f"{BASE}/api/v1/systems/{DEMO_SYSTEM_ID}/workbench/summary", headers=_H(demo_tok), timeout=60)
    assert s.status_code == 200, s.text
    with_ev = s.json().get("with_evidence")
    assert isinstance(with_ev, int), s.json()
    r = requests.get(f"{BASE}/api/v1/systems/{DEMO_SYSTEM_ID}/workbench/controls",
                     headers=_H(demo_tok), params={"has_evidence": "yes"}, timeout=60)
    assert r.status_code == 200
    assert len(r.json()) == with_ev, f"has_evidence=yes count {len(r.json())} != summary.with_evidence {with_ev}"


def test_workbench_status_save_persists(demo_tok):
    r = requests.get(f"{BASE}/api/v1/systems/{DEMO_SYSTEM_ID}/workbench/controls", headers=_H(demo_tok), timeout=60)
    assert r.status_code == 200
    items = r.json()
    assert items, "no controls"
    first = items[0]
    cid = first.get("control_id") or first.get("id")
    r2 = requests.put(
        f"{BASE}/api/v1/systems/{DEMO_SYSTEM_ID}/workbench/controls/{cid}/status",
        headers=_H(demo_tok), json={"implementation_status": "implemented"}, timeout=30,
    )
    assert r2.status_code in (200, 204), f"status PUT failed: {r2.status_code} {r2.text}"
    body = r2.json() if r2.text else {}
    assert body.get("implementation_status") == "implemented" or r2.status_code == 204


def test_policy_detail_contains_ra1_mapping_with_confidence(demo_tok):
    r = requests.get(f"{BASE}/api/v1/policies/{RA_POLICY_ID}", headers=_H(demo_tok), timeout=60)
    assert r.status_code == 200, r.text
    d = r.json()
    cur = d.get("control_mappings", [])
    assert cur, "expected at least one control mapping"
    acros = []
    for m in cur:
        acros.append(m.get("control_acronym") or m.get("acronym") or m.get("control_id") or "")
    assert any("RA-1" in str(a).upper() for a in acros), f"expected RA-1 mapping; got {acros}"
    # confidence present
    assert any(m.get("confidence") in ("High", "Medium", "Low", "high", "medium", "low") for m in cur), cur


def test_reject_mapping_requires_justification(demo_tok):
    # Attempt reject with short justification -> 400/422
    r = requests.post(
        f"{BASE}/api/v1/policies/{RA_POLICY_ID}/control-mappings/reject",
        headers=_H(demo_tok),
        json={"control_acronym": "AC-17", "justification": "short"},
        timeout=30,
    )
    assert r.status_code in (400, 422), f"expected validation error for short justification, got {r.status_code}: {r.text}"


def test_scan_upload_rejection_lists_formats(demo_tok):
    files = {"file": ("bogus.txt", io.BytesIO(b"not a scan at all"), "text/plain")}
    r = requests.post(
        f"{BASE}/api/v1/systems/{DEMO_SYSTEM_ID}/uploads",
        headers=_H(demo_tok), files=files, timeout=30,
    )
    assert r.status_code in (400, 415, 422), f"expected rejection, got {r.status_code}: {r.text}"
    body = r.text.lower()
    assert any(fmt in body for fmt in ("ckl", "xccdf", "arf", "nessus")), f"expected supported formats list, got {r.text}"


def test_export_params_csv_has_header(demo_tok):
    r = requests.get(f"{BASE}/api/v1/policies/{RA_POLICY_ID}/parameters.csv", headers=_H(demo_tok), timeout=30)
    assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
    lines = r.text.splitlines()
    assert lines, "empty CSV"
    header = lines[0]
    assert "Parameter ID" in header and "policy" in header, f"header missing: {header}"  # CSV = screen columns since bbb8d81
    assert len(lines) >= 2, "expected at least one data row"
