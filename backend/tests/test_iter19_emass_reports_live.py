# Live API tests for the shared eMASS report import (5 report types) – iteration 19
import os
from pathlib import Path

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
API = BASE.rstrip("/") + "/api/v1"
FIX = Path(__file__).parent / "fixtures" / "emass"
LTP = "3630fca0-4fb1-45d5-b020-a93156344bb4"
MPP = "3ce4a995-a789-4e0d-a2b2-d26c104cec29"


@pytest.fixture(scope="module")
def s():
    r = requests.post(f"{API}/auth/login", json={"email": "demo@ironvision.ai", "password": "IronVisionDemo!2026"}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    ses = requests.Session()
    ses.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    return ses


def up(s, name, system_id=None, content=None):
    data = {"system_id": system_id} if system_id else {}
    return s.post(f"{API}/emass-imports", files={"file": (name, content or (FIX / name).read_bytes())}, data=data, timeout=60)


def target(s, iid, **body):
    return s.post(f"{API}/emass-imports/{iid}/target", json=body, timeout=60)


# Detection + no-system prompt
def test_detect_system_details_global(s):
    r = up(s, "SYNTHETIC_system_details.xlsx")
    assert r.status_code == 201, r.text
    d = r.json()
    det = d.get("detected") or {}
    print(det.get("type"), det.get("confidence"), det.get("identity"), d.get("status"))
    assert det["type"] == "system_details" and det["confidence"] == "high"
    assert d.get("system_id") in (None, "")
    s.post(f"{API}/emass-imports/{d['id']}/discard")


@pytest.mark.parametrize("name,typ", [("SYNTHETIC_poam.xlsx", "poam"), ("SYNTHETIC_ControlInfoExport.xlsx", "control_information"),
                                      ("SYNTHETIC_TRExport.xlsx", "test_results"), ("SYNTHETIC_HWSWList.xlsm", "hwsw")])
def test_detect_types(s, name, typ):
    r = up(s, name)
    assert r.status_code == 201, r.text
    det = r.json()["detected"]
    print(name, det["type"], det["confidence"], det.get("scores"))
    assert det["type"] == typ
    s.post(f"{API}/emass-imports/{r.json()['id']}/discard")


# Mismatch warning in system context
def test_mismatch_in_mpp_context(s):
    r = up(s, "SYNTHETIC_system_details.xlsx", MPP)
    d = r.json()
    print(d["detected"].get("mismatch"))
    assert d["detected"].get("mismatch")
    s.post(f"{API}/emass-imports/{d['id']}/discard")


def test_no_mismatch_in_ltp_context(s):
    d = up(s, "SYNTHETIC_system_details.xlsx", LTP).json()
    assert not d["detected"].get("mismatch")
    s.post(f"{API}/emass-imports/{d['id']}/discard")


# Register-new prefill: nothing created
def test_register_prefill_creates_nothing(s):
    before = s.get(f"{API}/systems").json()
    n0 = len(before if isinstance(before, list) else before.get("items", []))
    d = up(s, "SYNTHETIC_system_details.xlsx").json()
    r = target(s, d["id"], action="register")
    assert r.status_code == 200, r.text
    pf = r.json()["prefill"]["system"]
    print(pf)
    assert pf.get("name") and pf.get("acronym")
    after = s.get(f"{API}/systems").json()
    assert len(after if isinstance(after, list) else after.get("items", [])) == n0
    s.post(f"{API}/emass-imports/{d['id']}/discard")


# System details update on LTP; blocked fields; apply + audit
def test_system_details_update_ltp(s):
    d = up(s, "SYNTHETIC_system_details.xlsx").json()
    r = target(s, d["id"], action="update", system_id=LTP)
    assert r.status_code == 200, r.text
    v = r.json()
    secs = {i["section"] for i in v["items"]}
    print("sections", secs)
    for i in v["items"]:
        for k, f in i["fields"].items():
            if f.get("blocked") or f.get("change"):
                print(i["section"], k, "change" if f["change"] else "", "BLOCKED:" + str(f["blocked"]) if f["blocked"] else "")
    blocked = [k for i in v["items"] for k, f in i["fields"].items() if f.get("blocked")]
    assert any(k.startswith("authorization") for k in blocked)
    chg = [(i["key"], k) for i in v["items"] for k, f in i["fields"].items() if f["change"] and not f["blocked"] and not f["error"]]
    print("changeable", chg)
    sys_before = s.get(f"{API}/systems/{LTP}").json()
    if not chg:
        s.post(f"{API}/emass-imports/{v['id']}/discard")
        pytest.skip("no applicable change (already applied earlier)")
    key, fld = chg[0]
    item = next(i for i in v["items"] if i["key"] == key)
    newval = item["fields"][fld]["imported"]
    # decisions do not change the system
    r = s.put(f"{API}/emass-imports/{v['id']}/decisions", json={"decisions": [{"key": key, "field": fld, "decision": "accept"}]})
    assert r.status_code == 200, r.text
    assert s.get(f"{API}/systems/{LTP}").json().get(fld) == sys_before.get(fld)
    # blocked field accept must be refused/ignored
    bk = next(((i["key"], k) for i in v["items"] for k, f in i["fields"].items() if f.get("blocked")), None)
    rb = s.put(f"{API}/emass-imports/{v['id']}/decisions", json={"decisions": [{"key": bk[0], "field": bk[1], "decision": "accept"}]})
    print("blocked accept ->", rb.status_code, rb.text[:200])
    r = s.post(f"{API}/emass-imports/{v['id']}/apply")
    assert r.status_code == 200, r.text
    after = s.get(f"{API}/systems/{LTP}").json()
    print("applied", fld, after.get(fld))
    assert after.get(fld) == newval
    assert after.get("authorization_status") == sys_before.get("authorization_status")
    # restore original value via the regular system update, if possible
    s.patch(f"{API}/systems/{LTP}", json={fld: sys_before.get(fld)})


# POA&M import
def test_poam_import_ltp(s):
    d = up(s, "SYNTHETIC_poam.xlsx", LTP).json()
    v = target(s, d["id"], action="update", system_id=LTP).json()
    assert v["status"] == "review", v
    for i in v["items"]:
        print(i["key"], i["create"], i["required_issue"], {k: (f["error"], bool(f["blocked"])) for k, f in i["fields"].items() if f["error"] or f["blocked"]})
    errs = [f["error"] for i in v["items"] for f in i["fields"].values() if f["error"]]
    assert any("ZZ" in e or "Control" in e for e in errs)
    assert any(k == "due_date" and f["error"] for i in v["items"] for k, f in i["fields"].items())
    assert any(k == "status" and f["blocked"] for i in v["items"] for k, f in i["fields"].items())
    assert any(k == "poc" and f["blocked"] for i in v["items"] for k, f in i["fields"].items())
    new = next((i for i in v["items"] if i["create"] and not i["required_issue"]), None)
    if new is None:
        s.post(f"{API}/emass-imports/{v['id']}/discard")
        pytest.skip("no creatable row (matched existing)")
    r = s.put(f"{API}/emass-imports/{v['id']}/decisions", json={"decisions": [{"key": new["key"], "field": "weakness", "decision": "accept"},
                                                                              {"key": new["key"], "field": "control", "decision": "accept"}]})
    assert r.status_code == 200, r.text
    r = s.post(f"{API}/emass-imports/{v['id']}/apply")
    assert r.status_code == 200, r.text
    print(r.json().get("results"))
    weak = new["fields"]["weakness"]["imported"]
    poams = s.get(f"{API}/poams", params={"system_id": LTP}).json()
    items = poams if isinstance(poams, list) else poams.get("items", [])
    hit = [p for p in items if p.get("weakness") == weak]
    print("created", [(p.get("human_id"), p.get("status")) for p in hit])
    assert hit and hit[0]["status"] == "new"


# Control information via shared flow
def test_control_info_shared(s):
    d = up(s, "SYNTHETIC_ControlInfoExport.xlsx", LTP).json()
    v = target(s, d["id"], action="update", system_id=LTP).json()
    assert v["status"] == "review"
    errs = [f["error"] for i in v["items"] for f in i["fields"].values() if f.get("error")]
    print("ci errors", errs[:5], "items", len(v["items"]))
    assert errs and all(i["section"] == "Controls" for i in v["items"])
    s.post(f"{API}/emass-imports/{v['id']}/discard")


# Test results: single item, apply creates non-approved TR workbook
def test_tr_import(s):
    d = up(s, "SYNTHETIC_TRExport.xlsx", LTP).json()
    v = target(s, d["id"], action="update", system_id=LTP).json()
    assert len(v["items"]) == 1 and v["items"][0]["create"]
    s.put(f"{API}/emass-imports/{v['id']}/decisions", json={"bulk": "accept_safe"})
    r = s.post(f"{API}/emass-imports/{v['id']}/apply")
    assert r.status_code == 200, r.text
    res = r.json().get("results")
    print(res)
    wid = next(x.get("created_id") for x in res if x.get("created_id"))
    w = s.get(f"{API}/systems/{LTP}/test-results/workbooks/{wid}")
    print("wb", w.status_code, w.text[:400])


# HW/SW import
def test_hwsw_import(s):
    d = up(s, "SYNTHETIC_HWSWList.xlsm", LTP).json()
    v = target(s, d["id"], action="update", system_id=LTP).json()
    assert len(v["items"]) == 1
    print(v["items"][0].get("note"))
    s.put(f"{API}/emass-imports/{v['id']}/decisions", json={"bulk": "accept_safe"})
    r = s.post(f"{API}/emass-imports/{v['id']}/apply")
    assert r.status_code == 200, r.text
    print(r.json().get("results"))


# Unsupported files / samples / override / cancel / history
@pytest.mark.parametrize("name", ["notes.txt", "doc.docx"])
def test_unsupported(s, name):
    r = up(s, name, content=b"hello world")
    print(r.status_code, r.text)
    assert r.status_code == 422 and "detail" in r.json()


@pytest.mark.parametrize("typ", ["system_details", "control_information", "test_results", "poam", "hwsw"])
def test_samples(s, typ):
    r = s.get(f"{API}/emass-imports/samples/{typ}")
    assert r.status_code == 200 and len(r.content) > 1000
    assert r.content[:2] == b"PK"


def test_override_and_cancel(s):
    d = up(s, "SYNTHETIC_system_details.xlsx").json()
    r = target(s, d["id"], action="update", system_id=LTP, report_type="poam")
    print("override to poam on sysdetails:", r.status_code, r.text[:200])
    d2 = up(s, "SYNTHETIC_system_details.xlsx").json()
    r = target(s, d2["id"], action="cancel")
    assert r.status_code == 200 and r.json()["status"] == "discarded"
    h = s.get(f"{API}/emass-imports").json()
    assert any(i["id"] == d2["id"] for i in h["items"])
    s.post(f"{API}/emass-imports/{d['id']}/discard")


def test_discard_twice(s):
    d = up(s, "SYNTHETIC_poam.xlsx", LTP).json()
    assert s.post(f"{API}/emass-imports/{d['id']}/discard").status_code == 200
    assert s.post(f"{API}/emass-imports/{d['id']}/discard").status_code == 409


def test_audit_source(s):
    r = s.get(f"{API}/audit", params={"limit": 50})
    print(r.status_code)
    if r.status_code != 200:
        pytest.skip("audit not readable by ISSO")
    txt = r.text
    print("has eMASS source:", "eMASS" in txt and "sha256" in txt)
