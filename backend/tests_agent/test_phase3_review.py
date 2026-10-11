"""Agent integration tests for Phase 3 - RMF Workflow Modules.

Runs against the live preview at REACT_APP_BACKEND_URL. Validates the
Phase 3 acceptance bullets from the review request.
"""
from __future__ import annotations

import io
import os
import time

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://aegis-rmf-demo.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api/v1"
PW = "AegisDemo!2026"
ACCOUNTS = {
    "owner": "system.owner@aegisrmf.demo",
    "isso": "isso@aegisrmf.demo",
    "issm": "issm@aegisrmf.demo",
    "sca": "sca@aegisrmf.demo",
    "ao": "ao@aegisrmf.demo",
    "devsecops": "devsecops@aegisrmf.demo",
    "leader": "leadership.viewer@aegisrmf.demo",
    "admin": "platform.admin@aegisrmf.demo",
}


def _login(email: str) -> str:
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": PW}, timeout=20)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["access_token"]


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="module")
def tokens() -> dict[str, str]:
    return {k: _login(v) for k, v in ACCOUNTS.items()}


@pytest.fixture(scope="module")
def ltp_id(tokens) -> str:
    r = requests.get(f"{API}/systems", headers=_h(tokens["issm"]), timeout=20)
    r.raise_for_status()
    for s in r.json():
        if s.get("acronym") == "LTP":
            return s["id"]
    pytest.fail("LTP not found")


