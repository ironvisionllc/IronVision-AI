"""Recovery `verify` is READ-ONLY: independent SHA-256 check of every evidence object, read-only DB transaction, no app
verify_integrity job (which writes integrity_checks/evidence/freshness for every org). Real pod Postgres + SeaweedFS."""
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.db import engine as test_engine

pytestmark = pytest.mark.skipif(os.environ.get("RECOVERY_E2E") != "1", reason="RECOVERY_E2E=1 (pod Postgres + SeaweedFS) only")
BACKEND = Path(__file__).resolve().parents[1]
S3 = {"S3_ENDPOINT_URL": "http://127.0.0.1:18333", "S3_BUCKET": "evidence-live", "S3_REGION": "us-east-1", "S3_ADDRESSING_STYLE": "path",
      "S3_ACCESS_KEY_ID": "recapp", "S3_SECRET_ACCESS_KEY": "rec-app-secret-0123456789abcdef",
      "RECOVER_S3_ADMIN_ACCESS_KEY_ID": "recadmin", "RECOVER_S3_ADMIN_SECRET_ACCESS_KEY": "rec-admin-secret-0123456789abcdef"}


def _admin_s3():
    import boto3
    from botocore.config import Config
    return boto3.client("s3", endpoint_url=S3["S3_ENDPOINT_URL"], aws_access_key_id=S3["RECOVER_S3_ADMIN_ACCESS_KEY_ID"],
                        aws_secret_access_key=S3["RECOVER_S3_ADMIN_SECRET_ACCESS_KEY"], region_name="us-east-1",
                        config=Config(s3={"addressing_style": "path"}))


def _pg(url: str) -> str:
    return make_url(url).set(drivername="postgresql").render_as_string(hide_password=False)


@pytest.fixture
def target(tmp_path):
    """Scratch copy of the test DB; every evidence row gets its own object in the live bucket under a test-only prefix."""
    base = test_engine.url.render_as_string(hide_password=False)
    name, tag = f"rv_{uuid.uuid4().hex[:10]}", uuid.uuid4().hex[:8]
    url = make_url(base).set(database=name).render_as_string(hide_password=False)
    adm = create_engine(make_url(base).set(database="postgres"), isolation_level="AUTOCOMMIT")
    with adm.connect() as c:
        c.execute(text(f'create database "{name}"'))
    dump = subprocess.run(["pg_dump", "-Fc", _pg(base)], capture_output=True, check=True).stdout
    subprocess.run(["pg_restore", "--no-owner", "-d", _pg(url)], input=dump, capture_output=True, check=False)
    cl, eng = _admin_s3(), create_engine(url)
    with eng.begin() as c:
        ids = [r[0] for r in c.execute(text("select id::text from evidence order by id"))]
        for i in ids:
            body, key = f"rv evidence {i}".encode(), f"evidence/rvtest-{tag}/{i}"
            cl.put_object(Bucket=S3["S3_BUCKET"], Key=key, Body=body)
            c.execute(text("update evidence set storage_key = :k, sha256 = :s where id = :i"), {"k": key, "s": hashlib.sha256(body).hexdigest(), "i": i})
    eng.dispose()
    assert ids, "test DB has no evidence"
    yield {"url": url, "name": name, "ids": ids, "tag": tag, "rdir": tmp_path / "rdir", "s3": cl}
    for i in ids:
        cl.delete_object(Bucket=S3["S3_BUCKET"], Key=f"evidence/rvtest-{tag}/{i}")
    with adm.connect() as c:
        c.execute(text(f'drop database if exists "{name}" with (force)'))
    adm.dispose()


def _key(t, i):
    return f"evidence/rvtest-{t['tag']}/{i}"


def verify(t) -> tuple[subprocess.CompletedProcess, dict]:
    t["rdir"].mkdir(exist_ok=True)
    env = {"PATH": os.environ["PATH"], "HOME": "/root", "APP_ENV": "production", "IRONVISION_DOTENV": "0", "DATABASE_URL": t["url"],
           "STORAGE_DRIVER": "s3", "RECOVERY_DIR": str(t["rdir"]), **S3}
    r = subprocess.run([sys.executable, "-m", "app.tools.recovery", "verify"], env=env, cwd=BACKEND, capture_output=True, text=True, check=False)
    rep = json.loads(max(t["rdir"].glob("verify-*.json")).read_text())
    return r, rep


def all_tables(url: str) -> dict:
    eng = create_engine(url)
    with eng.connect() as c:
        tabs = [r[0] for r in c.execute(text("select tablename from pg_tables where schemaname = 'public' order by 1"))]
        out = {tb: tuple(c.execute(text(f'select count(*), md5(coalesce(string_agg(t::text, \',\' order by t::text), \'\')) from "{tb}" t')).first())
               for tb in tabs}
    eng.dispose()
    return out


