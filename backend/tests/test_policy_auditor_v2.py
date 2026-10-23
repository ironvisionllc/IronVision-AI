"""Policy Auditor fixes A1–A6 and the non-XX-1 extension (B): downgrade suggestions, per-policy coverage, section labels,
top-level values, version supersession, policy-vs-implementation rule, AI quote verification, low-confidence gating, AO block,
tenant isolation and the precision/recall evaluation."""
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import ControlAssignment, Policy, PolicyControlMap, PolicyRequirementCoverage
from app.services import policy_coverage as pc
from app.services import policy_profile as pp
from tests import policy_eval_set as ev
from tests.conftest import auth
from tests.test_policy_coverage import COMPLETE, NO_FREQ, _analyze
from tests.test_sandbox import _signup, signup_on  # noqa: F401
from tests.test_sme_section1 import _docx


def _upload(client, h, sid, lines, title):
    r = client.post("/api/v1/policies", files={"file": (f"{uuid.uuid4().hex[:6]}.docx", _docx(lines))}, data={"title": title, "system_ids": sid}, headers=h)
    assert r.status_code == 201, r.text
    _analyze(r.json()["id"])
    return r.json()["id"]


def _map(pid, cid):
    from app.services import policy_mapping as pm

    with SessionLocal() as db:
        p = db.get(Policy, uuid.UUID(pid))
        m = next((x for x in pm.current(db, p.id) if x.control_id == cid), None)
        if m is None or m.status != "mapped":
            pm.decide(db, p, cid, "mapped", type("A", (), {"id": None, "email": "pytest@example.com"})(), "accepted in test")
        db.commit()


def _set_status(sid, cid, st):
    with SessionLocal() as db:
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(sid), ControlAssignment.control_id == cid))
        a.implementation_status = st
        db.commit()


@pytest.fixture(scope="module")
def ws(client, signup_on):  # noqa: F811
    t = _signup(client, f"pa2-{uuid.uuid4().hex[:6]}@example.com", "PA2 Org")
    h = auth(t["access_token"])
    r = client.post("/api/v1/systems", json={"name": "PA2 System", "acronym": "PA2S", "baseline_key": "moderate", "categorization_mode": "fips199",
                                             "information_types": [{"id": "D.16.3"}]}, headers=h)
    assert r.status_code == 201, r.text
    sid = r.json()["id"]
    full = _upload(client, h, sid, COMPLETE, "RA Full")
    gap = _upload(client, h, sid, NO_FREQ, "RA Gap")
    ia = _upload(client, h, sid, ev.POLICIES["identification"], "IA Standard")
    for pid, cid in ((full, "ra-1"), (gap, "ra-1"), (ia, "ia-5")):
        _map(pid, cid)
    return {"h": h, "sid": sid, "full": full, "gap": gap, "ia": ia}


def _queue(client, ws):
    return client.get("/api/v1/mapping-review", params={"system_id": ws["sid"]}, headers=ws["h"]).json()


def test_a1_gap_policy_downgrades_implemented_control(client, ws):
    _set_status(ws["sid"], "ra-1", "implemented")
    items = [q for q in _queue(client, ws)["queue"] if q["kind"] == "policy_status" and q["control_id"] == "ra-1"]
    assert len(items) == 1, "one decision per control across all current policies"
    q = items[0]
    assert q["policy_id"] == ws["gap"] and q["downgrade"] and q["target"] == "partially_implemented"
    assert q["title"].startswith("RA-1 is Implemented but the latest policy version (v1) is missing") and "suggest Partially Implemented" in q["title"]
    assert "most conservative" in q["reasoning"] and len(q["policies"]) == 2


def test_a1_ao_sees_item_but_cannot_approve(client, ws):
    ao = auth(client.post("/api/v1/sandbox/act-as", json={"role": "ao"}, headers=ws["h"]).json()["access_token"])
    d = client.get("/api/v1/mapping-review", params={"system_id": ws["sid"]}, headers=ao)
    assert d.status_code == 200 and any(q["kind"] == "policy_status" for q in d.json()["queue"])
    q = next(q for q in d.json()["queue"] if q["kind"] == "policy_status")
    r = client.post("/api/v1/mapping-review/decide", json={"system_id": ws["sid"], "action": "approve", "justification": "",
                                                          "items": [{"kind": q["kind"], "ids": q["ids"], "control_id": q["control_id"], "evidence_fp": q["evidence_fp"]}]},
                    headers=ao)
    assert r.status_code == 403
    assert _status_ra1(ws) == "implemented"


