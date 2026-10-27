import re
"""CCI-level Policy Auditor: requirement coverage (DISA CCIs + 800-53A objectives) → MET/PARTIAL/MISSING with snippets,
status suggestions in Mapping Review (never auto-applied), approval links CCIs + audit, gap actions, policy filters and the CCI view."""
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent, CciControlMap, ControlAssignment
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401
from tests.test_sme_section1 import _docx

COMPLETE = [
    "Risk Assessment Policy (synthetic)",
    "1. Purpose. This policy establishes the purpose of risk assessment for the organization and implements RA-1.",
    "2. Scope. This policy applies to all organizational systems, personnel and contractors.",
    "3. Roles and responsibilities. System owners are accountable for risk assessments and ISSOs perform them.",
    "4. Management commitment. Senior leadership affirms management commitment to managing risk.",
    "5. Coordination and compliance. Coordination among organizational entities is required, and compliance is monitored by the ISSM.",
    "6. This policy is consistent with applicable laws, executive orders, directives, regulations, policies, standards, and guidelines.",
    "7. This risk assessment policy is disseminated to all system owners, ISSOs and the ISSM via the policy portal.",
    "8. Risk assessment procedures are developed and documented to facilitate the implementation of this policy and the associated risk assessment controls.",
    "9. The risk assessment procedures are disseminated to all ISSOs, system administrators and assessors.",
    "10. The ISSM is designated as the official to manage the development, documentation, and dissemination of the risk assessment policy and procedures.",
    "11. The ISSM reviews and updates this risk assessment policy at least annually and following significant changes, security incidents or assessment findings.",
    "12. The risk assessment procedures are reviewed and updated at least annually and following significant changes or security incidents.",
]
NO_FREQ = [ln.replace(" at least annually and", "") for ln in COMPLETE]
UNRELATED = ["Cafeteria Menu Guidelines", "Lunch is served daily from noon. Vegetarian options are available on request.",
             "Please return trays to the counter. Coffee refills are free."]


def _analyze(pid):
    from worker.handlers import handle_policy_analyze

    with SessionLocal() as db:
        handle_policy_analyze(db, {"policy_id": pid})
        db.commit()


@pytest.fixture(scope="module")
def ws(client, signup_on):  # noqa: F811
    t = _signup(client, f"cci-{uuid.uuid4().hex[:6]}@example.com", "CCI Org")
    h = auth(t["access_token"])
    sids = []
    for name, acr in (("CCI System", "CCIS"), ("CCI System Two", "CCI2")):
        r = client.post("/api/v1/systems", json={"name": name, "acronym": acr, "baseline_key": "moderate", "categorization_mode": "fips199",
                                                 "information_types": [{"id": "D.16.3"}]}, headers=h)
        assert r.status_code == 201, r.text
        sids.append(r.json()["id"])
    pids = {}
    for key, lines, sid in (("complete", COMPLETE, sids[0]), ("nofreq", NO_FREQ, sids[1]), ("unrelated", UNRELATED, sids[1])):
        r = client.post("/api/v1/policies", files={"file": (f"{key}.docx", _docx(lines))}, data={"title": f"RA {key}", "system_ids": sid}, headers=h)
        assert r.status_code == 201, r.text
        pids[key] = r.json()["id"]
        _analyze(pids[key])
    return {"h": h, "sid": sids[0], "sid2": sids[1], "p": pids}


def _status(sid, cid="ra-1"):
    with SessionLocal() as db:
        return db.scalar(select(ControlAssignment.implementation_status).where(ControlAssignment.system_id == uuid.UUID(sid), ControlAssignment.control_id == cid))


def _cov(client, ws, key, cid="ra-1"):
    d = client.get(f"/api/v1/policies/{ws['p'][key]}", headers=ws["h"]).json()
    return next((c for c in d["coverage"] if c["control_id"] == cid), None)


def _queue(client, ws, sid):
    return client.get("/api/v1/mapping-review", params={"system_id": sid}, headers=ws["h"]).json()["queue"]


