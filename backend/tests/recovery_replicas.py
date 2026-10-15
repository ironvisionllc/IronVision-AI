"""Recovery replicas for the pod (synthetic, realistic): python tests/recovery_replicas.py OUT_DIR

- source: real app seed at head padded to the customer's stated shape (8 users, 1 org, 4 systems, 25 role assignments,
  38 evidence, 111 findings, 1,624 jobs, 1,772 audit events – chain valid), then `alembic downgrade 0009`, pg_dump -Fc
- prod replica DB rec_live_prod: head → reference catalogs only (+1 production-only admin via its own org) → downgrade 0012
- MinIO xl-single archive of the 38 evidence objects under the OLD bucket name (inline + part.1 cases, 1 missing, 1 corrupted)
Env: DATABASE_URL base (role with CREATEDB), RECOVER_PG_BIN.
"""
import hashlib
import io
import json
import os
import struct
import subprocess
import sys
import tarfile
import uuid
from pathlib import Path

import msgpack
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

BACKEND = Path(__file__).resolve().parents[1]
SHAPE = {"evidence": 38, "findings": 111, "jobs": 1624, "audit_events": 1772}


def _url(name: str) -> str:
    return make_url(os.environ["DATABASE_URL"]).set(database=name).render_as_string(hide_password=False)


def _fresh(name: str) -> str:
    eng = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        c.execute(text(f'CREATE DATABASE "{name}"'))
    eng.dispose()
    return _url(name)


def _alembic(url: str, fn: str, rev: str) -> None:
    from alembic.config import Config

    from alembic import command
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.attributes["database_url"] = url
    getattr(command, fn)(cfg, rev)


def _dump(url: str, out: Path) -> None:
    u = make_url(url)
    subprocess.run([os.path.join(os.environ.get("RECOVER_PG_BIN", ""), "pg_dump"), "-h", u.host, "-p", str(u.port or 5432), "-U", u.username,
                    "-Fc", "-f", str(out), u.database], env={**os.environ, "PGPASSWORD": u.password or ""}, check=True)


def stage_source(out: Path) -> None:
    """Runs in its own process (settings cache): DATABASE_URL=source db, STORAGE_DRIVER=local."""
    from sqlalchemy import func, select

    from app.db import SessionLocal
    from app.models import Evidence, Finding, Job, System
    from app.seed import seed_demo
    from app.seed_phase1 import seed_phase1
    from app.services import audit, jobs
    from app.services.content.loader import load_reference_content
    from app.services.rmf import store_evidence
    with SessionLocal() as db:
        org = seed_demo(db, "Replica-Pass-2026!x")
        load_reference_content(db)
        db.commit()
        seed_phase1(db, org, str(BACKEND.parent / "samples"))
        db.commit()
        systems = list(db.scalars(select(System).order_by(System.acronym)))
        i = 0
        while db.scalar(select(func.count()).select_from(Evidence)) < SHAPE["evidence"]:
            big = i % 3 == 0  # > 128 KiB → MinIO part.1 file; others inline in xl.meta
            data = (f"replica evidence {i}\n".encode() * (9000 if big else 40)) + os.urandom(64)
            store_evidence(db, systems[i % len(systems)].id, f"replica-{i:02d}.txt", data, "document", "replica@aegisrmf.demo", "replica")
            db.commit()
            i += 1
        f = db.scalar(select(Finding).limit(1))
        while db.scalar(select(func.count()).select_from(Finding)) < SHAPE["findings"]:
            cols = {c.name: getattr(f, c.key) for c in Finding.__table__.columns if c.name not in ("id", "created_at", "updated_at")}
            cols["dedup_key"] = hashlib.sha256(os.urandom(8)).hexdigest()
            db.add(Finding(**cols))
            db.commit()
        n = db.scalar(select(func.count()).select_from(Job))
        for k in range(SHAPE["jobs"] - n):
            jobs.enqueue(db, "replica_history", {"n": k})
        db.commit()
        n = db.scalar(select(func.count()).select_from(audit.AuditEvent))
        for k in range(SHAPE["audit_events"] - n):
            audit.record(db, action="replica.history", entity_type="replica", entity_id=str(k), actor_email="replica@aegisrmf.demo")
            if k % 200 == 0:
                db.commit()
        db.commit()
        ev = [{"key": e.storage_key, "sha256": e.sha256} for e in db.scalars(select(Evidence))]
    (out / "evidence.json").write_text(json.dumps(ev))