def tuple_writes(url: str) -> int:
    time.sleep(1.5)  # exiting backends flush their stats; give the collector a moment
    eng = create_engine(url)
    with eng.connect() as c:
        c.execute(text("select pg_stat_clear_snapshot()"))
        n = c.execute(text("select coalesce(sum(n_tup_ins + n_tup_upd + n_tup_del), 0) from pg_stat_user_tables")).scalar()
    eng.dispose()
    return int(n)


def test_successful_verify_changes_no_table_and_leaves_no_object(target):
    before, w0 = all_tables(target["url"]), tuple_writes(target["url"])
    r, rep = verify(target)
    assert r.returncode == 0, r.stdout + r.stderr
    o = rep["checks"]["objects"]
    assert o["read_only"] and o["verified"] == o["evidence"] == len(target["ids"]) and o["failures"] == [] and o["accepted_exceptions"] == []
    assert all_tables(target["url"]) == before                       # every table, not only the protected categories
    assert tuple_writes(target["url"]) == w0                         # zero inserts/updates/deletes on the target DB
    rt = rep["checks"]["storage_roundtrip"]
    assert rt["ok"] and rt["key"].startswith(".ironvision-recovery-roundtrip/") and rt["deleted"]
    left = target["s3"].list_objects_v2(Bucket=S3["S3_BUCKET"], Prefix=".ironvision-recovery-roundtrip/").get("KeyCount", 0)
    assert left == 0


def test_hash_mismatch_fails_naming_id_and_key_without_contents(target):
    i = target["ids"][0]
    target["s3"].put_object(Bucket=S3["S3_BUCKET"], Key=_key(target, i), Body=b"TAMPERED-CONTENT")
    r, rep = verify(target)
    assert r.returncode == 1 and not rep["passed"]
    assert rep["checks"]["objects"]["failures"] == [{"evidence_id": i, "storage_key": _key(target, i), "status": "hash_mismatch"}]
    assert rep["checks"]["objects"]["counts"]["hash_mismatch"] == 1 and "TAMPERED" not in json.dumps(rep) + r.stdout


def test_missing_object_fails(target):
    i = target["ids"][-1]
    target["s3"].delete_object(Bucket=S3["S3_BUCKET"], Key=_key(target, i))
    r, rep = verify(target)
    assert r.returncode == 1 and rep["checks"]["objects"]["failures"][0]["status"] == "missing"


def test_unreadable_object_fails(target, monkeypatch):
    from app.tools import recovery as rv

    class Broken:
        def get_object(self, **kw):
            raise RuntimeError("connection reset")
    monkeypatch.setattr(rv, "s3", lambda admin=False: Broken())
    res = rv.evidence_check_ro(target["url"], S3["S3_BUCKET"], set())
    assert res["counts"]["unreadable"] == len(target["ids"]) and res["verified"] == 0 and len(res["failures"]) == len(target["ids"])


def _apply_record(t, key, accepted: bool):
    t["rdir"].mkdir(exist_ok=True)
    (t["rdir"] / "apply-20990101t000000.json").write_text(json.dumps({
        "target_db": t["name"], "result": {"objects": {"detail": [{"storage_key": key, "status": "missing"}]}},
        "evidence_exceptions": {"exceptions_hash": "abcd", "accepted_by_operator": accepted}}))


def test_known_unrecoverable_fails_unless_acknowledged_and_is_never_counted_verified(target):
    i = target["ids"][0]
    target["s3"].delete_object(Bucket=S3["S3_BUCKET"], Key=_key(target, i))
    _apply_record(target, _key(target, i), accepted=False)
    r, rep = verify(target)
    assert r.returncode == 1 and "NOT acknowledged" in rep["failures"][0]
    _apply_record(target, _key(target, i), accepted=True)
    r, rep = verify(target)
    o = rep["checks"]["objects"]
    assert r.returncode == 0 and o["accepted_exceptions"] == [{"evidence_id": i, "storage_key": _key(target, i), "status": "missing"}]
    assert o["verified"] == len(target["ids"]) - 1 and o["counts"]["missing"] == 1 and o["failures"] == []
    assert rep["checks"]["known_unrecoverable"]["acknowledged"] is True and "ACCEPTED-EXCEPTION missing" in r.stdout


def test_roundtrip_refuses_a_namespace_used_by_evidence(target):
    eng = create_engine(target["url"])
    with eng.begin() as c:
        c.execute(text("update evidence set storage_key = '.ironvision-recovery-roundtrip/x' where id = :i"), {"i": target["ids"][0]})
    eng.dispose()
    r, rep = verify(target)
    assert r.returncode == 1 and not rep["checks"]["storage_roundtrip"]["put"] and "refusing" in rep["checks"]["storage_roundtrip"]["error"]