def test_requirements_are_the_reference_ccis_and_objectives_all_met(client, ws):
    c = _cov(client, ws, "complete")
    with SessionLocal() as db:
        ref = set(db.scalars(select(CciControlMap.cci_id).where(CciControlMap.control_id == "ra-1", CciControlMap.version == "5")))
    got = {r["requirement_id"] for r in c["requirements"] if r["requirement_type"] == "cci"}
    assert got == ref and len(ref) == 21
    assert c["summary"]["objectives"] >= 15 and any(r["label"] == "RA-01c.02[01]" for r in c["requirements"])
    bad = [(r["label"], r["status"], r["reason"]) for r in c["requirements"] if r["status"] != "met"]
    assert not bad, bad
    assert c["summary"]["state"] == "met" and c["line"].startswith(f"RA-1 (base control only, enhancements counted separately): {c['summary']['total']} of {c['summary']['total']} requirements met")
    r = next(r for r in c["requirements"] if r["requirement_id"] == "CCI-001040")
    assert r["parameter_value"] == "at least annually" and r["snippets"][0]["location"].startswith("p. 1")
    rec = next(r for r in c["requirements"] if r["requirement_id"] == "CCI-002368")
    assert "system owners" in rec["parameter_value"]


def test_complete_policy_suggests_implemented_but_never_auto_applies(client, ws):
    assert _status(ws["sid"]) != "implemented"
    q = [i for i in _queue(client, ws, ws["sid"]) if i["kind"] == "policy_status" and i["control_id"] == "ra-1"]
    assert len(q) == 1 and q[0]["target"] == "implemented" and "requirements met" in q[0]["title"] and "Implemented" in q[0]["title"]
    assert _status(ws["sid"]) != "implemented"


def test_filters_counts_and_cci_view_match_lists(client, ws):
    url = f"/api/v1/systems/{ws['sid']}/workbench/controls"
    f = client.get(f"/api/v1/systems/{ws['sid']}/workbench/policy-facets", headers=ws["h"]).json()
    for facet, vals in (("policy_mapping", ("mapped", "not_mapped", "proposed")), ("policy_coverage", ("met", "partial", "gaps"))):
        for v in vals:
            assert len(client.get(url, params={facet: v}, headers=ws["h"]).json()) == f[facet][v], (facet, v)
    assert "ra-1" in {r["control_id"] for r in client.get(url, params={"policy": ws["p"]["complete"], "policy_coverage": "met"}, headers=ws["h"]).json()}
    pol = next(p for p in f["policy"] if p["id"] == ws["p"]["complete"])
    assert pol["count"] == len(client.get(url, params={"policy": ws["p"]["complete"]}, headers=ws["h"]).json())
    assert len(client.get(url, params={"policy_mapping": "proposed", "has_evidence": "no"}, headers=ws["h"]).json()) <= f["policy_mapping"]["proposed"]
    cc = client.get(f"/api/v1/systems/{ws['sid']}/ccis", params={"control": "ra-1", "mapped": "yes"}, headers=ws["h"]).json()
    assert cc["total"] == 21 == len(cc["items"]) and all(i["coverage"] == "met" and i["definition"] for i in cc["items"])
    unm = client.get(f"/api/v1/systems/{ws['sid']}/ccis", params={"mapped": "no", "family": "ac"}, headers=ws["h"]).json()
    assert unm["total"] == len(unm["items"]) > 0 and not any(i["mapped"] for i in unm["items"])
    csv = client.get(f"/api/v1/systems/{ws['sid']}/ccis", params={"control": "ra-1", "mapped": "yes", "fmt": "csv"}, headers=ws["h"])
    assert csv.text.splitlines()[0].startswith("cci_id,control_id") and len(csv.text.splitlines()) == 22
    tr = client.get(f"/api/v1/systems/{ws['sid']}/traceability", params={"policy": ws["p"]["complete"]}, headers=ws["h"]).json()
    assert tr and all(r["policies"] for r in tr) and next(r for r in tr if r["control_id"] == "ra-1")["ccis"] == {"total": 21, "met": 21}


def test_approval_updates_status_links_ccis_audits_and_filters_update(client, ws):
    item = next(i for i in _queue(client, ws, ws["sid"]) if i["kind"] == "policy_status" and i["control_id"] == "ra-1")
    with SessionLocal() as db:
        seq0 = db.query(AuditEvent.seq).order_by(AuditEvent.seq.desc()).limit(1).scalar() or 0
    r = client.post("/api/v1/mapping-review/decide", headers=ws["h"], json={"system_id": ws["sid"], "action": "approve", "justification": "Coverage reviewed",
                                                                           "items": [{k: item[k] for k in ("kind", "ids", "control_id", "evidence_fp")}]})
    assert r.status_code == 200, r.text
    assert _status(ws["sid"]) == "implemented"
    c = _cov(client, ws, "complete")
    assert all(x["linked"] and x["linked"]["system_id"] == ws["sid"] and x["linked"]["by"] for x in c["requirements"])
    with SessionLocal() as db:
        acts = [a for a, in db.query(AuditEvent.action).filter(AuditEvent.seq > seq0)]
    assert "control.policy_coverage_status_approved" in acts and "mapping_review.item_approved" in acts
    assert not [i for i in _queue(client, ws, ws["sid"]) if i["kind"] == "policy_status" and i["control_id"] == "ra-1"]
    mapped = client.get(f"/api/v1/systems/{ws['sid']}/workbench/controls", params={"policy_mapping": "mapped"}, headers=ws["h"]).json()
    assert "ra-1" in {x["control_id"] for x in mapped}
    wb = client.get(f"/api/v1/systems/{ws['sid']}/workbench/controls/ra-1", headers=ws["h"]).json()
    assert wb["policy_coverage"] and wb["policy_coverage"][0]["summary"]["state"] == "met"


