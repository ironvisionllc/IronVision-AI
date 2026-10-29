"""Import Center "Remove before import": queued files are removed before anything is applied – audited; a routed eMASS file still at its
review prompt is discarded and its stored copy deleted; applied imports, other tenants and roles without write access are refused."""
import uuid

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import AuditEvent, EmassImport
from app.services import emass_migration as em
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

FIPS = {"baseline_key": "moderate", "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}], "processes_pii": False}


def _org(client, tag):
    t = _signup(client, f"{tag}-{uuid.uuid4().hex[:6]}@example.com", f"{tag} Org")
    h = auth(t["access_token"])
    role = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=h).json()["access_token"])  # noqa: E731
    sid = client.post("/api/v1/systems", json={"name": f"{tag} Sys", "acronym": "RM" + uuid.uuid4().hex[:3], **FIPS}, headers=h).json()["id"]
    return {"sid": sid, "h": h, "role": role, "isso": role("isso")}


@pytest.fixture(scope="module")
def ctx(client, signup_on):  # noqa: F811
    return _org(client, "rm")


@pytest.fixture(scope="module")
def other(client, signup_on):  # noqa: F811
    return _org(client, "rmo")


def _upload(client, o):
    r = client.post("/api/v1/emass-imports", files={"file": ("slcm.xlsx", em.sample("slcm"))}, data={"system_id": o["sid"]}, headers=o["isso"])
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _remove(client, o, items, h=None):
    return client.post("/api/v1/import-center/remove", json={"system_id": o["sid"], "items": items}, headers=h or o["isso"])


def test_remove_queued_and_stored_files_before_apply(client, ctx):
    from app.services.storage.base import get_storage
    iid = _upload(client, ctx)
    with SessionLocal() as db:
        key = db.get(EmassImport, uuid.UUID(iid)).storage_key
    assert get_storage().exists(key)
    r = _remove(client, ctx, [{"file_name": "slcm.xlsx", "size_bytes": 10, "state": "needs_decision", "emass_import_id": iid},
                              {"file_name": "scan.ckl", "size_bytes": 5, "state": "ready"}])
    assert r.status_code == 200 and len(r.json()["removed"]) == 2 and not r.json()["skipped"], r.text
    assert r.json()["removed"][0]["stored_copy_deleted"] is True and not get_storage().exists(key)
    with SessionLocal() as db:
        assert db.get(EmassImport, uuid.UUID(iid)).status == "discarded"
        evs = list(db.scalars(select(AuditEvent).where(AuditEvent.action == "import.removed_before_apply").order_by(AuditEvent.occurred_at.desc()).limit(2)))
        by = {e.details["file_name"]: e.details for e in evs}
        assert by["slcm.xlsx"]["was_stored"] and by["slcm.xlsx"]["stored_copy_deleted"] and not by["scan.ckl"]["was_stored"]
    again = _remove(client, ctx, [{"file_name": "slcm.xlsx", "emass_import_id": iid}])
    assert again.json()["skipped"][0]["reason"].startswith("Already discarded")


def test_remove_refuses_other_tenant_read_only_role_and_applied(client, ctx, other):
    iid = _upload(client, ctx)
    cross = client.post("/api/v1/import-center/remove", json={"items": [{"file_name": "x", "emass_import_id": iid}]}, headers=other["isso"])
    assert cross.status_code == 200 and cross.json()["skipped"][0]["reason"] == "Not found"
    assert _remove(client, other, [{"file_name": "x"}], h=ctx["isso"]).status_code == 404, "another tenant's system is not visible"
    ro = _remove(client, ctx, [{"file_name": "x", "emass_import_id": iid}], h=ctx["role"]("leadership_viewer"))
    assert ro.status_code in (200, 403)
    if ro.status_code == 200:
        assert ro.json()["skipped"] and not ro.json()["removed"]
    with SessionLocal() as db:
        imp = db.get(EmassImport, uuid.UUID(iid))
        assert imp.status != "discarded"
        imp.status = "applied"
        db.commit()
    ap = _remove(client, ctx, [{"file_name": "x", "emass_import_id": iid}])
    assert ap.json()["skipped"][0]["reason"].startswith("Already applied") and not ap.json()["removed"]
    assert client.post("/api/v1/import-center/remove", json={"items": []}, headers=ctx["isso"]).status_code == 422
