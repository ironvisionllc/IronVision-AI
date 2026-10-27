# Live: already-decided items are reported as skipped (decide endpoint + bulk job race)
import os

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/") + "/api/v1"
pytestmark = pytest.mark.skipif(not os.environ.get("REACT_APP_BACKEND_URL"), reason="live only")


def test_redecide_finding_map_is_skipped():
    tok = requests.post(f"{BASE}/auth/demo-login", timeout=30).json()["access_token"]
    h = {"Authorization": f"Bearer {tok}"}
    s = requests.get(f"{BASE}/systems", headers=h, timeout=30).json()
    sid = next(x["id"] for x in (s if isinstance(s, list) else s["items"]) if x["acronym"] == "LTP")
    q = requests.get(f"{BASE}/mapping-review", params={"system_id": sid}, headers=h, timeout=60).json()["queue"]
    fm = [x for x in q if x["kind"] == "finding_map"]
    if not fm:
        pytest.skip("no finding_map items")
    it = {"kind": "finding_map", "ids": fm[0]["ids"], "control_id": fm[0]["control_id"]}
    r1 = requests.post(f"{BASE}/mapping-review/decide", headers=h, timeout=60, json={"system_id": sid, "action": "approve", "items": [it]})
    assert r1.status_code == 200 and r1.json()["approved"] == 1, r1.text
    r2 = requests.post(f"{BASE}/mapping-review/decide", headers=h, timeout=60, json={"system_id": sid, "action": "approve", "items": [it]})
    assert r2.status_code == 200, r2.text
    print(r2.json())
    assert r2.json()["approved"] == 0 and len(r2.json()["skipped"]) == 1
    q2 = requests.get(f"{BASE}/mapping-review", params={"system_id": sid}, headers=h, timeout=60).json()["queue"]
    assert fm[0]["key"] not in {x["key"] for x in q2}
