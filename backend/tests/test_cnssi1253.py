"""CNSSI No. 1253 (29 July 2022) Appendix D NSS baselines: parsed data, hand-verified rows, union selection, application to systems."""
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import ControlAssignment, Implementation, System
from app.services import cnssi1253 as cn
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

NSS = {"baseline_key": "high", "categorization_mode": "cnssi1253", "nss_determination": "yes", "information_types": [{"id": "D.16.3"}],
       "confidentiality_impact": "Moderate", "integrity_impact": "High", "availability_impact": "Low"}


def test_source_and_parsed_counts_per_level():
    d = cn.data()
    assert d["source"]["sha256"] == "d876741dfb78c54cf21e1f8f966475bddb9df0d3fc8e935e5350862c246d1180" and d["source"]["date"] == "2022-07-29"
    assert len(d["rows"]) == 1189 and sum(r["withdrawn"] for r in d["rows"]) == 182 and not d["parse_problems"] and not d["duplicate_ids"]
    assert d["catalog_check"]["not_in_catalog"] == [] and d["catalog_check"]["withdrawn_mismatch"] == []
    assert all(r["pdf_page"] and r["doc_page"].startswith("D-") for r in d["rows"])
    sel = lambda o, lv: sum(1 for r in d["rows"] if not r["withdrawn"] and r["marks"][f"{o}_{lv}"] in ("X", "+"))  # noqa: E731
    assert {f"{o}{lv}": sel(o, lv) for o in "cia" for lv in "lmh"} == {"cl": 273, "cm": 319, "ch": 397, "il": 310, "im": 380, "ih": 474,
                                                                       "al": 147, "am": 202, "ah": 283}
    assert sum(1 for r in d["rows"] if r["privacy_baseline"] in ("X", "+")) == 93
    assert d["legend"]["+"].startswith("Identifies a control needed to protect NSS") and "3.2.1" in d["selection_rule"]["ref"]


# Hand-verified against the PDF (rendered pages): id → (pdf page, doc page, C L/M/H, I L/M/H, A L/M/H, privacy baseline, withdrawn)
HAND = {
    "AC-2(6)": (26, "D-5", "...", "...", "...", "", False), "AC-2(7)": (26, "D-5", "+++", "+++", "...", "", False),
    "AC-2(8)": (26, "D-5", "...", "...", "...", "", False), "AC-2(10)": (26, "D-5", "...", "...", "...", "", True),
    "AC-2(11)": (26, "D-5", "..X", "..X", "..X", "", False), "AC-2(12)": (26, "D-5", "++X", "++X", "...", "", False),
    "AC-2(13)": (26, "D-5", "+XX", "+XX", "...", "", False), "AC-3": (26, "D-5", "XXX", "XXX", "...", "", False),
    "AC-3(1)": (26, "D-5", "...", "...", "...", "", True), "IA-11": (79, "D-58", "XXX", "XXX", "...", "", False),
    "IA-12": (79, "D-58", "+XX", "+XX", "...", "", False), "IA-12(1)": (79, "D-58", "+++", "+++", "...", "", False),
    "IA-12(4)": (79, "D-58", "..X", "..X", "...", "", False), "IA-12(6)": (79, "D-58", "...", "...", "...", "", False),
    "PM-1": (101, "D-80", "...", "...", "...", "+", False), "PM-2": (101, "D-80", "...", "...", "...", "", False),
    "PM-3": (101, "D-80", "...", "...", "...", "X", False), "PM-7(1)": (101, "D-80", "...", "...", "...", "", False),
    "SA-1": (114, "D-93", "XXX", "XXX", "XXX", "X", False), "SA-2": (114, "D-93", "XXX", "XXX", "XXX", "--", False),
    "SA-15": (123, "D-102", "++X", "++X", "++X", "", False), "SC-7(8)": (129, "D-108", "++X", "++X", "...", "", False),
    "SI-3(9)": (147, "D-126", "...", "...", "...", "", True), "SI-3(10)": (147, "D-126", "...", "+++", "...", "", False),
    "SI-4": (147, "D-126", "XXX", "XXX", "XXX", "", False), "SI-4(1)": (147, "D-126", "+++", "+++", "+++", "", False),
    "SI-4(2)": (147, "D-126", ".XX", ".XX", ".XX", "", False), "SI-4(4)": (147, "D-126", "+XX", "+XX", "+XX", "", False),
    "SI-4(6)": (147, "D-126", "...", "...", "...", "", True), "SI-4(22)": (149, "D-128", "+++", "+++", "+++", "", False),
}


@pytest.mark.parametrize("rid", sorted(HAND))
def test_hand_verified_rows(rid):
    page, doc, c, i, a, priv, wd = HAND[rid]
    r = next(x for x in cn.rows() if x["id"] == rid)
    m = r["marks"]
    got = tuple("".join(m[f"{o}_{lv}"] or "." for lv in "lmh") for o in "cia")
    assert (r["pdf_page"], r["doc_page"], *got, r["privacy_baseline"], r["withdrawn"]) == (page, doc, c, i, a, priv, wd)