def _status_ra1(ws):
    with SessionLocal() as db:
        return db.scalar(select(ControlAssignment.implementation_status).where(ControlAssignment.system_id == uuid.UUID(ws["sid"]), ControlAssignment.control_id == "ra-1"))


def test_a3_policy_filter_uses_only_that_policy(client, ws):
    base = f"/api/v1/systems/{ws['sid']}/ccis"
    gap = client.get(base, params={"policy": ws["gap"], "control": "ra-1"}, headers=ws["h"]).json()
    full = client.get(base, params={"policy": ws["full"], "control": "ra-1"}, headers=ws["h"]).json()
    both = client.get(base, params={"control": "ra-1"}, headers=ws["h"]).json()
    assert full["counts"]["met"] == full["total"] == 21
    assert gap["counts"]["met"] < gap["total"], "the gap policy must not borrow MET from the other policy"
    miss = client.get(base, params={"policy": ws["gap"], "coverage": "missing", "mapped": "true"}, headers=ws["h"]).json()
    part = client.get(base, params={"policy": ws["gap"], "coverage": "partial", "mapped": "yes"}, headers=ws["h"]).json()
    assert miss["total"] + part["total"] > 0
    gap_not_met = {r["cci_id"] for r in gap["items"] if r["coverage"] != "met"}
    assert both["counts"]["met"] == 21 and all(r["matched_by"] in ("RA Full v1", "RA Gap v1") for r in both["items"])
    assert gap_not_met and all(r["matched_by"] == "RA Full v1" for r in both["items"] if r["cci_id"] in gap_not_met), "a gap is filled only by the policy that meets it"
    wb = client.get(f"/api/v1/systems/{ws['sid']}/workbench/controls", params={"policy": ws["gap"], "policy_coverage": "gaps"}, headers=ws["h"]).json()
    wbp = client.get(f"/api/v1/systems/{ws['sid']}/workbench/controls", params={"policy": ws["gap"], "policy_coverage": "partial"}, headers=ws["h"]).json()
    assert "ra-1" in {r["control_id"] for r in wb + wbp}, "Workbench and CCI view agree that RA-1 has gaps in the gap policy"
    met = client.get(f"/api/v1/systems/{ws['sid']}/workbench/controls", params={"policy": ws["full"], "policy_coverage": "met"}, headers=ws["h"]).json()
    assert "ra-1" in {r["control_id"] for r in met}


def test_a4_section_labels(client, ws):
    d = client.get(f"/api/v1/policies/{ws['full']}", headers=ws["h"]).json()
    reqs = next(c for c in d["coverage"] if c["control_id"] == "ra-1")["requirements"]
    locs = [s["location"] for r in reqs for s in (r["snippets"] or []) if s["text"].startswith("Scope") or "applies to all organizational" in s["text"]]
    assert locs and all("§ 2. Scope" in loc for loc in locs), locs
    from app.services.rmf import locate

    t = "1. Purpose. Text.\n2. Scope. This applies to all."
    assert locate(t, t.index("This applies")).endswith("§ 2. Scope")


def test_a5_top_level_values(client, ws):
    d = client.get(f"/api/v1/policies/{ws['full']}", headers=ws["h"]).json()
    vals = [v for v in d["values"] if v["control_id"] == "ra-1"]
    assert any("annually" in (v["policy_value"] or "") for v in vals), d["values"]
    assert any(v["parameter"].startswith("designated official") and v["policy_value"] == "ISSM" for v in vals)


