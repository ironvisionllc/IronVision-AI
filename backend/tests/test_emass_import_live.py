"""Live (public URL) regression tests: eMASS Control Information import + login page whitepaper removal (iteration 18)."""
import io
import os
import zipfile

import pytest
import requests

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE}/api/v1"
XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
pytestmark = pytest.mark.skipif(not BASE, reason="live preview test: set REACT_APP_BACKEND_URL")


def _login():
    r = requests.post(f"{API}/auth/demo-login", json={})
    if r.status_code == 429:  # demo-login rate limit (30/h per IP) – fall back to the demo account password (test_credentials.md)
        r = requests.post(f"{API}/auth/login", json={"email": "demo@ironvision.ai", "password": os.environ.get("DEMO_PASSWORD", "IronVisionDemo!2026")})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def isso():
    return {"Authorization": f"Bearer {_login()}"}


@pytest.fixture(scope="module")
def sca():
    t = _login()
    r = requests.post(f"{API}/sandbox/act-as", json={"role": "sca"}, headers={"Authorization": f"Bearer {t}"})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _ltp():
    r = requests.get(f"{API}/systems", headers={"Authorization": f"Bearer {_login()}"})
    d = r.json()
    d = d.get("items", d) if isinstance(d, dict) else d
    return next(x["id"] for x in d if x.get("acronym") == "LTP")


SID = os.environ.get("EMASS_LIVE_SYSTEM_ID") or (_ltp() if BASE else "")


def _upload(h, name, data):
    return requests.post(f"{API}/systems/{SID}/emass-imports", headers=h, files={"file": (name, data, XLSX)})


@pytest.fixture(scope="module")
def sample(isso):
    r = requests.get(f"{API}/systems/{SID}/emass-imports/sample.xlsx", headers=isso)
    assert r.status_code == 200 and r.content[:2] == b"PK"
    return r.content


# --- public whitepaper/demo files still served ---
@pytest.mark.parametrize("path", ["whitepaper.pdf", "whitepaper.docx", "demo/ironvision_ai_rmf_narration.txt", "demo/ironvision_ai_rmf_captions.srt"])
def test_public_files(path):
    r = requests.get(f"{API}/public/{path}")
    assert r.status_code == 200 and len(r.content) > 50


def test_public_video_head():
    assert requests.head(f"{API}/public/demo/ironvision_ai_rmf_demo.mp4").status_code == 200


# --- upload + report ---
def test_sample_upload_report(isso, sample):
    r = _upload(isso, "SYNTHETIC_sample.xlsx", sample)
    assert r.status_code == 201, r.text
    j = r.json()
    rep = j["report"]
    assert j["status"] == "review" and len(j["sha256"]) == 64
    assert [x["control"] for x in rep["not_in_system"]] == ["ZZ-99"]
    inv = {(x["control"], x["field"]) for x in rep["invalid"]}
    assert ("CM-6", "SLCM Frequency") in inv and ("RA-5", "Residual Risk Level") in inv and ("SI-2", "SLCM Comments") in inv
    assert any(c == "RA-5" and "Completion" in f for c, f in inv)
    assert len(rep["invalid"]) == 4
    assert any(x["control"] == "IA-2(1)" and x["field"] == "Severity" for x in rep["blocked"])
    au2 = requests.get(f"{API}/systems/{SID}/workbench/controls/au-2/emass", headers=isso).json().get("values") or {}
    if not str(au2.get("na_justification") or "").strip():  # shared demo state: a previous apply may already have filled the justification
        # since the per-row status gate (20ff395) a status missing its required field is reported as "not applied – missing …"
        assert any(x["control"] == "AU-2" and "N/A Justification" in x["missing"] for x in rep["status_not_applied"]) or \
            any(x["control"] == "AU-2" and "N/A Justification" in x["issue"] for x in rep["required_issues"])
    assert any(x["control"] == "AC-2" for x in rep["duplicates"])
    pytest.imp_id = j["id"]


def test_decisions_do_not_save_until_apply(isso):
    before = requests.get(f"{API}/systems/{SID}/workbench/controls/ac-2/emass", headers=isso).json()
    r = requests.put(f"{API}/systems/{SID}/emass-imports/{pytest.imp_id}/decisions", headers=isso,
                     json={"decisions": [{"control_id": "ac-2", "field": "*", "decision": "accept"}]})
    assert r.status_code == 200, r.text
    after = requests.get(f"{API}/systems/{SID}/workbench/controls/ac-2/emass", headers=isso).json()
    assert before["values"] == after["values"]
    # invalid field cannot be accepted
    r = requests.put(f"{API}/systems/{SID}/emass-imports/{pytest.imp_id}/decisions", headers=isso,
                     json={"decisions": [{"control_id": "cm-6", "field": "slcm_frequency", "decision": "accept"}]})
    assert r.status_code == 422
    # blocked field cannot be accepted
    r = requests.put(f"{API}/systems/{SID}/emass-imports/{pytest.imp_id}/decisions", headers=isso,
                     json={"decisions": [{"control_id": "ia-2.1", "field": "severity", "decision": "accept"}]})
    assert r.status_code == 422