def test_missing_frequency_suggests_partial_with_gap_named_and_reject_needs_reason(client, ws):
    c = _cov(client, ws, "nofreq")
    freq = [r for r in c["requirements"] if r["requirement_id"] in ("CCI-001040", "CCI-001044")]
    assert freq and all(r["status"] != "met" and "annually" in r["needs"] for r in freq)
    q = [i for i in _queue(client, ws, ws["sid2"]) if i["kind"] == "policy_status" and i["policy_id"] == ws["p"]["nofreq"]]
    assert len(q) == 1 and q[0]["target"] == "partially_implemented"
    assert re.search(r"No review and update frequency is stated for the [A-Z]{2} procedures\.", q[0]["title"]) \
        and re.search(r"No review and update frequency is stated for the [A-Z]{2} policy\.", q[0]["title"])  # complete sentences, not fragments
    body = {"system_id": ws["sid2"], "action": "reject", "justification": "", "items": [{k: q[0][k] for k in ("kind", "ids", "control_id", "evidence_fp")}]}
    assert client.post("/api/v1/mapping-review/decide", headers=ws["h"], json=body).status_code == 422
    body["justification"] = "Procedures are reviewed under the CM plan"
    assert client.post("/api/v1/mapping-review/decide", headers=ws["h"], json=body).status_code == 200
    assert not [i for i in _queue(client, ws, ws["sid2"]) if i["kind"] == "policy_status" and i["policy_id"] == ws["p"]["nofreq"]]
    assert _status(ws["sid2"]) != "partially_implemented"


def test_unrelated_policy_gets_no_ra_suggestions(client, ws):
    assert _cov(client, ws, "unrelated") is None
    assert not [i for i in _queue(client, ws, ws["sid2"]) if i["kind"] == "policy_status" and i["policy_id"] == ws["p"]["unrelated"]]


def test_gap_actions_covered_elsewhere_and_poam(client, ws):
    c = _cov(client, ws, "nofreq")
    gap = next(r for r in c["requirements"] if r["requirement_id"] == "CCI-001044")
    base = f"/api/v1/policies/{ws['p']['nofreq']}/coverage/{gap['id']}"
    assert client.post(f"{base}/covered-elsewhere", json={"reason": "short"}, headers=ws["h"]).status_code == 422
    d = client.post(f"{base}/covered-elsewhere", json={"reason": "Covered by the CM procedures review"}, headers=ws["h"]).json()
    assert d["covered_elsewhere"] and d["effective"] != "met", "covered elsewhere never turns a policy-text gap into MET"
    row = next(r for r in _cov(client, ws, "nofreq")["requirements"] if r["id"] == gap["id"])
    assert row["effective"] != "met" and row["override"]["reason"]
    other = next(r for r in c["requirements"] if r["requirement_id"] == "CCI-001040")
    p = client.post(f"/api/v1/policies/{ws['p']['nofreq']}/coverage/{other['id']}/poam", json={"system_id": ws["sid2"]}, headers=ws["h"])
    assert p.status_code == 201, p.text
    d = client.get(f"/api/v1/poams/{p.json()['poam_id']}", headers=ws["h"]).json()
    assert "CCI-001040" in str(d) and "ra-1" in str(d).lower()


def test_tenant_isolation(client, ws, token):  # noqa: F811
    o = auth(token("isso@aegisrmf.demo"))
    pid = ws["p"]["complete"]
    c = _cov(client, ws, "complete")
    assert client.get(f"/api/v1/policies/{pid}", headers=o).status_code in (403, 404)
    assert client.post(f"/api/v1/policies/{pid}/coverage/{c['requirements'][0]['id']}/covered-elsewhere", json={"reason": "cross tenant attempt"}, headers=o).status_code in (403, 404)
    assert client.get(f"/api/v1/systems/{ws['sid']}/ccis", headers=o).status_code in (403, 404)
    assert client.get(f"/api/v1/systems/{ws['sid']}/workbench/policy-facets", headers=o).status_code in (403, 404)