def test_a6_version_supersession(client, ws):
    v2 = _upload(client, ws["h"], ws["sid"], NO_FREQ, "RA Full")
    _map(v2, "ra-1")
    old = client.get(f"/api/v1/policies/{ws['full']}", headers=ws["h"]).json()
    new = client.get(f"/api/v1/policies/{v2}", headers=ws["h"]).json()
    assert old["is_current"] is False and old["superseded_by"]["id"] == v2 and new["is_current"] and new["policy"]["version"] == 2
    rows = client.get(f"/api/v1/systems/{ws['sid']}/ccis", params={"control": "ra-1"}, headers=ws["h"]).json()["items"]
    assert all(ws["full"] not in r["policy_ids"] for r in rows), "superseded version must not contribute coverage"
    q = [x for x in _queue(client, ws)["queue"] if x["kind"] == "policy_status" and x["control_id"] == "ra-1"]
    assert q and q[0]["policy_id"] == v2 and "(v2)" in q[0]["title"]


def test_b_non_xx1_policy_alone_is_never_implemented(client, ws):
    _set_status(ws["sid"], "ia-5", "not_implemented")
    d = client.get(f"/api/v1/policies/{ws['ia']}", headers=ws["h"]).json()
    ia5 = next(c for c in d["coverage"] if c["control_id"] == "ia-5")
    assert any(r["effective"] == "met" for r in ia5["requirements"])
    assert {r["kind"] for r in ia5["requirements"]} >= {"technical"}
    items = [q for q in _queue(client, ws)["queue"] if q["kind"] == "policy_status" and q["control_id"] == "ia-5"]
    assert all(q["target"] != "implemented" for q in items)
    if items:
        assert items[0]["tech_needed"] and "technical evidence" in items[0]["reasoning"].lower()


def _row(status, conf, cid="ia-5", text="authenticators are changed"):
    return PolicyRequirementCoverage(control_id=cid, requirement_id=uuid.uuid4().hex, requirement_type="objective", label="x", text=text,
                                     concept="profile-concept", status=status, confidence=conf, override=None)


def test_b_low_confidence_creates_no_suggestion():
    a = ControlAssignment(control_id="ra-1", implementation_status="not_implemented")
    p = Policy(title="P", version=1)
    v = pc.policy_view(None, a, [_row("partial", "Low", "ra-1"), _row("missing", "Low", "ra-1")], p)
    d = pc.control_decision(None, a, [v])
    assert "target" not in d and d.get("review"), d
    v2 = pc.policy_view(None, a, [_row("met", "High", "ra-1"), _row("partial", "Low", "ra-1")], p)
    assert v2["met"] == 1 and v2["policy_gap"] and v2["low"], "low-confidence rows never count as met"


def test_b_ai_quote_must_be_exact_substring():
    text = "Default passwords are changed prior to first use. Passwords must be long."
    base = {"status": "partial", "confidence": "Medium", "reason": "r", "snippets": [], "needs": "n"}
    bad = pp.apply_ai(text, dict(base), {"status": "met", "quote": "Default passwords are rotated before deployment", "rationale": "x"})
    assert bad["status"] == "partial" and bad["ai_discarded"]
    good = pp.apply_ai(text, dict(base), {"status": "met", "quote": "Default passwords are changed prior to first use.", "rationale": "x"})
    assert good["status"] == "met" and good["basis"] == "ai"
    contra = pp.apply_ai(text, {**base, "status": "met"}, {"status": "missing", "quote": "", "rationale": "not stated"})
    assert contra["status"] == "partial" and contra["confidence"] == "Low"


def test_tenant_isolation_second_org(client, ws, signup_on):  # noqa: F811
    t = _signup(client, f"pa2-other-{uuid.uuid4().hex[:6]}@example.com", "PA2 Other Org")
    h2 = auth(t["access_token"])
    assert client.get(f"/api/v1/systems/{ws['sid']}/ccis", headers=h2).status_code in (403, 404)
    assert client.get(f"/api/v1/policies/{ws['gap']}", headers=h2).status_code == 404
    assert client.get("/api/v1/mapping-review", params={"system_id": ws["sid"]}, headers=h2).status_code in (403, 404)


