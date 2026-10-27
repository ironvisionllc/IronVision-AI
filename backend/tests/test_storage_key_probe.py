"""Storage-key probe: tenant B can never read or overwrite tenant A's stored objects through any endpoint that accepts a key, file name,
slug or path – keys/paths in path/query params (OpenAPI-generated), traversal slugs, A's download IDs, and traversal upload file names."""
import hashlib
import posixpath
import re
import uuid
from urllib.parse import quote

import pytest
from sqlalchemy import select

from app import models as M
from app.db import SessionLocal
from app.main import app
from app.services.storage import get_storage
from tests.conftest import auth
from tests.test_sandbox import _signup, signup_on  # noqa: F401

STORED = [m.class_ for m in M.Base.registry.mappers if "storage_key" in m.class_.__table__.c]


def _a_objects(org) -> list[tuple[str, bytes, str]]:
    out = []
    with SessionLocal() as db:
        sids = list(db.scalars(select(M.System.id).where(M.System.org_id == org)))
        for Mdl in STORED:
            c = Mdl.__table__.c
            if "org_id" in c:
                cl = Mdl.org_id == org
            elif "system_id" in c:
                cl = Mdl.system_id.in_(sids)
            else:
                continue
            for row in db.scalars(select(Mdl).where(cl, Mdl.storage_key.is_not(None))):
                try:
                    data = get_storage().get(row.storage_key)
                except Exception:  # noqa: BLE001
                    continue
                out.append((row.storage_key, data, f"{Mdl.__name__}:{row.id}"))
    return out


@pytest.fixture(scope="module")
def w(client, signup_on):  # noqa: F811
    ta = _signup(client, f"sp-a-{uuid.uuid4().hex[:6]}@example.com", "Probe A")
    ha = auth(ta["access_token"])
    assert client.post("/api/v1/sandbox/demo-data", headers=ha).status_code in (200, 201, 202)
    with SessionLocal() as db:
        org_a = db.scalar(select(M.User.org_id).where(M.User.email == ta["user"]["email"]))
    tb = _signup(client, f"sp-b-{uuid.uuid4().hex[:6]}@example.com", "Probe B")
    hb = auth(tb["access_token"])
    sid_b = client.post("/api/v1/systems", json={"name": "Probe B", "acronym": f"PB{uuid.uuid4().hex[:3]}", "baseline_key": "low",
                                                 "categorization_mode": "fips199", "information_types": [{"id": "D.16.3"}]}, headers=hb).json()["id"]
    mint = lambda r: auth(client.post("/api/v1/sandbox/act-as", json={"role": r}, headers=hb).json()["access_token"])  # noqa: E731
    objs = [o for o in _a_objects(org_a) if len(o[1]) >= 64]
    assert objs, "tenant A has stored objects"
    return {"objs": objs, "b": {r: mint(r) for r in ("isso", "platform_admin")}, "sid_b": sid_b, "org_a": org_a}


def _leaks(body: bytes, objs) -> list[str]:
    return [lbl for _, data, lbl in objs if data[:64] in body or hashlib.sha256(body).digest() == hashlib.sha256(data).digest()]


def test_keys_and_paths_in_string_params_never_return_a_objects(client, w):
    spec = app.openapi()
    keys = [k for k, _, _ in w["objs"][:6]]
    probes = keys + [quote(k, safe="") for k in keys] + [f"../../{k}" for k in keys] + ["../../backend/.env", "..%2f..%2fbackend%2f.env", "/etc/passwd"]
    n, leaks = 0, []
    for path, ops in spec["paths"].items():
        if not path.startswith("/api/v1"):
            continue
        op = ops.get("get")
        if not op:
            continue
        strs = [p for p in op.get("parameters", []) if p.get("schema", {}).get("type") == "string" and p.get("schema", {}).get("format") != "uuid"
                and p["in"] in ("path", "query")]
        uuids = re.findall(r"{(\w+)}", path)
        if not strs:
            continue
        for pr in probes:
            params = {p: (pr if any(s["name"] == p for s in strs) else str(uuid.uuid4())) for p in uuids}
            url = path.format(**params) if params else path
            query = {s["name"]: pr for s in strs if s["in"] == "query"}
            for h in w["b"].values():
                r = client.get(url, params=query, headers=h)
                n += 1
                if got := _leaks(r.content, w["objs"]):
                    leaks.append((path, pr, r.status_code, got[:2]))
                assert b"JWT_SECRET" not in r.content and b"root:x:0:0" not in r.content, (path, pr)
    print(f"string-param probes={n}, A objects={len(w['objs'])}")
    assert n > 0 and not leaks, leaks


def test_download_endpoints_with_a_ids_denied(client, w):
    with SessionLocal() as db:
        ev = db.scalars(select(M.Evidence).join(M.System, M.System.id == M.Evidence.system_id).where(M.System.org_id == w["org_a"])).all()
    urls = [f"/api/v1/evidence/{e.id}/download" for e in ev[:20]] + [f"/api/v1/oscal-exports/{e.id}/download" for e in ev[:5]]
    for u in urls:
        for h in w["b"].values():
            r = client.get(u, headers=h)
            assert r.status_code in (403, 404) and not _leaks(r.content, w["objs"]), (u, r.status_code)


def test_traversal_upload_file_name_stays_in_own_namespace(client, w):
    key_a, data_a, _ = next(o for o in w["objs"] if o[0].startswith("evidence/"))
    evil = "../../" + key_a.split("/", 1)[1]  # evidence/<B>/<sha>/../../<A sys>/<A sha>/<name> would resolve into A's prefix
    files = {"file": (evil, b"<?xml version='1.0'?><checklist>SYNTHETIC overwrite attempt</checklist>", "application/xml")}
    r = client.post(f"/api/v1/systems/{w['sid_b']}/uploads", files=files, headers=w["b"]["isso"])
    assert get_storage().get(key_a) == data_a, "tenant A object was overwritten"
    with SessionLocal() as db:
        for k in db.scalars(select(M.Evidence.storage_key).where(M.Evidence.system_id == uuid.UUID(w["sid_b"]))):
            assert ".." not in k.split("/") and posixpath.normpath(k).startswith(f"evidence/{w['sid_b']}/"), k
    print("traversal upload status", r.status_code)


def test_traversal_file_name_cannot_enter_another_prefix(w):
    """Root cause found by this probe: user file names were put into storage keys verbatim (evidence/<B sys>/<sha>/<name>); a name like
    '../../<A sys>/<A sha>/<A name>' resolved into tenant A's prefix (overwrite risk). Names are now one sanitized key segment and
    storage drivers reject '..' segments."""
    from app.services import rmf
    from app.services.storage.base import check_key, safe_key_part
    key_a, data_a, _ = next(o for o in w["objs"] if o[0].startswith("evidence/"))
    evil = "../../" + key_a.split("/", 1)[1]
    with SessionLocal() as db:
        ev = rmf.store_evidence(db, uuid.UUID(w["sid_b"]), evil, b"SYNTHETIC overwrite attempt " * 4, "manual", "probe@example.com", "probe")
        assert posixpath.normpath(ev.storage_key).startswith(f"evidence/{w['sid_b']}/") and ".." not in ev.storage_key.split("/"), ev.storage_key
        db.rollback()
    assert get_storage().get(key_a) == data_a
    assert safe_key_part("..\\..\\x/../y.txt") == "y.txt" and safe_key_part("..") == "file"
    for bad in ("evidence/a/../b", "../x", "/etc/passwd"):
        with pytest.raises(ValueError):
            check_key(bad)