def test_dash_mark_is_not_selected_and_privacy_implementation_captured():
    r = next(x for x in cn.rows() if x["id"] == "IA-12(5)")
    assert r["marks"]["c_m"] == "--" and r["privacy_implementation"] == "√3" and "ia-12.5" not in cn.selection("H-H-H")["ids"]
    assert next(x for x in cn.rows() if x["id"] == "SI-4")["privacy_implementation"] == "√2,3"


def test_union_selection_llll_mhl_hhh():
    for tri, n, union, parts in (("L-L-L", 394, 357, (273, 310, 147)), ("M-H-L", 559, 525, (319, 474, 147)), ("H-H-H", 607, 573, (397, 474, 283))):
        s = cn.selection(tri)
        assert (len(s["ids"]), s["security_union"], len(s["by"]["c"]), len(s["by"]["i"]), len(s["by"]["a"]), len(s["by"]["privacy"])) == (n, union, *parts, 93)
        assert s["ids"] == s["by"]["c"] | s["by"]["i"] | s["by"]["a"] | s["by"]["privacy"]
    m = cn.selection("M-H-L")
    assert "ac-2.11" in m["ids"] and "ac-2.11" not in m["by"]["c"], "selected through I=H only"
    assert "ac-3.1" not in m["ids"], "withdrawn never selected"
    assert cn.basis("ac-2.12", "M-H-L") == "Selected by CNSSI 1253 Table D-1 (C=M (+ NSS addition), I=H), p. D-5 (PDF p. 26)"


@pytest.fixture(scope="module")
def org(client, signup_on):  # noqa: F811
    t = _signup(client, f"cn-{uuid.uuid4().hex[:6]}@example.com", "CNSSI Org")
    h = auth(t["access_token"])
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])  # noqa: E731
    return {"h": h, "role": role}