def evaluate_set(db) -> dict:
    """Deterministic predictions on the synthetic set → per-control and total precision/recall of MET."""
    from app.services.policy_coverage import _sentences, _snip, requirements

    tp = fp = fn = 0
    per = {}
    for key, lines in ev.POLICIES.items():
        text = "\n".join(lines)
        sents = _sentences(text)
        for cid, exp in ev.EXPECTED[key].items():
            objs = [r for r in requirements(db, cid) if r["type"] == "objective"]
            pred = set()
            for r in objs:
                res = pp.evaluate(text, sents, cid, r["text"], lambda h, t=text: _snip(t, h))
                if res and res["status"] == "met":
                    pred.add(r["id"].split("_obj")[1])
            per[cid] = {"expected": sorted(exp), "predicted": sorted(pred), "objectives": len(objs)}
            tp += len(pred & exp)
            fp += len(pred - exp)
            fn += len(exp - pred)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": tp / (tp + fp) if tp + fp else 1.0, "recall": tp / (tp + fn) if tp + fn else 1.0, "per": per}


def test_b_evaluation_precision_recall():
    with SessionLocal() as db:
        r = evaluate_set(db)
    print("EVAL", r)
    assert r["precision"] >= ev.PRECISION_MIN, r
    assert r["recall"] >= ev.RECALL_MIN, r


def test_values_never_from_ids_and_bound_to_their_sentence():
    from app.services.rmf import rule_extract

    for key, exp in ev.VALUES.items():
        text = "\n".join(ev.POLICIES[key])
        got = {(v["control_id"], v["parameter"]): v for v in rule_extract(text, {"ac"}, None)["values"]}
        for k, num in exp.items():
            assert k in got and got[k]["numeric_value"] == num, (k, got.get(k))
            assert not got[k]["quote"].startswith("AC-7 Unsuccessful Logon Attempts.") or str(num) in got[k]["quote"]
    from app.services.policy_coverage import _sentences, _snip
    text = "\n".join(ev.POLICIES["account_management"])
    with SessionLocal() as db:
        from app.services.policy_coverage import requirements
        for r in requirements(db, "ac-2") + requirements(db, "ac-7"):
            res = pp.evaluate(text, _sentences(text), r["id"].split("_")[0].split(".")[0] if r["type"] == "objective" else "ac-2", r["text"], lambda h, t=text: _snip(t, h))
            if res and res.get("value"):
                assert all(v.split()[0] in res["snippets"][0]["text"] for v in res["value"].split("; ")), res


def _decide(client, ws, sid, cid):
    q = next(x for x in client.get("/api/v1/mapping-review", params={"system_id": sid}, headers=ws["h"]).json()["queue"]
             if x["kind"] == "policy_status" and x["control_id"] == cid)
    r = client.post("/api/v1/mapping-review/decide", json={"system_id": sid, "action": "approve", "justification": "",
                                                          "items": [{"kind": q["kind"], "ids": q["ids"], "control_id": cid, "evidence_fp": q["evidence_fp"]}]}, headers=ws["h"])
    assert r.status_code == 200, r.text
    return q


def _open(client, ws, sid):
    return [x for x in client.get("/api/v1/mapping-review", params={"system_id": sid}, headers=ws["h"]).json()["queue"] if not x.get("awaiting_sca")]


def _ps(client, ws, sid, cid):
    return [x for x in client.get("/api/v1/mapping-review", params={"system_id": sid}, headers=ws["h"]).json()["queue"] if x["kind"] == "policy_status" and x["control_id"] == cid]