def stage_prod() -> None:
    from app.db import SessionLocal
    from app.models import AuthIdentity, Organization, RoleAssignment, User
    from app.seed import ensure_reference_content
    from app.services.content.loader import load_reference_content
    with SessionLocal() as db:
        load_reference_content(db)
        ensure_reference_content(db)
        org = Organization(name="IronVision Operations", slug="ironvision-ops")
        db.add(org)
        db.flush()
        u = User(org_id=org.id, email="ops-admin@ironvisionai.com", display_name="Ops admin (create-admin)", source="cli:create-admin")
        db.add(u)
        db.flush()
        db.add(RoleAssignment(user_id=u.id, role="platform_admin", scope_type="organization", scope_id=org.id))
        db.add(AuthIdentity(user_id=u.id, provider="oidc", subject=f"https://auth.example/realms/ironvision-demo|{uuid.uuid4()}"))
        db.commit()


# ---------------- MinIO xl-single writer (per the published on-disk format) ----------------
def _frame(data: bytes, shard: int = 1048576) -> bytes:
    return b"".join(os.urandom(32) + data[i:i + shard] for i in range(0, max(len(data), 1), shard))


def xl_meta(data: bytes, inline: bool, ddir: uuid.UUID) -> bytes:
    vid = b"\0" * 16  # unversioned bucket → version "null"
    obj = {"ID": vid, "DDir": ddir.bytes, "EcAlgo": 1, "EcM": 1, "EcN": 0, "EcBSize": 1048576, "EcIndex": 1, "EcDist": [1], "CSumAlgo": 1,
           "PartNums": [1], "PartETags": None, "PartSizes": [len(data)], "PartASizes": [len(data)], "Size": len(data), "MTime": 1735689600000000000,
           "MetaSys": {"x-minio-internal-inline-data": b"true"} if inline else {}, "MetaUsr": {"content-type": "text/plain", "etag": hashlib.md5(data).hexdigest()}}
    meta = msgpack.packb({"Type": 1, "V2Obj": obj})
    hdr = msgpack.packb([vid, obj["MTime"], b"\0\0\0\0", 1, 0])
    block = msgpack.packb(3) + msgpack.packb(2) + msgpack.packb(1) + msgpack.packb(hdr) + msgpack.packb(meta)
    raw = b"XL2 " + struct.pack("<HH", 1, 3) + msgpack.packb(block) + msgpack.packb(0xC0FFEE)
    if inline:
        raw += bytes([1]) + msgpack.packb({"null": _frame(data)})
    return raw


def build_archive(ev: list[dict], store: Path, out: Path) -> dict:
    buf = io.BytesIO()
    plan = {"missing": ev[5]["key"], "corrupted": ev[7]["key"], "inline": 0, "part": 0}
    with tarfile.open(out, "w:gz") as tf:
        def add(name: str, data: bytes) -> None:
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            tf.addfile(ti, io.BytesIO(data))
        add("data/.minio.sys/format.json", json.dumps({"version": "1", "format": "xl-single", "id": str(uuid.uuid4()),
                                                      "xl": {"version": "3", "this": "d1", "sets": [["d1"]], "distributionAlgo": "SIPMOD+PARITY"}}).encode())
        for e in ev:
            if e["key"] == plan["missing"]:
                continue
            data = (store / e["key"]).read_bytes()
            if e["key"] == plan["corrupted"]:
                data = data[:-1] + bytes([data[-1] ^ 0xFF])
            inline = len(data) < 128 * 1024
            ddir = uuid.uuid4()
            base = f"data/aegisrmf-evidence/{e['key']}"
            add(f"{base}/xl.meta", xl_meta(data, inline, ddir))
            if not inline:
                add(f"{base}/{ddir}/part.1", _frame(data))
            plan["inline" if inline else "part"] += 1
    del buf
    return plan


def main(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    store = out / "store"
    env = {**os.environ, "STORAGE_DRIVER": "local", "STORAGE_LOCAL_ROOT": str(store), "PYTHONPATH": str(BACKEND)}
    src = _fresh("rec_replica_source")
    _alembic(src, "upgrade", "head")
    subprocess.run([sys.executable, __file__, "--stage-source", str(out)], env={**env, "DATABASE_URL": src}, check=True, cwd=BACKEND)
    _alembic(src, "downgrade", "0009")
    _dump(src, out / "aegisrmf-old-db.backup")
    prod = _fresh("rec_live_prod")
    _alembic(prod, "upgrade", "head")
    subprocess.run([sys.executable, __file__, "--stage-prod"], env={**env, "DATABASE_URL": prod}, check=True, cwd=BACKEND)
    _alembic(prod, "downgrade", "0012")
    _dump(prod, out / "ironvision-production-before-restore.backup")
    ev = json.loads((out / "evidence.json").read_text())
    plan = build_archive(ev, store, out / "aegisrmf-minio-backup.tar.gz")
    (out / "archive-plan.json").write_text(json.dumps(plan))
    print(json.dumps({"source_db": "rec_replica_source", "prod_db": "rec_live_prod", "archive": plan}))


if __name__ == "__main__":
    if sys.argv[1] == "--stage-source":
        stage_source(Path(sys.argv[2]))
    elif sys.argv[1] == "--stage-prod":
        stage_prod()
    else:
        main(Path(sys.argv[1]))