def _mk(client, org, **kw):
    r = client.post("/api/v1/systems", json={"name": f"NSS {uuid.uuid4().hex[:4]}", "acronym": f"N{uuid.uuid4().hex[:3]}", **NSS, **kw}, headers=org["h"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_nss_registration_uses_cnssi_baseline_and_counts_reconcile(client, org):
    sid = _mk(client, org)
    sel = client.get(f"/api/v1/systems/{sid}/select", headers=org["h"]).json()
    c = sel["counts"]
    assert sel["cnssi"]["applied"] == "M-H-L" and sel["cnssi"]["proposal"] is None and c["baseline"] == 559 == c["assigned"]
    assert c["cnssi"] == {"trigraph": "M-H-L", "c": 319, "i": 474, "a": 147, "security_union": 525, "privacy_baseline": 93, "union": 559}
    assert c["labels"]["baseline"].startswith("CNSSI 1253 baseline for M-H-L: 559 (C: 319, I: 474, A: 147, union 525")
    assert c["labels"]["reconciliation"].endswith("= 559 assigned")
    assert any("SME review required" in x and "ia-13" in x for x in sel["cnssi"]["sme_review"]), "uncovered catalog controls stay SME"
    wb = client.get(f"/api/v1/systems/{sid}/workbench/controls/ac-2.12", headers=org["h"]).json()["assignment"]
    assert wb["origin_detail"] == "CNSSI 1253 M-H-L" and wb["selection_basis"].startswith("Selected by CNSSI 1253 Table D-1 (C=M")
    assert client.post(f"/api/v1/systems/{sid}/select/baseline", json={"baseline_key": "moderate"}, headers=org["h"]).status_code == 422


def test_fips_systems_unaffected(client, org):
    sid = client.post("/api/v1/systems", json={"name": "FIPS sys", "acronym": f"F{uuid.uuid4().hex[:3]}", "baseline_key": "moderate",
                                               "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=org["h"]).json()["id"]
    sel = client.get(f"/api/v1/systems/{sid}/select", headers=org["h"]).json()
    assert sel["cnssi"] is None and sel["counts"]["cnssi"] is None and sel["counts"]["baseline"] == 287
    assert sel["counts"]["labels"]["baseline"] == "287 in the Moderate baseline (base + enhancements)"


def test_classified_overlay_applies_on_top_of_mhl(client, org):
    sid = _mk(client, org, classified_information="yes")
    before = client.get(f"/api/v1/systems/{sid}/select", headers=org["h"]).json()["counts"]
    r = client.post(f"/api/v1/systems/{sid}/select/overlay", json={"overlay_key": "cnssi-classified", "apply": True}, headers=org["h"])
    assert r.status_code == 200, r.text
    c = r.json()["counts"]
    assert c["baseline"] == before["baseline"] == 559 and (c["overlay_added"] > 0 or c["overlay_removed"] > 0)
    assert c["assigned"] == c["baseline"] + c["overlay_added"] - c["overlay_removed"] - c["tailored_out"] + c["tailored_in"]


def _cat(client, sid, h, c, i, a):
    return client.put(f"/api/v1/systems/{sid}/categorization", json={"mode": "cnssi1253", "nss_determination": "yes", "information_types": [{"id": "D.16.3"}],
                                                                       "cia": {"c": c, "i": i, "a": a}, "rationale": "Trigraph change for test"}, headers=h)


def test_reapproval_recomputes_baseline_as_proposal(client, org):
    sid = _mk(client, org)
    isso, ao = org["role"]("isso"), org["role"]("ao")
    assert _cat(client, sid, isso, "Moderate", "High", "Low").status_code == 200
    cur = client.get(f"/api/v1/systems/{sid}/categorization/records", headers=isso).json()["current"]
    client.post(f"/api/v1/systems/{sid}/categorization/records/{cur['id']}/approve", json={"rationale": "Approved trigraph M-H-L"}, headers=ao)
    tail = client.post(f"/api/v1/systems/{sid}/select/tailor", json={"action": "remove", "control_ids": ["ac-2.12"], "justification": "Not applicable here"}, headers=isso)
    assert tail.status_code == 200
    with SessionLocal() as db:  # control with work that leaves the baseline at L-L-L
        a = db.scalar(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(sid), ControlAssignment.control_id == "ac-2.11"))
        db.add(Implementation(assignment_id=a.id, version=2, narrative="Implemented", implementation_status="implemented", review_status="approved"))
        db.commit()
    assert _cat(client, sid, isso, "Low", "Low", "Low").json()["calculation"]["record_status"] == "pending_reapproval"
    assert client.get(f"/api/v1/systems/{sid}/select", headers=isso).json()["cnssi"]["proposal"] is None, "nothing changes before re-approval"
    cur = client.get(f"/api/v1/systems/{sid}/categorization/records", headers=isso).json()["current"]
    client.post(f"/api/v1/systems/{sid}/categorization/records/{cur['id']}/approve", json={"rationale": "Re-approved at L-L-L"}, headers=ao)
    sel = client.get(f"/api/v1/systems/{sid}/select", headers=isso).json()
    p = sel["cnssi"]["proposal"]
    assert sel["counts"]["cnssi"]["trigraph"] == "M-H-L", "applied baseline unchanged until the proposal is accepted"
    assert p["from"] == "M-H-L" and p["to"] == "L-L-L" and "ac-2.11" in p["keep_with_work"] and "ac-2.11" not in p["remove"]
    assert p["message"].startswith(f"CNSSI 1253 baseline loaded – {len(p['add'])} controls added / {len(p['remove'])} removed")
    assert client.post(f"/api/v1/systems/{sid}/select/cnssi-baseline", json={"to": "M-M-M"}, headers=isso).status_code == 422, "stale proposal"
    r = client.post(f"/api/v1/systems/{sid}/select/cnssi-baseline", json={"to": "L-L-L"}, headers=isso)
    assert r.status_code == 200 and r.json()["applied"] == "L-L-L"
    c = r.json()["counts"]
    assert c["cnssi"]["trigraph"] == "L-L-L" and c["baseline"] == 394
    assert c["assigned"] == c["baseline"] + c["overlay_added"] - c["overlay_removed"] - c["tailored_out"] + c["tailored_in"]
    with SessionLocal() as db:
        asg = {a.control_id: a for a in db.scalars(select(ControlAssignment).where(ControlAssignment.system_id == uuid.UUID(sid)))}
        assert asg["ac-2.11"].origin == "tailored_in", "work kept, never dropped silently"
        assert "ac-2.12" not in asg, "tailored-out stays out"
    assert client.get(f"/api/v1/systems/{sid}/select", headers=isso).json()["cnssi"]["proposal"] is None


def test_existing_nss_system_gets_a_proposal_not_a_silent_change(client, org):
    sid = client.post("/api/v1/systems", json={"name": "Legacy NSS", "acronym": f"L{uuid.uuid4().hex[:3]}", "baseline_key": "high",
                                               "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=org["h"]).json()["id"]
    with SessionLocal() as db:  # an NSS system registered before the tables were loaded (SP 800-53B High provisional baseline)
        s = db.get(System, uuid.UUID(sid))
        s.categorization_mode, s.confidentiality_impact, s.integrity_impact, s.availability_impact = "cnssi1253", "Moderate", "High", "Low"
        db.commit()
        n0 = len(list(db.scalars(select(ControlAssignment.id).where(ControlAssignment.system_id == s.id))))
    sel = client.get(f"/api/v1/systems/{sid}/select", headers=org["h"]).json()
    p = sel["cnssi"]["proposal"]
    assert sel["cnssi"]["applied"] is None and sel["counts"]["assigned"] == n0 == 370 and p["from"] == "NIST SP 800-53B high" and p["to"] == "M-H-L"
    assert p["add"] and p["remove"] and "review" in p["message"]
    r = client.post(f"/api/v1/systems/{sid}/select/cnssi-baseline", json={"to": "M-H-L"}, headers=org["h"]).json()
    assert r["counts"]["baseline"] == 559 == r["counts"]["assigned"] and r["added"] == len(p["add"]) and r["removed"] == len(p["remove"])
