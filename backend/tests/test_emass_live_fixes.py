"""Live API checks for the two eMASS plan fixes."""
import os
import requests
import pytest

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://aegis-rmf-demo.preview.emergentagent.com").rstrip("/")
SID = None


@pytest.fixture(scope="module")
def token():
    from tests.live_auth import demo_token
    return demo_token(f"{BASE}/api/v1")


@pytest.fixture(scope="module", autouse=True)
def _ltp(token):
    global SID
    systems = requests.get(f"{BASE}/api/v1/systems", headers={"Authorization": f"Bearer {token}"}, timeout=30).json()
    SID = next(x["id"] for x in systems if x["acronym"] == "LTP")  # demo system id changes on every demo reset


@pytest.fixture(scope="module")
def hdr(token):
    return {"Authorization": f"Bearer {token}"}


def test_emass_missing_422_invalid(hdr):
    r = requests.get(f"{BASE}/api/v1/systems/{SID}/workbench/controls",
                     params={"emass_missing": "maybe"}, headers=hdr, timeout=30)
    assert r.status_code == 422, r.text


def test_emass_status_422_invalid(hdr):
    r = requests.get(f"{BASE}/api/v1/systems/{SID}/workbench/controls",
                     params={"emass_status": "Done"}, headers=hdr, timeout=30)
    assert r.status_code == 422, r.text


def _list_ids(r):
    assert r.status_code == 200, r.text
    j = r.json()
    items = j.get("items") if isinstance(j, dict) else j
    return sorted([(it.get("control_id") or it.get("id")) for it in items])


def test_emass_missing_truthy_identical(hdr):
    ids_y = _list_ids(requests.get(f"{BASE}/api/v1/systems/{SID}/workbench/controls",
                                   params={"emass_missing": "yes", "page_size": 500}, headers=hdr, timeout=30))
    ids_t = _list_ids(requests.get(f"{BASE}/api/v1/systems/{SID}/workbench/controls",
                                   params={"emass_missing": "true", "page_size": 500}, headers=hdr, timeout=30))
    ids_1 = _list_ids(requests.get(f"{BASE}/api/v1/systems/{SID}/workbench/controls",
                                   params={"emass_missing": "1", "page_size": 500}, headers=hdr, timeout=30))
    assert ids_y == ids_t == ids_1


def test_emass_missing_falsy_identical(hdr):
    ids_n = _list_ids(requests.get(f"{BASE}/api/v1/systems/{SID}/workbench/controls",
                                   params={"emass_missing": "no", "page_size": 500}, headers=hdr, timeout=30))
    ids_f = _list_ids(requests.get(f"{BASE}/api/v1/systems/{SID}/workbench/controls",
                                   params={"emass_missing": "false", "page_size": 500}, headers=hdr, timeout=30))
    ids_0 = _list_ids(requests.get(f"{BASE}/api/v1/systems/{SID}/workbench/controls",
                                   params={"emass_missing": "0", "page_size": 500}, headers=hdr, timeout=30))
    assert ids_n == ids_f == ids_0


def test_narrative_consistency(hdr):
    # Fetch missing=yes list
    r = requests.get(f"{BASE}/api/v1/systems/{SID}/workbench/controls",
                     params={"emass_missing": "yes", "page_size": 500}, headers=hdr, timeout=30)
    assert r.status_code == 200
    j = r.json()
    items = j.get("items") if isinstance(j, dict) else j
    missing_ids = set((it.get("control_id") or it.get("id")) for it in items)

    # Fetch validation report
    rv = requests.get(f"{BASE}/api/v1/systems/{SID}/emass/implementation-plan/validation",
                      headers=hdr, timeout=30)
    assert rv.status_code == 200, rv.text
    vj = rv.json()
    val_items = vj.get("items") if isinstance(vj, dict) else vj
    # Build map control_id -> missing fields
    val_map = {}
    for v in val_items:
        cid = (v.get("control") or v.get("control_id") or v.get("id") or "").lower()
        fields = v.get("missing") or v.get("missing_required") or v.get("fields") or []
        val_map[cid] = set(fields)

    # Sample controls
    for cid in ["ac-2", "cp-4", "au-2", "ia-2.1", "cm-2"]:
        er = requests.get(f"{BASE}/api/v1/systems/{SID}/workbench/controls/{cid}/emass",
                          headers=hdr, timeout=30)
        if er.status_code != 200:
            continue
        ej = er.json()
        missing_req = set(ej.get("missing_required") or [])
        status = (ej.get("fields") or {}).get("implementationStatus") or ej.get("status")
        in_missing_list = cid in missing_ids
        has_narr_control = "implementation_narrative" in missing_req
        narr_in_validation = any("narrative" in f.lower() or "implementation_narrative" in f.lower()
                                 for f in val_map.get(cid, set()))
        print(f"{cid}: status={status} missing_required={missing_req} "
              f"in_missing_list={in_missing_list} narr_val={narr_in_validation}")
        # Inherited never lists narrative
        if (status or "").lower() == "inherited":
            assert not has_narr_control, f"{cid}: Inherited should not require narrative"
            assert not narr_in_validation, f"{cid}: Inherited in validation includes narrative"
        # Consistency: narrative-in-control-missing_required <-> narrative-in-validation
        assert has_narr_control == narr_in_validation, (
            f"{cid}: control missing_required narrative={has_narr_control} but validation={narr_in_validation}"
        )
        # If any missing fields, control should be in missing list
        if missing_req:
            assert in_missing_list, f"{cid}: has missing fields but not in emass_missing=yes list"
