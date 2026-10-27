"""Catalog tree redesign is presentation only: the catalog API output (counts and per-control data) must stay identical.
Snapshot: tests/fixtures/catalog_api_snapshot.json (regenerate only on a deliberate catalog content change: UPDATE_CATALOG_SNAPSHOT=1)."""
import hashlib
import json
import os
import uuid
from pathlib import Path

from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

SNAP = Path(__file__).parent / "fixtures" / "catalog_api_snapshot.json"
DETAIL = ["ac-1", "ac-2", "ac-2.1", "ac-17", "au-2", "cm-6", "ia-2.1", "ir-4", "ra-5", "sc-7", "si-4", "sr-3", "ac-2.10", "sc-7.5"]


def _digest(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def test_catalog_api_output_unchanged(client, signup_on):  # noqa: F811
    t = _signup(client, f"cat-{uuid.uuid4().hex[:6]}@example.com", "Catalog snapshot Org")
    h = auth(t["access_token"])
    full = client.get("/api/v1/controls", params={"include_withdrawn": True, "limit": 2000}, headers=h).json()
    live = client.get("/api/v1/controls", params={"limit": 2000}, headers=h).json()
    fams = client.get("/api/v1/controls/families", headers=h).json()
    items = full["items"]
    snap = {
        "total_incl_withdrawn": full["total"], "total_selectable": live["total"],
        "withdrawn": sum(1 for c in items if c["is_withdrawn"]), "enhancements": sum(1 for c in items if c["is_enhancement"]),
        "families": {f["family_id"]: [f["family_title"], f["count"]] for f in fams},
        "items_sha256": _digest(items),
        "detail_sha256": {cid: _digest({k: v for k, v in client.get(f"/api/v1/controls/{cid}", headers=h).json().items() if k != "provenance"}) for cid in DETAIL},
    }
    if os.environ.get("UPDATE_CATALOG_SNAPSHOT") == "1":
        SNAP.write_text(json.dumps(snap, indent=1, sort_keys=True))
    want = json.loads(SNAP.read_text())
    assert snap == want
    assert want["total_incl_withdrawn"] == 1196 and want["withdrawn"] + want["total_selectable"] == 1196  # active Rev 5 catalog as loaded


def test_cci_index_is_read_only_lookup(client, signup_on):  # noqa: F811
    t = _signup(client, f"cci-{uuid.uuid4().hex[:6]}@example.com", "CCI index Org")
    idx = client.get("/api/v1/controls/cci-index", headers=auth(t["access_token"])).json()
    assert "ac-2.1" in idx["CCI-000015"] and all(isinstance(v, list) and v for v in idx.values())