def test_sca_readonly(sca):
    d = requests.get(f"{API}/systems/{SID}/emass-imports/{pytest.imp_id}", headers=sca)
    assert d.status_code == 200 and d.json()["can_apply"] is False
    assert requests.get(f"{API}/systems/{SID}/emass-imports", headers=sca).json()["can_apply"] is False
    assert requests.put(f"{API}/systems/{SID}/emass-imports/{pytest.imp_id}/decisions", headers=sca, json={"bulk": "reset"}).status_code == 403
    assert requests.post(f"{API}/systems/{SID}/emass-imports/{pytest.imp_id}/apply", headers=sca).status_code == 403
    assert requests.post(f"{API}/systems/{SID}/emass-imports/{pytest.imp_id}/discard", headers=sca).status_code == 403


def test_sca_upload_403(sca, sample):
    assert _upload(sca, "x.xlsx", sample).status_code == 403


def test_apply_and_audit(isso):
    # AU-2 status is blocked by the per-row status gate (N/A without justification): accepting it is refused with the actionable text
    r = requests.put(f"{API}/systems/{SID}/emass-imports/{pytest.imp_id}/decisions", headers=isso,
                     json={"decisions": [{"control_id": "au-2", "field": "implementation_status", "decision": "accept"}]})
    assert r.status_code == 422 and "N/A Justification" in r.text
    r = requests.put(f"{API}/systems/{SID}/emass-imports/{pytest.imp_id}/decisions", headers=isso,
                     json={"decisions": [{"control_id": "at-2", "field": "*", "decision": "reject"}]})
    assert r.status_code == 200, r.text
    imp = r.json()
    ac2 = next(i for i in imp["items"] if i["control_id"] == "ac-2")
    accepted = {k: f["imported"] for k, f in ac2["fields"].items() if f["decision"] == "accept"}
    at2_before = requests.get(f"{API}/systems/{SID}/workbench/controls/at-2/emass", headers=isso).json()
    r = requests.post(f"{API}/systems/{SID}/emass-imports/{pytest.imp_id}/apply", headers=isso)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "applied"
    res = {x["control"]: x for x in j["results"]}
    assert not (res.get("AU-2") or {}).get("applied_status"), "blocked status never applied"
    assert "AT-2" not in res
    ac2_now = requests.get(f"{API}/systems/{SID}/workbench/controls/ac-2/emass", headers=isso).json()
    for k, v in accepted.items():
        if k in ac2_now["values"]:
            assert str(ac2_now["values"][k]) == str(v), (k, ac2_now["values"][k], v)
    at2_after = requests.get(f"{API}/systems/{SID}/workbench/controls/at-2/emass", headers=isso).json()
    assert at2_before["values"] == at2_after["values"]
    rows = requests.get(f"{API}/audit-events", headers=isso, params={"action": "emass.plan_updated", "limit": 50}).json()
    srcs = [((x.get("details") or {}).get("source") or "") for x in rows]
    assert any(s.startswith("eMASS import") and "sha256" in s for s in srcs), srcs[:5]
    # apply again -> 409
    assert requests.post(f"{API}/systems/{SID}/emass-imports/{pytest.imp_id}/apply", headers=isso).status_code == 409
    hist = requests.get(f"{API}/systems/{SID}/emass-imports", headers=isso).json()
    h = next(x for x in hist["items"] if x["id"] == pytest.imp_id)
    assert h["status"] == "applied" and h["counts"]["applied_fields"] == j["counts"]["applied_fields"] >= len(accepted)


def test_discard(isso, sample):
    j = _upload(isso, "SYNTHETIC_discard.xlsx", sample).json()
    r = requests.post(f"{API}/systems/{SID}/emass-imports/{j['id']}/discard", headers=isso)
    assert r.status_code == 200 and r.json()["status"] == "discarded"
    assert requests.post(f"{API}/systems/{SID}/emass-imports/{j['id']}/apply", headers=isso).status_code == 409


def test_round_trip(isso):
    x = requests.get(f"{API}/systems/{SID}/emass/implementation-plan.xlsx", headers=isso)
    assert x.status_code == 200, x.text[:200]
    r = _upload(isso, "roundtrip.xlsx", x.content)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["counts"]["changed_fields"] == 0, [(i["control"], k, f) for i in j["items"] for k, f in i["fields"].items() if f["change"]][:5]
    assert j["counts"]["invalid"] == 0
    assert j["report"]["matched"] == j["detection"]["data_rows"]
    requests.post(f"{API}/systems/{SID}/emass-imports/{j['id']}/discard", headers=isso)


def _zip(entries):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        for n, c in entries.items():
            z.writestr(n, c)
    return b.getvalue()


@pytest.mark.parametrize("name,data", [("evil.txt", b"hello"), ("rand.xlsx", os.urandom(4096)),
                                       ("nowb.xlsx", _zip({"[Content_Types].xml": "<x/>", "foo.txt": "a"})),
                                       ("legacy.xlsx", b"\xd0\xcf\x11\xe0" + b"\0" * 100)])
def test_malicious_rejected(isso, name, data):
    n0 = len(requests.get(f"{API}/systems/{SID}/emass-imports", headers=isso).json()["items"])
    r = _upload(isso, name, data)
    assert r.status_code == 422, r.text
    assert "detail" in r.json()
    assert len(requests.get(f"{API}/systems/{SID}/emass-imports", headers=isso).json()["items"]) == n0
