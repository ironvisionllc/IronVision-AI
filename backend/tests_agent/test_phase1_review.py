"""Phase 1 agent review tests against live preview via REACT_APP_BACKEND_URL."""
from __future__ import annotations
import os, time, pathlib, uuid
import pytest, requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://aegis-rmf-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api/v1"
PWD = "AegisDemo!2026"

EMAILS = {
    "system_owner": "system.owner@aegisrmf.demo",
    "isso": "isso@aegisrmf.demo",
    "issm": "issm@aegisrmf.demo",
    "sca": "sca@aegisrmf.demo",
    "ao": "ao@aegisrmf.demo",
    "devsecops": "devsecops@aegisrmf.demo",
    "leadership_viewer": "leadership.viewer@aegisrmf.demo",
    "platform_admin": "platform.admin@aegisrmf.demo",
}


def _login(email: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PWD}, timeout=20)
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _h(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="module")
def tokens():
    return {role: _login(email) for role, email in EMAILS.items()}


def test_login_all_eight_users(tokens):
    assert len(tokens) == 8
    for role, tok in tokens.items():
        me = requests.get(f"{API}/auth/me", headers=_h(tok), timeout=10)
        assert me.status_code == 200, f"/me failed for {role}"


def test_dev_user_options_exactly_eight():
    r = requests.get(f"{API}/auth/provider", timeout=10)
    assert r.status_code == 200
    accounts = r.json().get("dev_accounts", [])
    # the public account picker was removed (one shared demo account + self sign-up); the 8 role accounts still sign in by password
    assert accounts == [], f"no public account picker expected, got {len(accounts)}"
    assert r.json().get("demo_login_enabled") is True


def _systems(tokens, role="isso"):
    r = requests.get(f"{API}/systems", headers=_h(tokens[role]), timeout=15)
    assert r.status_code == 200, r.text[:300]
    return r.json()


def _find(items, acronym):
    for s in items:
        if (s.get("acronym") or "").upper() == acronym.upper():
            return s
    return None


def test_systems_list_four_seeded(tokens):
    items = _systems(tokens)
    assert len(items) >= 4, f"expected >=4 systems, got {len(items)}"
    for a in ("LTP", "MPP", "FMDH", "TRS"):
        assert _find(items, a), f"missing seeded system {a}"


def test_ltp_has_291_assigned_controls(tokens):
    ltp = _find(_systems(tokens), "LTP")
    assert ltp
    assert ltp["metrics"]["assigned_controls"] == 291, f"LTP assigned_controls={ltp['metrics']['assigned_controls']}"


def test_register_moderate_as_issm_287_and_lv_forbidden(tokens):
    # leadership_viewer should be 403
    payload_lv = {
        "name": f"LV forbid {int(time.time())}",
        "baseline_key": "moderate",
        "confidentiality_impact": "Moderate",
        "integrity_impact": "Moderate",
        "availability_impact": "Moderate",
    }
    r_lv = requests.post(f"{API}/systems", headers=_h(tokens["leadership_viewer"]), json=payload_lv, timeout=15)
    assert r_lv.status_code == 403, f"leadership_viewer register expected 403, got {r_lv.status_code}: {r_lv.text[:200]}"

    # ISSM registers moderate (no overlays) -> expect 287
    payload = {
        "name": f"Agent Moderate {int(time.time())}",
        "acronym": f"AM{int(time.time())%100000}",
        "baseline_key": "moderate",
        "confidentiality_impact": "Moderate",
        "integrity_impact": "Moderate",
        "availability_impact": "Moderate",
        "include_privacy": False,
        "overlay_keys": [],
        "tailoring": [],
    }
    r = requests.post(f"{API}/systems", headers=_h(tokens["issm"]), json=payload, timeout=30)
    assert r.status_code == 201, f"issm register: {r.status_code} {r.text[:400]}"
    sys = r.json()
    assert sys["metrics"]["assigned_controls"] == 287, f"new moderate: expected 287 got {sys['metrics']['assigned_controls']}"


def test_evidence_sources_mock_labels_and_no_secrets(tokens):
    ltp = _find(_systems(tokens), "LTP")
    r = requests.get(f"{API}/systems/{ltp['id']}/sources", headers=_h(tokens["isso"]), timeout=15)
    assert r.status_code == 200, r.text[:200]
    sources = r.json()
    assert len(sources) >= 1
    # No secret_ciphertext leaked
    for s in sources:
        assert "secret_ciphertext" not in s, f"secret_ciphertext leaked for source {s.get('name')}"
        assert isinstance(s.get("credential_set"), bool)
    # Non-file connectors should carry a mock/demo adapter_mode
    non_file = [s for s in sources if s.get("source_type") not in ("stig_file", "acas_file", "file", "file_import")]
    assert non_file, "expected at least one non-file connector"
    assert any((s.get("adapter_mode") or "").lower() in ("mock", "demo", "synthetic") for s in non_file), \
        f"no mock/demo adapter_mode on non-file sources: {[s.get('adapter_mode') for s in non_file]}"


SAMPLE = pathlib.Path("/app/samples/stig/ltp_db-server-01.ckl")


