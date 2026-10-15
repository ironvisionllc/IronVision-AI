"""Unit tests for the recovery toolkit pieces that need no external services."""
import json
import os
import uuid
from pathlib import Path

import msgpack
import pytest

from app.tools import minio_xl
from tests.recovery_replicas import _frame, xl_meta


def _obj(tmp: Path, data: bytes, inline: bool, meta_sys: dict | None = None, ec=(1, 0)) -> Path:
    d = tmp / "bucket" / "k.txt"
    d.mkdir(parents=True)
    ddir = uuid.uuid4()
    raw = xl_meta(data, inline, ddir)
    if meta_sys is not None or ec != (1, 0):  # rewrite the version meta with refusal markers
        vs, inl = minio_xl._versions(raw)
        o = vs[0]["V2Obj"]
        o["MetaSys"] = {**o["MetaSys"], **(meta_sys or {})}
        o["EcM"], o["EcN"] = ec
        meta = msgpack.packb({"Type": 1, "V2Obj": o})
        hdr = msgpack.packb([o["ID"], o["MTime"], b"\0\0\0\0", 1, 0])
        block = msgpack.packb(3) + msgpack.packb(2) + msgpack.packb(1) + msgpack.packb(hdr) + msgpack.packb(meta)
        raw = raw[:8] + msgpack.packb(block) + msgpack.packb(0) + inl
    (d / "xl.meta").write_bytes(raw)
    if not inline:
        (d / str(ddir)).mkdir()
        (d / str(ddir) / "part.1").write_bytes(_frame(data))
    return d


def test_minio_inline_and_multi_block_part(tmp_path):
    small = b"inline evidence"
    assert minio_xl.read_object(_obj(tmp_path / "a", small, True)) == small
    big = os.urandom(2 * 1048576 + 12345)  # 3 bitrot-framed shard blocks
    assert minio_xl.read_object(_obj(tmp_path / "b", big, False)) == big


@pytest.mark.parametrize("meta,ec,msg", [({"X-Minio-Internal-Server-Side-Encryption-Sealed-Key": b"x"}, (1, 0), "SSE"),
                                         ({"X-Minio-Internal-compression": b"klauspost/compress/s2"}, (1, 0), "compressed"),
                                         ({}, (2, 2), "erasure-coded")])
def test_minio_refuses_encrypted_compressed_erasure(tmp_path, meta, ec, msg):
    with pytest.raises(minio_xl.MinioFormatError, match=msg):
        minio_xl.read_object(_obj(tmp_path, b"x" * 10, True, meta, ec))


def test_minio_refuses_multi_drive_format_and_bad_magic(tmp_path):
    (tmp_path / ".minio.sys").mkdir()
    (tmp_path / ".minio.sys" / "format.json").write_text(json.dumps({"format": "xl", "xl": {"sets": [["a", "b", "c", "d"]]}}))
    with pytest.raises(minio_xl.MinioFormatError, match="multi-drive"):
        minio_xl.check_format(tmp_path)
    d = tmp_path / "o"
    d.mkdir()
    (d / "xl.meta").write_bytes(b'{"legacy": "xl.json"}')
    with pytest.raises(minio_xl.MinioFormatError, match="magic"):
        minio_xl.read_object(d)


def test_purge_refuses_protected_customer_and_real_role_tenants(client):
    from sqlalchemy import select

    from app.db import SessionLocal
    from app.models import Organization, RoleAssignment, User
    from app.services import sandbox as sbx
    with SessionLocal() as db:
        real = db.scalar(select(Organization).where(Organization.is_sandbox.is_(False)).limit(1))
        assert sbx.purge_refusal(db, real) == "not a sandbox tenant"
        with pytest.raises(PermissionError):
            sbx.purge(db, real, "test")
        u, org = sbx.create_owner(db, f"guard-{uuid.uuid4().hex[:6]}@example.org", "Guard Owner", None)
        db.flush()
        assert sbx.purge_refusal(db, org) is None  # genuine self-service sandbox: eligible
        org.protected = True
        assert sbx.purge_refusal(db, org) == "tenant is protected"
        org.protected = False
        db.add(RoleAssignment(user_id=u.id, role="isso", scope_type="organization", scope_id=org.id))
        db.flush()
        assert "outside sandbox persona mode" in sbx.purge_refusal(db, org)
        demo = db.scalar(select(User).where(User.email == sbx.DEMO_EMAIL))
        if demo:
            assert "shared demo" in sbx.purge_refusal(db, db.get(Organization, demo.org_id))
        db.rollback()


def test_check_env_registration_rules():
    from app.check_env import validate as check
    base = {"APP_ENV": "production", "AUTH_DOMAIN": "auth.example.com", "AUTH_PROVIDERS": "oidc", "KEYCLOAK_ALLOW_REGISTRATION": "true",
            "KEYCLOAK_BACKEND_CLIENT_SECRET": "x" * 40}
    errs = check({**base, "DEPLOYMENT_KIND": "customer-production"})[0]
    assert any("KEYCLOAK_ALLOW_REGISTRATION=true is refused unless DEPLOYMENT_KIND=demo" in e for e in errs)
    errs = check({**base, "DEPLOYMENT_KIND": "demo", "KEYCLOAK_BACKEND_CLIENT_SECRET": "short"})[0]
    assert any("KEYCLOAK_BACKEND_CLIENT_SECRET" in e for e in errs)
    errs = check({**base, "DEPLOYMENT_KIND": "demo", "KEYCLOAK_REALM": "customer"})[0]
    assert any("only supported on realm ironvision-demo" in e for e in errs)


def test_recovery_redaction_and_scratch_guard(monkeypatch):
    from app.tools import recovery as R
    monkeypatch.setenv("S3_SECRET_ACCESS_KEY", "supersecretvalue123")
    assert R.redact("postgresql+psycopg://u:pw@h/db key supersecretvalue123") == "postgresql+psycopg://u:***@h/db key ***"
    for name in ("ironvision", "keycloak", "ironvision_recovered_20261015t000000", "aegisrmf_backup_test"):
        with pytest.raises(R.RecoveryError, match="refusing to drop"):
            R.drop_scratch_db(name)