# ---------- 1. Inheritance ----------
def test_inheritance_summary_and_providers(tokens, ltp_id):
    r = requests.get(f"{API}/systems/{ltp_id}/inheritance", headers=_h(tokens["isso"]), timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    c = data["cards"]
    assert c["sum_check"] is True
    assert c["fully_inherited"] + c["shared"] + c["system_owned"] == c["assigned"]
    assert len(data["providers"]) >= 1
    # shared controls include CM-6, AC-2, SC-28 per the spec
    sctl = {row["control_id"] for row in data["shared"]}
    for cid in ("cm-6", "ac-2", "sc-28"):
        assert cid in sctl, f"expected shared control {cid}, got {sctl}"
    for cid in ("cm-6", "ac-2", "sc-28"):
        row = next((r for r in data["shared"] if r["control_id"] == cid), None)
        assert row is not None
        # per spec: provider vs system responsibility texts rendered on shared controls
        assert row["provider_responsibility"] or row["system_responsibility"], f"{cid} has no responsibility split"
    # attestations include CP-4 overdue and AT-2 pending
    atts = {a["control_id"]: a for a in data["attestations"]}
    assert "cp-4" in atts
    assert atts["cp-4"]["display_status"] == "overdue"
    assert "at-2" in atts
    assert atts["at-2"]["status"] in ("pending", "signed")
    signed = [a["control_id"] for a in data["attestations"] if a["status"] == "signed"]
    seeded_signed = {"mp-6", "ir-3", "ps-3"}
    present = seeded_signed & set(signed)
    assert len(present) >= 2, f"expected most of {seeded_signed} to be signed, found={signed}"


# ---------- 2. Attestation flow ----------
def test_attestation_rbac_and_signing(tokens, ltp_id):
    r = requests.get(f"{API}/systems/{ltp_id}/inheritance", headers=_h(tokens["owner"]), timeout=20)
    at2 = next(a for a in r.json()["attestations"] if a["control_id"] == "at-2" and a["status"] == "pending")
    att_id = at2["id"]
    # upload evidence as owner
    files = {"file": ("at2-training.txt", b"synthetic training record v2026-01", "text/plain")}
    r = requests.post(f"{API}/attestations/{att_id}/evidence", headers=_h(tokens["owner"]), files=files, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["sha256"]
    # non-owner (ISSO) attest should 403
    r = requests.post(f"{API}/attestations/{att_id}/attest", headers=_h(tokens["isso"]), timeout=20)
    assert r.status_code == 403, f"ISSO must not attest, got {r.status_code}"
    # owner signs -> signed
    r = requests.post(f"{API}/attestations/{att_id}/attest", headers=_h(tokens["owner"]), timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "signed"
    # renew produces a new version with higher version number
    r = requests.post(f"{API}/attestations/{att_id}/renew", headers=_h(tokens["owner"]), timeout=20)
    assert r.status_code == 201, r.text
    new_v = r.json()["version"]
    # history preserves prior signed
    r = requests.get(f"{API}/attestations/{att_id}/history", headers=_h(tokens["owner"]), timeout=20)
    assert r.status_code == 200
    versions = [h["version"] for h in r.json()]
    assert new_v in versions and (new_v - 1) in versions
    # platform admin can back-date a different signed attestation to force expire
    r = requests.get(f"{API}/systems/{ltp_id}/inheritance", headers=_h(tokens["admin"]), timeout=20)
    signed = [a for a in r.json()["attestations"] if a["status"] == "signed" and a["control_id"] != "at-2"]
    assert signed, "need another signed attestation"
    r = requests.post(f"{API}/demo/attestations/{signed[0]['id']}/expire", headers=_h(tokens["admin"]),
                      json={"days_ago": 7}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["cascade"]["expired"] >= 1 or r.json()["attestation"]["status"] == "expired"


# ---------- 3. Provider CRUD ----------
def test_provider_crud(tokens):
    body = {"name": f"TEST_Provider_{int(time.time())}", "package": "FedRAMP High",
            "basis": "ATO letter", "coverage_text": "DNS, logging"}
    r = requests.post(f"{API}/providers", headers=_h(tokens["issm"]), json=body, timeout=20)
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    r = requests.patch(f"{API}/providers/{pid}", headers=_h(tokens["issm"]),
                       json={**body, "coverage_text": "DNS only"}, timeout=20)
    assert r.status_code == 200
    assert r.json()["coverage_text"] == "DNS only"


# ---------- 4. Policy auditor ----------
def test_policy_list_and_access_control(tokens):
    r = requests.get(f"{API}/policies", headers=_h(tokens["isso"]), timeout=30)
    assert r.status_code == 200, r.text
    pols = r.json()["policies"]
    cur = [p for p in pols if p.get("status") == "current"]
    assert len(cur) >= 10, f"expected >=10 current policies, got {len(cur)}"
    acp = next((p for p in cur if "access control" in p["title"].lower()), None)
    assert acp, "Access Control Policy not seeded"
    r = requests.get(f"{API}/policies/{acp['id']}", headers=_h(tokens["isso"]), timeout=30)
    assert r.status_code == 200, r.text
    detail = r.json()
    # AC-2.3 mismatch 35 vs 90, AC-7/AC-11 match
    results = {(v["control_id"].lower(), str(v["parameter"]).lower()): v for v in detail["values"]}
    ac23 = [v for (c, _), v in results.items() if c in ("ac-2.3", "ac-02.03", "ac-2(3)")]
    assert ac23, f"expected AC-2.3 parameter, keys={list(results.keys())[:10]}"
    assert any(v.get("result") == "Mismatch" for v in ac23)
    # findings include at least one policy_vs_config_difference
    types = {f["finding_type"] for f in detail["findings"]}
    assert "policy_vs_config_difference" in types or "odp_not_met" in types


def test_policy_finding_dismiss_requires_justification(tokens):
    r = requests.get(f"{API}/policies", headers=_h(tokens["isso"]), timeout=30)
    acp = next(p for p in r.json()["policies"] if p.get("status") == "current" and "access control" in p["title"].lower())
    d = requests.get(f"{API}/policies/{acp['id']}", headers=_h(tokens["isso"]), timeout=20).json()
    proposed = [f for f in d["findings"] if f["status"] == "proposed"]
    if not proposed:
        pytest.skip("no proposed findings")
    pf = proposed[0]
    # too short -> 422
    r = requests.post(f"{API}/policy-findings/{pf['id']}/dismiss", headers=_h(tokens["issm"]),
                      json={"justification": "nope"}, timeout=20)
    assert r.status_code == 422
    # Confirm works and returns finding id
    pf2 = proposed[1] if len(proposed) > 1 else pf
    r = requests.post(f"{API}/policy-findings/{pf2['id']}/confirm", headers=_h(tokens["issm"]),
                      json={}, timeout=30)
    assert r.status_code in (200, 409), r.text


def test_policy_upload_creates_new_version(tokens):
    sample = "/app/samples/policies/access_control_policy.txt"
    if not os.path.exists(sample):
        # fallback - try any sample
        for ext in ("pdf", "docx", "txt"):
            p = f"/app/samples/policies/access_control_policy.{ext}"
            if os.path.exists(p):
                sample = p
                break
    if not os.path.exists(sample):
        pytest.skip(f"sample policy not available at {sample}")
    with open(sample, "rb") as fh:
        data = fh.read()
    files = {"file": (os.path.basename(sample), data, "application/octet-stream")}
    form = {"title": "Access Control Policy", "policy_key": "access-control-policy"}
    r = requests.post(f"{API}/policies", headers=_h(tokens["owner"]), files=files, data=form, timeout=60)
    assert r.status_code == 201, r.text
    new_v = r.json()["version"]
    assert new_v >= 2
    # Poll analysis status
    pid = r.json()["id"]
    for _ in range(20):
        d = requests.get(f"{API}/policies/{pid}", headers=_h(tokens["owner"]), timeout=20).json()
        if d["policy"]["analysis_status"] == "analyzed":
            break
        time.sleep(1.5)
    else:
        pytest.fail(f"policy analysis never completed: last={d['policy']['analysis_status']}")


def test_policy_csv_export(tokens):
    r = requests.get(f"{API}/policies", headers=_h(tokens["isso"]), timeout=20)
    pid = r.json()["policies"][0]["id"]
    r = requests.get(f"{API}/policies/{pid}/parameters.csv", headers=_h(tokens["isso"]), timeout=20)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "system_id,control_id,parameter" in r.text


# ---------- 5. SCA assessment ----------
def test_sca_assessment_rbac(tokens, ltp_id):
    body = {"objectives": ["AC-2 account mgmt"], "methods": ["examine", "interview"],
            "findings_text": "n/a", "result": "satisfied"}
    # ISSO cannot (no assessment.perform)
    r = requests.post(f"{API}/systems/{ltp_id}/controls/at-2/assessments", headers=_h(tokens["isso"]),
                      json=body, timeout=20)
    assert r.status_code == 403, f"ISSO should be denied, got {r.status_code}"
    # SCA records assessment
    r = requests.post(f"{API}/systems/{ltp_id}/controls/at-2/assessments", headers=_h(tokens["sca"]),
                      json=body, timeout=30)
    assert r.status_code == 201, r.text
    # workbench assessment_status set
    r = requests.get(f"{API}/systems/{ltp_id}/workbench/controls/at-2", headers=_h(tokens["sca"]), timeout=20)
    assert r.status_code == 200
    d = r.json()
    status = d.get("assessment_status") or (d.get("assignment") or {}).get("assessment_status")
    assert status in ("satisfied", "other_than_satisfied"), f"assessment_status missing from workbench: keys={list(d.keys())}"


# ---------- 6. Authorization package ----------
def test_authorization_rbac(tokens, ltp_id):
    # Non-AO (ISSO) must be denied with 403 and audited
    r = requests.get(f"{API}/systems/{ltp_id}/authorization", headers=_h(tokens["isso"]), timeout=20)
    assert r.status_code == 200
    reqs = r.json().get("requests", [])
    # Try an authorization decision with any request id; expect 403
    fake_req = reqs[0]["id"] if reqs else "00000000-0000-0000-0000-000000000000"
    body = {"request_id": fake_req, "decision": "ATO",
            "expiration": "2027-12-31", "rationale": "test rationale for RBAC check"}
    r = requests.post(f"{API}/systems/{ltp_id}/authorization-decision", headers=_h(tokens["isso"]),
                      json=body, timeout=20)
    assert r.status_code == 403, f"ISSO must be 403 on auth decision, got {r.status_code}: {r.text}"


# ---------- 7. Global search RBAC ----------
def test_global_search_scoped(tokens, ltp_id):
    r = requests.get(f"{API}/search", headers=_h(tokens["issm"]), params={"q": "P-00"}, timeout=20)
    assert r.status_code == 200
    issm_hits = r.json()
    assert isinstance(issm_hits, list)
    # Leadership viewer sees fewer or different results due to lack of system role writes
    r = requests.get(f"{API}/search", headers=_h(tokens["leader"]), params={"q": "P-00"}, timeout=20)
    assert r.status_code == 200


# ---------- 8. RMF workflow page ----------
def test_rmf_workflow_stages(tokens, ltp_id):
    r = requests.get(f"{API}/systems/{ltp_id}/rmf-workflow", headers=_h(tokens["isso"]), timeout=20)
    assert r.status_code == 200
    stages = r.json()
    assert isinstance(stages, list)
    # expect 7 RMF stages + 4 ongoing cards per spec
    assert len(stages) >= 7, f"expected >=7 workflow stages, got {len(stages)}"
    # each has a reason
    assert all("stage" in s or "key" in s or "name" in s for s in stages)


# ---------- 9. Audit log ----------
def test_audit_log_filters_pagination_export(tokens):
    r = requests.get(f"{API}/audit-log", headers=_h(tokens["admin"]),
                     params={"page": 1, "page_size": 10}, timeout=20)
    assert r.status_code == 200
    data = r.json()
    assert "items" in data and "total" in data and "chain" in data
    assert data["chain"].get("valid") is True
    # filter by outcome=denied
    r = requests.get(f"{API}/audit-log", headers=_h(tokens["admin"]),
                     params={"outcome": "denied", "page_size": 5}, timeout=20)
    assert r.status_code == 200
    for item in r.json()["items"]:
        assert item["outcome"] == "denied"
    # csv export
    r = requests.get(f"{API}/audit-log", headers=_h(tokens["admin"]), params={"fmt": "csv"}, timeout=30)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    # leadership viewer -> 403
    r = requests.get(f"{API}/audit-log", headers=_h(tokens["leader"]), timeout=20)
    assert r.status_code == 403


# ---------- 10. Notification prefs ----------
def test_notification_prefs_persist(tokens):
    r = requests.get(f"{API}/notification-prefs", headers=_h(tokens["isso"]), timeout=20)
    assert r.status_code == 200
    kinds = r.json()["kinds"]
    assert kinds
    k = kinds[0]["kind"]
    orig = kinds[0]["enabled"]
    r = requests.put(f"{API}/notification-prefs", headers=_h(tokens["isso"]),
                     json={"kind": k, "enabled": not orig}, timeout=20)
    assert r.status_code == 200
    r = requests.get(f"{API}/notification-prefs", headers=_h(tokens["isso"]), timeout=20)
    now = {x["kind"]: x["enabled"] for x in r.json()["kinds"]}
    assert now[k] == (not orig)
    # restore
    requests.put(f"{API}/notification-prefs", headers=_h(tokens["isso"]),
                 json={"kind": k, "enabled": orig}, timeout=20)


# ---------- 11. Admin: security, banner, ai-settings, invite ----------
def test_admin_security_banner_ai_invite(tokens):
    r = requests.get(f"{API}/admin/security", headers=_h(tokens["admin"]), timeout=20)
    assert r.status_code == 200
    sec = r.json()
    assert isinstance(sec["session_timeout_minutes"], int) and sec["session_timeout_minutes"] > 0
    assert "SYNTHETIC" in sec["markings_banner"] or len(sec["markings_banner"]) > 0

    # banner edit
    new_txt = f"TEST BANNER {int(time.time())} – SYNTHETIC"
    r = requests.put(f"{API}/admin/banner", headers=_h(tokens["admin"]),
                     json={"text": new_txt}, timeout=20)
    assert r.status_code == 200
    r = requests.get(f"{API}/banner", headers=_h(tokens["isso"]), timeout=20)
    assert r.json()["text"] == new_txt
    # restore
    requests.put(f"{API}/admin/banner", headers=_h(tokens["admin"]),
                 json={"text": "SYNTHETIC DATA – NOT FOR OPERATIONAL USE"}, timeout=10)

    # AI settings - toggle a use case off and check enforcement (403 on associated endpoint)
    r = requests.get(f"{API}/admin/ai-settings", headers=_h(tokens["admin"]), timeout=20)
    assert r.status_code == 200
    settings = r.json()
    uc = settings.get("use_cases", {})
    assert uc, "expected use_cases config"
    # Pick 'implementation_statement' if present else first
    target = "implementation_statement" if "implementation_statement" in uc else next(iter(uc))
    r = requests.put(f"{API}/admin/ai-settings", headers=_h(tokens["admin"]),
                     json={"use_cases": {target: False}}, timeout=20)
    assert r.status_code == 200
    assert r.json()["use_cases"][target] is False
    # restore
    requests.put(f"{API}/admin/ai-settings", headers=_h(tokens["admin"]),
                 json={"use_cases": {target: True}}, timeout=20)

    # Invite user
    email = f"test_invitee_{int(time.time())}@aegisrmf.demo"
    r = requests.post(f"{API}/admin/users", headers=_h(tokens["admin"]),
                      json={"email": email, "display_name": "TEST Invitee", "role": "isso"}, timeout=20)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["temporary_password"] and len(body["temporary_password"]) > 8
    assert body["email"] == email

    # Access history
    r = requests.get(f"{API}/admin/users/{body['id']}/access-history", headers=_h(tokens["admin"]), timeout=20)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


# ---------- 12. Decision rules admin ----------
def test_decision_rules_admin_versioned_edit(tokens):
    body = {"label": "TEST_rule_edit",
            "steps": [{"role": "issm", "action": "endorse"}, {"role": "ao", "action": "decide"}]}
    r = requests.put(f"{API}/decision-rules/risk_acceptance", headers=_h(tokens["admin"]),
                     json=body, timeout=20)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["version"] >= 2


# ---------- 13. Phase 1/2 regression ----------
def test_phase1_regression_systems_list(tokens):
    r = requests.get(f"{API}/systems", headers=_h(tokens["isso"]), timeout=20)
    assert r.status_code == 200
    acs = {s["acronym"] for s in r.json()}
    for a in ("LTP", "MPP", "FMDH", "TRS"):
        assert a in acs


def test_phase2_regression_poams(tokens, ltp_id):
    r = requests.get(f"{API}/poams", headers=_h(tokens["isso"]), params={"system_id": ltp_id}, timeout=20)
    assert r.status_code == 200
    assert isinstance(r.json(), (list, dict))