def test_stability_downgrade_then_upgrade_then_complete_v4(client, ws):
    r = client.post("/api/v1/systems", json={"name": "Stable", "acronym": f"ST{uuid.uuid4().hex[:3]}", "baseline_key": "moderate", "categorization_mode": "fips199",
                                             "information_types": [{"id": "D.16.3"}]}, headers=ws["h"])
    sid = r.json()["id"]
    full = _upload(client, ws["h"], sid, COMPLETE, f"Stab Full {sid[:4]}")
    gap = _upload(client, ws["h"], sid, NO_FREQ, f"Stab Gap {sid[:4]}")
    _map(full, "ra-1"), _map(gap, "ra-1")
    _set_status(sid, "ra-1", "implemented")
    n0 = len(_open(client, ws, sid))
    q = _decide(client, ws, sid, "ra-1")
    assert q["downgrade"]
    for pid in (full, gap):  # recompute from the same inputs (re-analysis after approval) → still nothing to suggest
        _analyze(pid)
    assert _ps(client, ws, sid, "ra-1") == [], "approving the downgrade must not create the opposite suggestion"
    assert len(_open(client, ws, sid)) == n0 - 1, _open(client, ws, sid)
    with SessionLocal() as db:
        assert db.scalar(select(PolicyRequirementCoverage.id).where(PolicyRequirementCoverage.policy_id == uuid.UUID(gap),
                                                                    PolicyRequirementCoverage.status == "met", PolicyRequirementCoverage.linked.isnot(None)).limit(1))
        assert db.scalar(select(PolicyRequirementCoverage.id).where(PolicyRequirementCoverage.policy_id == uuid.UUID(gap), PolicyRequirementCoverage.status != "met").limit(1)), \
            "linking as evidence never turns a policy-text gap into MET"
    v4 = _upload(client, ws["h"], sid, COMPLETE, f"Stab Gap {sid[:4]}")  # genuinely complete new version of the gap policy
    _map(v4, "ra-1")
    up = _ps(client, ws, sid, "ra-1")
    assert len(up) == 1 and up[0]["target"] == "implemented" and up[0]["policy_version"] == 2
    _decide(client, ws, sid, "ra-1")
    _analyze(v4)
    assert _ps(client, ws, sid, "ra-1") == [], "approving the upgrade must not create a new suggestion"


def test_ac2_ac7_policy_gives_partial_with_technical_evidence_needed(client, ws):
    pid = _upload(client, ws["h"], ws["sid"], ev.POLICIES["account_management"], "QA AC Standard")
    _set_status(ws["sid"], "ac-7", "not_implemented")
    d = client.get("/api/v1/mapping-review", params={"system_id": ws["sid"]}, headers=ws["h"]).json()
    ac7 = [q for q in d["queue"] if q["kind"] == "policy_status" and q["control_id"] == "ac-7"]
    assert ac7 and ac7[0]["target"] == "partially_implemented" and ac7[0]["tech_needed"], (ac7, d["status_notes"], d["review_needed"])
    assert "technical evidence needed for" in ac7[0]["title"]
    vals = {(v["control_id"], v["parameter"]): v["policy_value"] for v in client.get(f"/api/v1/policies/{pid}", headers=ws["h"]).json()["values"]}
    assert vals[("ac-7", "unsuccessful_logon_attempts")] == "3 attempts" and vals[("ac-7", "lockout_minutes")] == "30 minutes"
    assert vals[("ac-7", "logon_attempt_window_minutes")] == "15 minutes" and vals[("ac-2.3", "inactivity_disable_days")] == "30 days"


def test_two_different_policies_each_get_mapping_items_and_identical_reupload_is_deduplicated(client, ws):
    a = _upload(client, ws["h"], ws["sid"], ev.POLICIES["account_management"], "AC Copy One")
    b = _upload(client, ws["h"], ws["sid"], ev.POLICIES["account_management"] + ["Owner: IT"], "AC Copy Two")
    q = client.get("/api/v1/mapping-review", params={"system_id": ws["sid"]}, headers=ws["h"]).json()["queue"]
    for pid in (a, b):
        assert any(x["kind"] == "policy_map" and x.get("policy_id", "") == pid or pid in x["ids"] for x in q if x["kind"] == "policy_map"), pid
    from tests.test_sme_section1 import _docx as dx
    data = dx(["Identical policy", "AC-7 The system enforces a limit of 3 consecutive invalid logon attempts."])
    r1 = client.post("/api/v1/policies", files={"file": ("same.docx", data)}, data={"title": "Same Twice", "system_ids": ws["sid"]}, headers=ws["h"]).json()
    r2 = client.post("/api/v1/policies", files={"file": ("same.docx", data)}, data={"title": "Same Twice", "system_ids": ws["sid"]}, headers=ws["h"]).json()
    assert r2["duplicate"] and r2["id"] == r1["id"] and r2["version"] == 1 and "Identical" in r2["message"]