def _poll(tok, run_id, timeout=120):
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = requests.get(f"{API}/ingest-runs/{run_id}", headers=_h(tok), timeout=15)
        if r.status_code == 200:
            last = r.json()
            st = (last.get("run") or {}).get("status") or last.get("status")
            if st in ("completed", "duplicate", "failed", "succeeded"):
                return last, st
        time.sleep(2)
    return last, None


def _upload(tok, sid, source_id, content, filename):
    files = {"file": (filename, content, "application/xml")}
    data = {"source_id": str(source_id)} if source_id else {}
    return requests.post(f"{API}/systems/{sid}/uploads", headers=_h(tok), files=files, data=data, timeout=60)


def test_duplicate_detection_and_modified_upload(tokens):
    assert SAMPLE.exists()
    content = SAMPLE.read_bytes()
    ltp = _find(_systems(tokens), "LTP")
    sid = ltp["id"]
    srcs = requests.get(f"{API}/systems/{sid}/sources", headers=_h(tokens["isso"]), timeout=15).json()
    file_src = next((s for s in srcs if s.get("source_type") in ("stig_file", "stig_ckl", "stig")), None)
    source_id = file_src["id"] if file_src else None

    r1 = _upload(tokens["isso"], sid, source_id, content, "ltp_db-server-01.ckl")
    assert r1.status_code == 202, f"first upload: {r1.status_code} {r1.text[:300]}"
    run1_id = r1.json()["id"]
    _, st1 = _poll(tokens["isso"], run1_id, 120)
    assert st1 in ("completed", "duplicate", "succeeded"), f"run1 status: {st1}"

    r2 = _upload(tokens["isso"], sid, source_id, content, "ltp_db-server-01.ckl")
    assert r2.status_code == 202
    run2_id = r2.json()["id"]
    _, st2 = _poll(tokens["isso"], run2_id, 60)
    assert st2 == "duplicate", f"expected duplicate, got {st2}"

    modified = content + f"\n<!-- agent test modification {uuid.uuid4().hex} -->\n".encode()
    r3 = _upload(tokens["isso"], sid, source_id, modified, "ltp_db-server-01-mod.ckl")
    assert r3.status_code == 202
    run3_id = r3.json()["id"]
    _, st3 = _poll(tokens["isso"], run3_id, 180)
    assert st3 in ("completed", "succeeded"), f"modified run status: {st3}"


def test_workbench_control_has_four_statuses(tokens):
    ltp = _find(_systems(tokens), "LTP")
    sid = ltp["id"]
    r = requests.get(f"{API}/systems/{sid}/workbench/controls", headers=_h(tokens["isso"]), timeout=20)
    assert r.status_code == 200, r.text[:300]
    ctrls = r.json()
    assert isinstance(ctrls, list) and len(ctrls) > 0
    cid = (ctrls[0].get("control_id") or ctrls[0].get("id"))
    r2 = requests.get(f"{API}/systems/{sid}/workbench/controls/{cid}", headers=_h(tokens["isso"]), timeout=20)
    assert r2.status_code == 200, r2.text[:300]
    body = r2.json()
    serialized = str(body).lower()
    for key in ("implementation_status", "assessment_status", "monitoring_status", "evidence_freshness_status"):
        assert key in serialized, f"workbench detail missing '{key}' (keys: {list(body.keys())})"


def test_evidence_ledger_verify_platform_admin(tokens):
    ltp = _find(_systems(tokens), "LTP")
    r = requests.post(f"{API}/systems/{ltp['id']}/evidence/verify", headers=_h(tokens["platform_admin"]), timeout=60)
    assert r.status_code in (200, 202), f"{r.status_code} {r.text[:300]}"


def test_isso_cannot_use_demo_backdate(tokens):
    ltp = _find(_systems(tokens), "LTP")
    ledger = requests.get(f"{API}/systems/{ltp['id']}/evidence", headers=_h(tokens["isso"]), timeout=15).json()
    if not ledger:
        pytest.skip("no evidence to back-date")
    eid = ledger[0]["id"]
    r_isso = requests.post(f"{API}/demo/evidence/{eid}/collected-at",
                           headers=_h(tokens["isso"]), json={"days_ago": 45}, timeout=15)
    assert r_isso.status_code == 403, f"isso demo back-date expected 403, got {r_isso.status_code}"


def test_leadership_dashboard_access(tokens):
    for role in ("leadership_viewer", "ao", "issm"):
        r = requests.get(f"{API}/dashboard/leadership", headers=_h(tokens[role]), timeout=20)
        assert r.status_code == 200, f"dashboard {role}: {r.status_code} {r.text[:200]}"
    r = requests.get(f"{API}/dashboard/leadership", headers=_h(tokens["isso"]), timeout=20)
    assert r.status_code == 403, f"isso dashboard expected 403, got {r.status_code}"


def test_system_detail_assets_and_roles(tokens):
    ltp = _find(_systems(tokens), "LTP")
    sid = ltp["id"]
    assets = requests.get(f"{API}/systems/{sid}/assets", headers=_h(tokens["isso"]), timeout=15)
    assert assets.status_code == 200
    roles = requests.get(f"{API}/systems/{sid}/roles", headers=_h(tokens["isso"]), timeout=15)
    assert roles.status_code == 200