def test_analyzer_version_reprocesses_stale_policy(client, ws):
    with SessionLocal() as db:
        p = db.get(Policy, uuid.UUID(ws["ia"]))
        p.analysis = {**(p.analysis or {}), "coverage_version": "coverage-0"}
        db.commit()
        assert pc.ensure_current(db, [p]) == 1
        db.commit()
        assert pc.ensure_current(db, [db.get(Policy, uuid.UUID(ws["ia"]))]) == 0
        n = db.scalar(select(PolicyControlMap.id).where(PolicyControlMap.policy_id == p.id).limit(1))
        assert n is not None


def test_polish_value_locations_use_control_id_headings():
    from app.services.rmf import locate, rule_extract

    text = ("Access Control Policy\n1. Purpose. This policy sets access rules.\n"
            "AC-2(3) Disable Accounts. Inactive accounts are disabled within 35 days of inactivity.\n"
            "AC-7 Unsuccessful Logon Attempts. The system enforces a limit of 4 consecutive invalid logon attempts within 12 minutes "
            "and locks the account for 25 minutes.")
    vals = {(v["control_id"], v["parameter"]): v for v in rule_extract(text, {"ac"}, None)["values"]}
    for k in [("ac-7", "unsuccessful_logon_attempts"), ("ac-7", "logon_attempt_window_minutes"), ("ac-7", "lockout_minutes")]:
        assert vals[k]["location"].endswith("§ AC-7 Unsuccessful Logon Attempts"), vals[k]
    assert vals[("ac-2.3", "inactivity_disable_days")]["location"].endswith("§ AC-2(3) Disable Accounts")
    assert vals[("ac-7", "unsuccessful_logon_attempts")]["numeric_value"] == 4
    assert locate(text, text.index("This policy sets")).endswith("§ 1. Purpose")


def test_polish_proposed_mapping_note_and_also_approved_audit(client, ws):
    r = client.post("/api/v1/systems", json={"name": "Polish", "acronym": f"PL{uuid.uuid4().hex[:3]}", "baseline_key": "moderate", "categorization_mode": "fips199",
                                             "information_types": [{"id": "D.16.3"}]}, headers=ws["h"])
    sid = r.json()["id"]
    pid = _upload(client, ws["h"], sid, ev.POLICIES["account_management"], f"Polish AC {sid[:4]}")
    _set_status(sid, "ac-7", "not_implemented")
    q = next(x for x in _ps(client, ws, sid, "ac-7"))
    from app.services import policy_mapping as pm
    with SessionLocal() as db:
        m = next(x for x in pm.current(db, uuid.UUID(pid)) if x.control_id == "ac-7")
        assert m.status == "proposed" and m.confidence in ("High", "Medium")
        map_id = str(m.id)
    assert q["mapping_note"].startswith(f"Based on a proposed {m.confidence}-confidence mapping – approving this also approves the AC-7 mapping")
    qall = client.get("/api/v1/mapping-review", params={"system_id": sid}, headers=ws["h"]).json()["queue"]
    assert any(x["kind"] == "policy_map" and x["control_id"] == "ac-7" for x in qall)
    d = client.post("/api/v1/mapping-review/decide", json={"system_id": sid, "action": "approve", "justification": "",
                                                          "items": [{"kind": q["kind"], "ids": q["ids"], "control_id": "ac-7", "evidence_fp": q["evidence_fp"]}]}, headers=ws["h"])
    assert d.status_code == 200 and d.json()["also_approved"] == [f"AC-7 mapping from “Polish AC {sid[:4]}” v1"], d.json()
    from app.models import AuditEvent as AuditLog
    with SessionLocal() as db:
        ev_ = list(db.scalars(select(AuditLog).where(AuditLog.entity_id == map_id, AuditLog.action == "policy.mapping_approved_with_status")))
        assert len(ev_) == 1 and ev_[0].after["status"] == "mapped"
    qall = client.get("/api/v1/mapping-review", params={"system_id": sid}, headers=ws["h"]).json()["queue"]
    assert not any(x["kind"] == "policy_map" and x["control_id"] == "ac-7" for x in qall)
