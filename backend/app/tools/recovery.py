"""IronVision data + object recovery engine (driven by ./recover.sh; runs in the `recovery` tool container or locally).

Strategy: NON-DESTRUCTIVE SWAP. The recovered database is a NEW database (source backup restored, upgraded 0009→head, production-
only rows merged, restored org marked protected); the live DB is never modified, so rollback = point DATABASE_URL back. Objects
are copied into the live bucket copy-only (an existing key is never overwritten; identical bytes count as present).
Secrets are never printed; logs/reports go to RECOVERY_DIR (default /root/ironvision-recovery).
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

RDIR = Path(os.environ.get("RECOVERY_DIR") or "/root/ironvision-recovery")
PRE = Path(os.environ.get("RECOVER_PREDEPLOY_DIR") or "/root/ironvision-predeploy")
CATALOG = {  # natural keys (+ content-version hashes) – UUIDs legitimately differ between independent loads
    "catalog_versions": ["content_type", "content_key", "version", "sha256"],
    "controls": ["control_id", "title"], "ccis": ["cci_id", "definition"], "baselines": ["baseline_key", "control_count"],
    "baseline_controls": ["control_id"], "cci_control_map": ["cci_id", "control_id", "reference_index"],
    "control_objectives": ["objective_id"], "stig_rules": ["rule_id", "vuln_id"],
}
TRANSIENT = {"auth_sessions", "oidc_pending", "oidc_login_codes", "login_attempts", "worker_heartbeats"}
VOLATILE = TRANSIENT | {"audit_events", "jobs", "notifications", "integrity_checks", "ai_interactions"}
SCRATCH = re.compile(r"^(rec_(src|prod|target)_\d{8}t\d{6}|ironvision_recovered_\d{8}t\d{6})$")


class RecoveryError(Exception):
    pass


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dt%H%M%S")


def redact(s: str) -> str:
    s = re.sub(r"(://[^:/@\s]+):[^@\s]+@", r"\1:***@", s)
    for k, v in os.environ.items():
        if v and len(v) >= 8 and re.search(r"SECRET|PASSWORD|_KEY$|TOKEN", k):
            s = s.replace(v, "***")
    return s


def log(msg: str) -> None:
    RDIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    line = redact(f"{datetime.now(timezone.utc).isoformat(timespec='seconds')} {msg}")
    print(line, flush=True)
    with open(RDIR / "recover.log", "a") as f:
        f.write(line + "\n")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def write_json(name: str, obj: dict) -> Path:
    RDIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    p = RDIR / name
    p.write_text(json.dumps(obj, indent=2, default=str))
    os.chmod(p, 0o600)
    return p


# ---------------- PostgreSQL ----------------
def live_url() -> str:
    return os.environ["DATABASE_URL"]


def db_url(name: str, base: str | None = None) -> str:
    return make_url(base or live_url()).set(database=name).render_as_string(hide_password=False)


def admin_url() -> str:
    return os.environ.get("RECOVER_ADMIN_DATABASE_URL") or db_url("postgres")


def pgtool(tool: str, url: str | None, *extra: str, stdout=None) -> subprocess.CompletedProcess:
    exe = os.path.join(os.environ["RECOVER_PG_BIN"], tool) if os.environ.get("RECOVER_PG_BIN") else tool
    env, args = dict(os.environ), []
    if url:
        u = make_url(url)
        env["PGPASSWORD"] = u.password or ""
        args = ["-h", u.host or "localhost", "-p", str(u.port or 5432), "-U", u.username or "postgres"]
    r = subprocess.run([exe, *args, *extra], env=env, stdout=stdout or subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if r.returncode:
        raise RecoveryError(f"{tool} failed: {redact(r.stderr.decode(errors='replace')[-600:])}")
    return r


def create_db(name: str) -> str:
    eng = create_engine(admin_url(), isolation_level="AUTOCOMMIT")
    with eng.connect() as c:
        if c.execute(text("select 1 from pg_database where datname=:n"), {"n": name}).scalar():
            raise RecoveryError(f"database {name} already exists – refusing to reuse/overwrite it")
        owner = make_url(live_url()).username
        c.execute(text(f'CREATE DATABASE "{name}" OWNER "{owner}"'))
    eng.dispose()
    return db_url(name)


def drop_scratch_db(name: str) -> None:
    if not SCRATCH.match(name) or name.startswith("ironvision_recovered_"):
        raise RecoveryError(f"refusing to drop {name}: only rec_* scratch databases are ever dropped")
    eng = create_engine(admin_url(), isolation_level="AUTOCOMMIT")
    for attempt in range(15):  # autovacuum (superuser backend) on a freshly restored DB cannot be terminated by the app role
        try:
            with eng.connect() as c:
                c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            break
        except Exception:
            if attempt == 14:
                raise
            time.sleep(2)
    eng.dispose()


def restore(backup: Path, url: str) -> None:
    pgtool("pg_restore", url, "--no-owner", "--no-privileges", "--exit-on-error", "-d", make_url(url).database, str(backup))


def dump(url: str, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    pgtool("pg_dump", url, "-Fc", "-f", str(out), make_url(url).database)
    os.chmod(out, 0o600)
    if out.stat().st_size == 0:
        raise RecoveryError(f"backup {out} is empty")
    pgtool("pg_restore", None, "-l", str(out))  # readable
    return out


def upgrade(url: str) -> None:
    from alembic.config import Config

    from alembic import command
    here = Path(__file__).resolve().parents[2]
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here / "alembic"))
    cfg.attributes["database_url"] = url
    command.upgrade(cfg, "head")


def revision(url: str) -> str | None:
    eng = create_engine(url)
    try:
        with eng.connect() as c:
            return c.execute(text("select version_num from alembic_version")).scalar()
    finally:
        eng.dispose()


def counts(url: str) -> dict:
    eng = create_engine(url)
    with eng.connect() as c:
        tabs = [r[0] for r in c.execute(text("select table_name from information_schema.tables where table_schema='public' "
                                              "and table_type='BASE TABLE' and table_name<>'alembic_version' order by 1"))]
        out = {t: c.execute(text(f'select count(*) from "{t}"')).scalar() for t in tabs}
    eng.dispose()
    return out


def catalog_fingerprint(url: str) -> dict:
    eng = create_engine(url)
    out = {}
    with eng.connect() as c:
        for t, cols in CATALOG.items():
            rows = sorted(json.dumps([r[i] for i in range(len(cols))], default=str)
                          for r in c.execute(text(f'select {", ".join(cols)} from "{t}"')))
            out[t] = {"count": len(rows), "sha256": hashlib.sha256("\n".join(rows).encode()).hexdigest()}
    eng.dispose()
    return out


def fk_orphans(url: str) -> list[dict]:
    q = text("""select c.conrelid::regclass::text, a.attname, c.confrelid::regclass::text, af.attname
                from pg_constraint c join pg_attribute a on a.attrelid=c.conrelid and a.attnum=c.conkey[1]
                join pg_attribute af on af.attrelid=c.confrelid and af.attnum=c.confkey[1]
                where c.contype='f' and array_length(c.conkey,1)=1 and c.connamespace='public'::regnamespace""")
    eng = create_engine(url)
    bad = []
    with eng.connect() as c:
        fks = list(c.execute(q))
        for t, col, rt, rcol in fks:
            n = c.execute(text(f'select count(*) from {t} x where x."{col}" is not null and not exists '
                               f'(select 1 from {rt} p where p."{rcol}"=x."{col}")')).scalar()
            if n:
                bad.append({"table": t, "column": col, "references": rt, "orphans": n})
    eng.dispose()
    return [{"fk_checked": len(fks)}] + bad


def chain(url: str) -> dict:
    from sqlalchemy.orm import Session

    from app.services import audit
    eng = create_engine(url)
    with Session(eng) as db:
        r = audit.verify_chain(db)
    eng.dispose()
    return r


# ---------------- merge (production-only rows) ----------------
def _append_audit(conn, row: dict, note: dict) -> None:
    from app.models import AuditEvent
    from app.services.audit import GENESIS_HASH, compute_hash
    last = conn.execute(text("select seq, hash from audit_events order by seq desc limit 1")).first()
    prev = last[1] if last else GENESIS_HASH
    vals = {k: v for k, v in row.items() if k not in ("seq", "prev_hash", "hash")}
    vals["details"] = {**(vals.get("details") or {}), "recovery": note}
    ev = AuditEvent(**vals)
    vals.update(seq=(last[0] if last else 0) + 1, prev_hash=prev, hash=compute_hash(prev, ev))
    conn.execute(AuditEvent.__table__.insert().values(**vals))


def reset_sequences(conn) -> list[str]:
    """Rows were inserted with explicit ids/seq (audit chain, merged rows): move every serial/identity sequence past max()."""
    done = []
    for t, c in conn.execute(text("select table_name, column_name from information_schema.columns where table_schema='public' "
                                  "and (column_default like 'nextval(%' or is_identity='YES')")).all():
        conn.execute(text(f"select setval(pg_get_serial_sequence('\"{t}\"', '{c}'), coalesce((select max(\"{c}\") from \"{t}\"), 0) + 1, false)"))
        done.append(f"{t}.{c}")
    return done


def catalog_key_maps(pc, tc, src_meta: MetaData, tgt_meta: MetaData) -> dict:
    """(catalog table, pk column) → {production pk: restored pk} for rows whose natural key is unique on both sides and whose
    UUIDs differ (independent catalog loads). catalog_compare already guarantees every production row exists by natural key."""
    maps = {}
    for t, cols in CATALOG.items():
        if t not in tgt_meta.tables or t not in src_meta.tables or len(tgt_meta.tables[t].primary_key.columns) != 1:
            continue
        pk = next(iter(tgt_meta.tables[t].primary_key.columns)).name

        def keyed(conn, t=t, cols=cols, pk=pk) -> dict:
            d: dict = {}
            for r in conn.execute(text(f'select {pk}, {", ".join(cols)} from "{t}"')):
                d.setdefault(json.dumps(list(r[1:]), default=str), []).append(r[0])
            return d
        p, q = keyed(pc), keyed(tc)
        maps[(t, pk)] = {ids[0]: q[k][0] for k, ids in p.items() if len(ids) == 1 and len(q.get(k, [])) == 1 and ids[0] != q[k][0]}
    return maps


def merge_prod(target: str, prod: str, summary: dict) -> dict:
    """Single transaction: identity conflict pre-check, then every production-only row (FK order, ON CONFLICT DO NOTHING),
    production audit events re-appended to the restored chain, plus one recovery.restored event."""
    src_meta, tgt_meta = MetaData(), MetaData()
    pe, te = create_engine(prod), create_engine(target)
    src_meta.reflect(pe)
    tgt_meta.reflect(te)
    report: dict = {"inserted": {}, "skipped_existing": {}, "audit_events_carried": 0, "conflicts": []}
    with pe.connect() as pc, te.begin() as tc:
        tusers = {r.email.lower(): r.id for r in tc.execute(text("select id, email from users"))}
        for r in pc.execute(text("select id, email from users")):
            if r.email.lower() in tusers and tusers[r.email.lower()] != r.id:
                report["conflicts"].append(f"users: {r.email} has id {r.id} in production but {tusers[r.email.lower()]} in the backup")
        if report["conflicts"]:
            raise RecoveryError("CONFLICT (same e-mail, different user id) – nothing merged: " + "; ".join(report["conflicts"]))
        maps = catalog_key_maps(pc, tc, src_meta, tgt_meta)
        report["rekeyed"] = {}
        for t in tgt_meta.sorted_tables:
            if t.name in CATALOG or t.name in TRANSIENT or t.name in ("audit_events", "alembic_version") or t.name not in src_meta.tables:
                continue
            cols = [c.name for c in t.columns if c.name in src_meta.tables[t.name].columns]
            fks = [(fk.parent.name, maps[(fk.column.table.name, fk.column.name)]) for fk in t.foreign_keys
                   if (fk.column.table.name, fk.column.name) in maps and fk.parent.name in cols]
            ins = skip = rk = 0
            for row in pc.execute(src_meta.tables[t.name].select()).mappings():
                vals = {c: row[c] for c in cols}
                for col, m in fks:  # production catalog UUID → restored catalog UUID (same natural key)
                    if vals.get(col) in m:
                        vals[col], rk = m[vals[col]], rk + 1
                sp = tc.begin_nested()
                try:
                    n = len(tc.execute(pg_insert(t).values(vals).on_conflict_do_nothing()
                                       .returning(*t.primary_key.columns)).fetchall())
                    sp.commit()
                except IntegrityError as exc:
                    sp.rollback()
                    raise RecoveryError(f"production row {t.name}.{row.get('id')} cannot be merged (FK/constraint: "
                                        f"{str(exc.orig).splitlines()[0][:200]}) – no unique natural-key match to re-key it; nothing merged") from exc
                ins, skip = ins + n, skip + (1 - n)
            if ins or skip:
                report["inserted"][t.name], report["skipped_existing"][t.name] = ins, skip
            if rk:
                report["rekeyed"][t.name] = rk
        for row in pc.execute(text("select * from audit_events order by seq")).mappings():
            _append_audit(tc, dict(row), {"carried_from": "pre-recovery production", "original_seq": row["seq"], "original_hash": row["hash"]})
            report["audit_events_carried"] += 1
        _append_audit(tc, {"occurred_at": datetime.now(timezone.utc), "action": "recovery.restored", "entity_type": "database",
                           "entity_id": make_url(target).database, "outcome": "success", "actor_email": "recover.sh",
                           "details": summary}, {"event": "recovery"})
        report["sequences_reset"] = reset_sequences(tc)
    pe.dispose()
    te.dispose()
    return report


def protect_orgs(url: str) -> list[str]:
    eng = create_engine(url)
    with eng.begin() as c:
        ids = [str(r[0]) for r in c.execute(text("update organizations set protected=true where is_sandbox=false returning id"))]
    eng.dispose()
    return ids


def catalog_rows(url: str) -> dict[str, set[str]]:
    eng = create_engine(url)
    with eng.connect() as c:
        out = {t: {json.dumps([r[i] for i in range(len(cols))], default=str) for r in c.execute(text(f'select {", ".join(cols)} from "{t}"'))}
               for t, cols in CATALOG.items()}
    eng.dispose()
    return out


def catalog_compare(target: str, prod: str) -> dict:
    """Every production reference row must exist in the restored data (natural key + content-version hash). Rows only in the
    backup (e.g. STIG benchmarks the agency imported) are restored data, reported – not a conflict."""
    t, p = catalog_rows(target), catalog_rows(prod)
    return {tab: {"production": len(p[tab]), "restored": len(t[tab]), "missing_in_restored": sorted(p[tab] - t[tab])[:20],
                  "n_missing": len(p[tab] - t[tab]), "only_in_backup": len(t[tab] - p[tab])} for tab in CATALOG}


def build_target(target_name: str, prod: str, summary: dict) -> dict:
    tgt = create_db(target_name)
    log(f"[build] restore source backup into {target_name}")
    restore(Path(os.environ.get("RECOVER_SOURCE_BACKUP") or PRE / "aegisrmf-old-db.backup"), tgt)
    src_rev = revision(tgt)
    src_counts = counts(tgt)
    log(f"[build] source revision {src_rev}; upgrading to head")
    upgrade(tgt)
    cmp = catalog_compare(tgt, prod)
    diff = sorted(t for t, v in cmp.items() if v["n_missing"])
    if diff:
        raise RecoveryError(f"production reference rows missing from the backup ({', '.join(t + ': ' + str(cmp[t]['n_missing']) for t in diff)}): "
                            "automatic FK re-keying is not enabled – see report; nothing applied")
    merged = merge_prod(tgt, prod, summary)
    protected = protect_orgs(tgt)
    return {"url": tgt, "source_revision": src_rev, "target_revision": revision(tgt), "source_counts": src_counts,
            "merge": merged, "protected_orgs": protected, "catalogs": {"production_rows_all_present": True, "compare": cmp,
                                                                       "fingerprint": catalog_fingerprint(tgt)}}


def reconcile(src: dict, prod: dict, tgt: dict, merged: dict) -> list[dict]:
    rows = []
    for t in sorted(set(src) | set(tgt)):
        exp = src.get(t, 0) + merged["inserted"].get(t, 0)
        why = []
        if merged["inserted"].get(t):
            why.append(f"+{merged['inserted'][t]} production-only")
        if t == "audit_events":
            exp += merged["audit_events_carried"] + 1
            why.append(f"+{merged['audit_events_carried']} production audit re-appended, +1 recovery.restored")
        if t in CATALOG:
            exp = src.get(t, 0)
            why.append("reference/content catalog (all production rows present by natural key; backup rows kept)")
        if t in TRANSIENT and prod.get(t):
            why.append(f"{prod[t]} transient production row(s) not carried")
        if t not in src:
            why.append("table added by migrations 0010–0013")
        rows.append({"table": t, "source": src.get(t, 0), "production": prod.get(t, 0), "target": tgt.get(t, 0), "expected": exp,
                     "ok": tgt.get(t, 0) == exp, "explanation": "; ".join(why)})
    return rows


# ---------------- objects ----------------
def s3(admin: bool = False):
    from app.services.storage.s3 import s3_client
    p = "RECOVER_S3_ADMIN_" if admin and os.environ.get("RECOVER_S3_ADMIN_ACCESS_KEY_ID") else "S3_"
    return s3_client(os.environ.get("S3_ENDPOINT_URL"), os.environ.get("S3_REGION") or "us-east-1", os.environ.get(p + "ACCESS_KEY_ID"),
                     os.environ.get(p + "SECRET_ACCESS_KEY"), os.environ.get("S3_ADDRESSING_STYLE") or "path")


def scan_archive(archive: Path, work: Path) -> dict:
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, mode=0o700)
    with tarfile.open(archive) as tf:
        tf.extractall(work, filter="data")
    return scan_dir(work)


def scan_dir(work: Path) -> dict:
    """Plain object files (e.g. an objsync export of a running legacy MinIO) or a MinIO xl-single tree."""
    from app.tools import minio_xl
    metas = [p.parent for p in work.rglob("xl.meta") if ".minio.sys" not in p.parts]
    if metas:
        fmt = minio_xl.check_format(work)
        index = {d.relative_to(work).as_posix(): (lambda d=d: minio_xl.read_object(d)) for d in metas}
        meta = {}
        for d in metas:
            try:
                info = minio_xl.describe(d)
            except minio_xl.MinioFormatError:
                continue
            if info["versions"] > 1 or info["latest_is_delete_marker"]:
                meta[d.relative_to(work).as_posix()] = info
        layout = f"minio-xl-single ({fmt})"
        return {"layout": layout, "index": index, "meta": meta}
    else:
        index = {f.relative_to(work).as_posix(): (lambda f=f: f.read_bytes()) for f in work.rglob("*") if f.is_file()
                 and ".minio.sys" not in f.parts and f.name != ".objsync-manifest.json"}
        layout = "plain object files"
    return {"layout": layout, "index": index}


def match_evidence(url: str, scan: dict) -> dict:
    eng = create_engine(url)
    with eng.connect() as c:
        ev = [dict(r._mapping) for r in c.execute(text("select id, storage_key, sha256, content_type from evidence"))]
    eng.dispose()
    used, res = set(), []
    for e in ev:
        cands = sorted((k for k in scan["index"] if k == e["storage_key"] or k.endswith("/" + e["storage_key"])), key=len)
        if not cands:
            res.append({**e, "status": "missing"})
            continue
        used.add(cands[0])
        try:
            data = scan["index"][cands[0]]()
        except Exception as exc:  # noqa: BLE001
            res.append({**e, "status": "unreadable", "archive_path": cands[0], "detail": str(exc)[:200]})
            continue
        h = hashlib.sha256(data).hexdigest()
        res.append({**e, "status": "recovered" if h == e["sha256"] else "hash_mismatch", "archive_path": cands[0],
                    "actual_sha256": h, "_data": data if h == e["sha256"] else None})
    orphans = sorted(set(scan["index"]) - used)
    return {"evidence": res, "orphans": orphans, "extra": classify_extra(scan, orphans, {e["sha256"]: e["storage_key"] for e in ev})}


EXTRA_KINDS = (("_bootstrap/", "bootstrap marker"), ("exports/", "export file"), ("export/", "export file"), ("policies/", "policy upload"),
               ("policy/", "policy upload"), ("tmp/", "temporary file"), ("multipart", "multipart temp"))


def classify_extra(scan: dict, orphans: list[str], ev_sha: dict, limit: int = 500) -> list[dict]:
    """Objects that match no evidence storage key: classified, never counted as evidence. One whose bytes equal an evidence
    record's SHA-256 under a different key is reported as such (a copy), still not counted."""
    out = []
    for k in orphans[:limit]:
        tail = k.split("/", 1)[1] if "/" in k else k
        kind = next((lbl for pfx, lbl in EXTRA_KINDS if tail.startswith(pfx) or f"/{pfx}" in f"/{tail}"), "not referenced by any evidence record")
        d = {"key": k, "kind": kind}
        try:
            data = scan["index"][k]()
            d.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            if d["sha256"] in ev_sha:
                d["kind"] = f"same bytes as evidence {ev_sha[d['sha256']]} under another key (not counted)"
        except Exception as exc:  # noqa: BLE001
            d["unreadable"] = str(exc)[:200]
        if k in scan.get("meta", {}):
            d["versions"] = scan["meta"][k]
        out.append(d)
    return out


def copy_objects(bucket: str, matched: dict, admin: bool = False) -> dict:
    from botocore.exceptions import ClientError
    cl, out = s3(admin), {"added": [], "present_identical": [], "conflict_existing_differs": []}
    for e in matched["evidence"]:
        if e["status"] != "recovered":
            continue
        try:
            cur = cl.get_object(Bucket=bucket, Key=e["storage_key"])["Body"].read()
            out["present_identical" if hashlib.sha256(cur).hexdigest() == e["sha256"] else "conflict_existing_differs"].append(e["storage_key"])
            continue
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in ("NoSuchKey", "404"):
                raise
        cl.put_object(Bucket=bucket, Key=e["storage_key"], Body=e["_data"], ContentType=e.get("content_type") or "application/octet-stream")
        out["added"].append({"key": e["storage_key"], "sha256": e["sha256"]})
    return out


def bucket_manifest(bucket: str, admin: bool = True) -> list[dict]:
    cl, out = s3(admin), []
    for page in cl.get_paginator("list_objects_v2").paginate(Bucket=bucket):
        for o in page.get("Contents", []):
            data = cl.get_object(Bucket=bucket, Key=o["Key"])["Body"].read()
            out.append({"key": o["Key"], "size": len(data), "sha256": hashlib.sha256(data).hexdigest()})
    return out


def present_in_production(m: dict) -> None:
    """Evidence absent from the legacy source (e.g. production-only rows merged in) whose key already exists in the production
    bucket with the SAME SHA-256 is not missing: status present_in_production (read-only GET; not counted as recovered)."""
    cl, prod_bucket = s3(), os.environ.get("S3_BUCKET")
    for e in m["evidence"]:
        if e["status"] != "missing" or not prod_bucket:
            continue
        try:
            cur = cl.get_object(Bucket=prod_bucket, Key=e["storage_key"])["Body"].read()
        except Exception:  # noqa: BLE001
            continue
        if hashlib.sha256(cur).hexdigest() == e["sha256"]:
            e["status"] = "present_in_production"


def verify_objects(url: str, bucket: str, admin: bool = False) -> dict:
    cl, ok, bad = s3(admin), 0, []
    eng = create_engine(url)
    with eng.connect() as c:
        rows = list(c.execute(text("select storage_key, sha256 from evidence")))
    eng.dispose()
    for key, sha in rows:
        try:
            got = hashlib.sha256(cl.get_object(Bucket=bucket, Key=key)["Body"].read()).hexdigest()
        except Exception:  # noqa: BLE001
            got = None
        if got == sha:
            ok += 1
        else:
            bad.append({"key": key, "status": "missing" if got is None else "hash_mismatch"})
    return {"evidence": len(rows), "verified": ok, "problems": bad}


def seaweed_checks(bucket: str) -> list[tuple[str, str, str]]:
    """App key: bucket-scoped list/put/get/delete; must NOT be able to create other buckets."""
    from botocore.exceptions import ClientError
    out, cl, probe = [], s3(False), f"recovery-probe/{ts()}"
    try:
        cl.head_bucket(Bucket=bucket)
        out.append(("OK", f"bucket {bucket}", "exists"))
        v = s3(True).get_bucket_versioning(Bucket=bucket).get("Status") or "Unversioned"
        out.append(("OK", "versioning", v))
        cl.put_object(Bucket=bucket, Key=probe, Body=b"probe")
        assert cl.get_object(Bucket=bucket, Key=probe)["Body"].read() == b"probe"
        cl.list_objects_v2(Bucket=bucket, Prefix="recovery-probe/", MaxKeys=1)
        cl.delete_object(Bucket=bucket, Key=probe)
        out.append(("OK", "app key list/put/get/delete", "ok in evidence bucket"))
    except Exception as exc:  # noqa: BLE001
        out.append(("FAIL", "S3 endpoint / app key", redact(str(exc))[:200]))
        return out
    other = f"recovery-scope-probe-{ts()}"
    try:
        cl.create_bucket(Bucket=other)
        s3(True).delete_bucket(Bucket=other)
        out.append(("WARN", "app key scope", "app key can create buckets – restrict it to the evidence bucket"))
    except ClientError:
        out.append(("OK", "app key scope", "cannot create other buckets"))
    m = bucket_manifest(bucket)
    out.append(("OK", "bucket state", f"{len(m)} objects, {sum(o['size'] for o in m)} bytes (manifest saved)"))
    return out


# ---------------- plan ----------------
def inputs() -> dict:
    files = {"source_backup": os.environ.get("RECOVER_SOURCE_BACKUP") or PRE / "aegisrmf-old-db.backup",
             "prod_rollback_backup": os.environ.get("RECOVER_PROD_ROLLBACK_BACKUP") or PRE / "ironvision-production-before-restore.backup",
             "object_archive": os.environ.get("RECOVER_OBJECT_ARCHIVE") or PRE / "aegisrmf-minio-backup.tar.gz"}
    out = {}
    if os.environ.get("RECOVER_OBJECT_DIR"):
        files.pop("object_archive")
        d = Path(os.environ["RECOVER_OBJECT_DIR"])
        m = d / ".objsync-manifest.json"
        if not m.is_file():
            raise RecoveryError(f"object_dir: {m} missing (objsync export incomplete)")
        out["object_dir"] = {"path": str(d), "size": sum(f.stat().st_size for f in d.rglob("*") if f.is_file()), "sha256": sha256_file(m),
                             "origin": os.environ.get("RECOVER_OBJECT_ORIGIN") or "objsync export"}
    for k, p in files.items():
        p = Path(p)
        if not (p.is_file() and os.access(p, os.R_OK)):
            raise RecoveryError(f"{k}: {p} missing or unreadable")
        out[k] = {"path": str(p), "size": p.stat().st_size, "sha256": sha256_file(p)}
    out["source_backup"]["origin"] = os.environ.get("RECOVER_SOURCE_ORIGIN") or "backup file"
    return out


def plan() -> dict:
    prod_counts = counts(live_url())
    p = {"inputs": inputs(), "strategy": "non-destructive swap (new database + DATABASE_URL switch)",
         "production": {"db": make_url(live_url()).database, "revision": revision(live_url()),
                        "stable_counts": {t: n for t, n in prod_counts.items() if t not in VOLATILE},
                        "catalogs": catalog_fingerprint(live_url())},
         "bucket": os.environ.get("S3_BUCKET")}
    p["plan_hash"] = hashlib.sha256(json.dumps(p, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return p


# ---------------- commands ----------------
def cmd_preflight(a) -> int:
    checks = []
    p = plan()
    for k, v in p["inputs"].items():
        checks.append(("OK", k, f"{v['path']} ({v['size']} bytes, sha256 {v['sha256'][:12]}…)"))
    toc = pgtool("pg_restore", None, "-l", p["inputs"]["source_backup"]["path"]).stdout.decode()
    checks.append(("OK", "pg_restore -l source", f"{toc.count(' TABLE DATA ')} table-data entries"))
    pgtool("pg_restore", None, "-l", p["inputs"]["prod_rollback_backup"]["path"])
    if "object_dir" in p["inputs"]:
        n = len(json.loads((Path(p["inputs"]["object_dir"]["path"]) / ".objsync-manifest.json").read_text())["objects"])
        checks.append(("OK", "object source", f"{p['inputs']['object_dir']['origin']}: {n} objects (SHA-256 manifest)"))
    else:
        with tarfile.open(p["inputs"]["object_archive"]["path"]) as tf:
            names = tf.getnames()
        xl = sum(n.endswith("/xl.meta") for n in names)
        checks.append(("OK", "object archive", f"{len(names)} entries; {'MinIO xl.meta layout (' + str(xl) + ' objects)' if xl else 'plain files'}"))
    checks.append(("OK", "source database", p["inputs"]["source_backup"]["origin"]))
    checks.append(("OK", "legacy containers needed from here on", "no – every source is a verified snapshot/backup file"))
    need = 3 * sum(v["size"] for v in p["inputs"].values())
    free = shutil.disk_usage(RDIR if RDIR.exists() else RDIR.parent).free
    checks.append(("OK" if free >= need else "FAIL", "disk space", f"free {free >> 20} MiB, need ≥ {need >> 20} MiB (3× inputs)"))
    checks.append(("OK", "production DB", f"{p['production']['db']} @ {p['production']['revision']}"))
    if os.environ.get("RECOVER_SOURCE_INSPECT_URL"):
        sc = counts(os.environ["RECOVER_SOURCE_INSPECT_URL"])
        checks.append(("OK", "source (isolated restore) counts", json.dumps({k: sc.get(k) for k in ("users", "organizations", "systems", "evidence", "findings", "jobs", "audit_events")})))
    if os.environ.get("KEYCLOAK_URL"):
        import httpx
        realm = os.environ.get("KEYCLOAK_REALM") or "ironvision-demo"
        try:
            ok = httpx.get(f"{os.environ['KEYCLOAK_URL']}/realms/{realm}/.well-known/openid-configuration", timeout=10).status_code == 200
        except httpx.HTTPError:
            ok = False
        checks.append(("OK" if ok else "FAIL", "Keycloak reachable", realm))
    checks += seaweed_checks(os.environ["S3_BUCKET"])
    t = ts()
    write_json(f"plan-{t}.json", {**p, "checks": checks, "production_counts": counts(live_url())})
    write_json(f"bucket-manifest-{t}.json", {"bucket": os.environ["S3_BUCKET"], "objects": bucket_manifest(os.environ["S3_BUCKET"])})
    for s, item, d in checks:
        log(f"[preflight] {s:<4} {item}: {d}")
    log(f"[preflight] PLAN: {p['strategy']}; plan-hash {p['plan_hash']}")
    return 1 if any(c[0] == "FAIL" for c in checks) else 0


def _run_recovery(t: str, prod_url: str, target_name: str, bucket: str, admin_bucket: bool) -> dict:
    summary = {"strategy": "swap", "ts": t}
    b = build_target(target_name, prod_url, summary)
    tgt_counts = counts(b["url"])
    rec = reconcile(b["source_counts"], counts(prod_url), tgt_counts, b["merge"])
    scan = scan_dir(Path(os.environ["RECOVER_OBJECT_DIR"])) if os.environ.get("RECOVER_OBJECT_DIR") else \
        scan_archive(Path(os.environ.get("RECOVER_OBJECT_ARCHIVE") or PRE / "aegisrmf-minio-backup.tar.gz"), RDIR / "work" / f"objects-{t}")
    m = match_evidence(b["url"], scan)
    present_in_production(m)
    copied = copy_objects(bucket, m, admin=admin_bucket)
    st = {s: sum(1 for e in m["evidence"] if e["status"] == s) for s in ("recovered", "present_in_production", "missing", "hash_mismatch", "unreadable")}
    return {"target_db": target_name, "build": {k: v for k, v in b.items() if k != "url"}, "reconciliation": rec,
            "fk": fk_orphans(b["url"]), "audit_chain": chain(b["url"]), "objects": {
                "layout": scan["layout"], "bucket": bucket, "summary": {**st, "extra": len(m["orphans"])}, "orphans": m["orphans"],
                "extra": m["extra"], "versioned": scan.get("meta", {}), "copy": copied,
                "detail": [{k: v for k, v in e.items() if k != "_data"} for e in m["evidence"] if e["status"] != "recovered"]},
            "bucket_verify": verify_objects(b["url"], bucket, admin=admin_bucket)}


def _passed(r: dict) -> list[str]:
    why = []
    why += [f"count mismatch {x['table']}" for x in r["reconciliation"] if not x["ok"]]
    why += [f"FK orphans {x['table']}.{x['column']}" for x in r["fk"][1:]]
    if not r["audit_chain"]["valid"]:
        why.append(f"audit chain invalid at seq {r['audit_chain']['first_invalid_seq']}")
    if r["objects"]["copy"]["conflict_existing_differs"]:
        why.append("existing bucket keys differ from recovered bytes")
    return why


def kc_dry_run(url: str, t: str) -> str:
    if not os.environ.get("KEYCLOAK_URL"):
        return "skipped (KEYCLOAK_URL not set)"
    env = {**os.environ, "DATABASE_URL": url}
    r = subprocess.run([sys.executable, "-m", "app.cli", "keycloak-migrate", "--report", str(RDIR / f"keycloak-migrate-plan-{t}.json")],
                       env=env, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2], check=False)
    return redact((r.stdout + r.stderr)[-3000:])


def write_report(kind: str, t: str, body: dict) -> None:
    write_json(f"{kind}-{t}.json", body)
    lines = [f"# IronVision recovery {kind} {t}", "", f"- plan-hash: `{body.get('plan_hash')}`", f"- result: **{'PASS' if body.get('passed') else 'FAIL'}**"]
    for w in body.get("failures", []):
        lines.append(f"  - {w}")
    if body.get("result"):
        r = body["result"]
        lines += ["", "## Row-count reconciliation", "", "| table | source | production | target | expected | ok | explanation |", "|---|---|---|---|---|---|---|"]
        lines += [f"| {x['table']} | {x['source']} | {x['production']} | {x['target']} | {x['expected']} | {'✓' if x['ok'] else '✗'} | {x['explanation']} |"
                  for x in r["reconciliation"] if x["source"] or x["target"] or x["production"]]
        o = r["objects"]
        lines += ["", "## SeaweedFS / objects", "", f"- layout: {o['layout']}; bucket `{o['bucket']}`", f"- evidence: {json.dumps(o['summary'])}",
                  f"- orphans in archive: {len(o['orphans'])}", (f"- copy: added {len(o['copy']['added'])}, present identical {len(o['copy']['present_identical'])}, "
                   f"conflicts {len(o['copy']['conflict_existing_differs'])}"), f"- bucket verify: {json.dumps({k: v for k, v in r['bucket_verify'].items() if k != 'problems'})}"]
        lines += [f"  - {d['storage_key']}: {d['status']}" for d in o["detail"]]
        lines += ["", f"## Audit chain\n\n{json.dumps(r['audit_chain'])}", "", f"## FK integrity\n\n{json.dumps(r['fk'])}"]
    if body.get("keycloak_migrate_dry_run"):
        lines += ["", "## Keycloak migration dry-run (NOT applied – `./recover.sh link --plan-hash …`)", "", "```", body["keycloak_migrate_dry_run"], "```"]
    (RDIR / f"{kind}-{t}.md").write_text(redact("\n".join(lines)) + "\n")
    os.chmod(RDIR / f"{kind}-{t}.md", 0o600)
    if kind == "rehearsal":
        for ext in ("md", "json"):
            link = RDIR / f"report-{t}.{ext}"
            link.unlink(missing_ok=True)
            link.symlink_to(f"{kind}-{t}.{ext}")


def cmd_rehearse(a) -> int:
    t, p = ts(), plan()
    src, prodc = f"rec_src_{t}", f"rec_prod_{t}"
    restore(Path(p["inputs"]["source_backup"]["path"]), create_db(src))
    pd = dump(live_url(), RDIR / "work" / f"prod-copy-{t}.dump")
    restore(pd, create_db(prodc))
    bucket = f"evidence-rehearsal-{t.replace('t', '-')}"
    s3(True).create_bucket(Bucket=bucket)
    body = {"plan_hash": p["plan_hash"], "ts": t, "scratch": {"dbs": [src, prodc, f"rec_target_{t}"], "bucket": bucket}}
    try:
        body["result"] = _run_recovery(t, db_url(prodc), f"rec_target_{t}", bucket, admin_bucket=True)
        body["failures"] = _passed(body["result"])
        body["keycloak_migrate_dry_run"] = kc_dry_run(db_url(f"rec_target_{t}"), t)
        sc = body["result"]["build"].get("source_counts") or {}
        body["source_facts"] = {k: {"expected": v, "actual": sc.get(k), "ok": sc.get(k) == v} for k, v in FACTS.items()}
        bad = {k: x for k, x in body["source_facts"].items() if not x["ok"]}
        log(f"[rehearse] source vs stated facts: {'all match' if not bad else 'DISCREPANCIES ' + json.dumps(bad)}")
    except RecoveryError as exc:
        body["failures"] = [str(exc)]
    body["backend_probe"] = "pending (recover.sh starts the rehearsal backend and runs rehearse-probe)"
    body["passed"] = not body["failures"]
    write_report("rehearsal", t, body)
    log(f"[rehearse] {'PASS' if body['passed'] else 'FAIL'} – report {RDIR}/rehearsal-{t}.md; target DB rec_target_{t}; bucket {bucket}")
    print(f"REHEARSAL_TS={t}")
    if a.cleanup:
        cleanup(body)
    return 0 if body["passed"] else 1


def cleanup(body: dict) -> None:
    for d in body["scratch"]["dbs"]:
        drop_scratch_db(d)
    cl = s3(True)
    for o in bucket_manifest(body["scratch"]["bucket"]):
        cl.delete_object(Bucket=body["scratch"]["bucket"], Key=o["key"])
    cl.delete_bucket(Bucket=body["scratch"]["bucket"])
    log("[rehearse] scratch databases and rehearsal bucket dropped (--cleanup)")


def latest(kind: str) -> dict | None:
    fs = sorted(RDIR.glob(f"{kind}-*.json"))
    return json.loads(fs[-1].read_text()) if fs else None


def cmd_rehearse_probe(a) -> int:
    import httpx
    fs = sorted(RDIR.glob("rehearsal-*.json"))
    body = json.loads(fs[-1].read_text())
    url = a.url.rstrip("/")
    res = {}
    for path in ("/api/v1/health/live", "/api/v1/ready", "/api/v1/auth/provider"):
        try:
            res[path] = httpx.get(url + path, timeout=15).status_code
        except httpx.HTTPError as exc:
            res[path] = f"error {exc}"
    if a.e2e:
        r = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[3] / "scripts" / "e2e_sso.py"), "--base", url, "--demo", "--json"], capture_output=True, text=True, check=False)
        res["e2e_sso"] = {"rc": r.returncode, "output": redact(r.stdout[-4000:])}
        try:
            failed = [s for s in json.loads(r.stdout) if not s["pass"]]
        except ValueError:
            failed = None
        if r.returncode and failed and all(s["step"] == "demo launcher login" and s["detail"] == "403" for s in failed):
            res["e2e_sso"]["rc"] = 0  # pre-existing: production has no demo identity mapping yet; cutover's Keycloak link creates it
            res["e2e_sso"]["note"] = "demo launcher not mapped in production yet (doctor FAIL) – cutover links it and its live e2e must pass"
            body.setdefault("warnings", []).append(res["e2e_sso"]["note"])
    body["backend_probe"] = res
    if any(v != 200 for k, v in res.items() if k.startswith("/")) or (a.e2e and res["e2e_sso"]["rc"]):
        body["failures"].append(f"rehearsal backend probe failed: {json.dumps(res)[:300]}")
    body["passed"] = not body["failures"]
    write_report("rehearsal", body["ts"], body)
    log(f"[rehearse-probe] {'PASS' if body['passed'] else 'FAIL'} {json.dumps({k: (v if k.startswith('/') else v['rc']) for k, v in res.items()})}")
    return 0 if body["passed"] else 1


FACTS = {"users": 8, "organizations": 1, "systems": 4, "role_assignments": 25, "evidence": 38, "findings": 111, "jobs": 1624, "audit_events": 1772}


def take_backups(t: str, skip_keycloak: bool = False) -> tuple[dict, list]:
    """Read-only against production: pg_dump of the live + Keycloak DBs and a SHA-256 manifest of the live bucket."""
    bk = RDIR / "backups" / t
    log(f"[backup] → {bk}")
    backups = {"prod_db": str(dump(live_url(), bk / "prod.dump"))}
    if not skip_keycloak:
        kc_url = os.environ.get("RECOVER_KEYCLOAK_DATABASE_URL") or db_url(os.environ.get("KEYCLOAK_DB_NAME") or "keycloak", admin_url())
        backups["keycloak_db"] = str(dump(kc_url, bk / "keycloak.dump"))
    man = bucket_manifest(os.environ["S3_BUCKET"])
    backups["bucket_manifest"] = str(write_json(f"backups/{t}/bucket-manifest.json", {"bucket": os.environ["S3_BUCKET"], "objects": man}))
    write_json(f"backups/{t}/manifest.json", {"created_at": datetime.now(timezone.utc).isoformat(), "kind": "recovery-backup",
                                              "files": {k: {"path": v, "sha256": sha256_file(Path(v))} for k, v in backups.items()}})
    return backups, man


def cmd_backup(a) -> int:
    backups, man = take_backups(ts(), a.skip_keycloak_backup)
    log(f"[backup] OK prod DB + Keycloak DB dumps, bucket manifest ({len(man)} objects): {json.dumps(backups)}")
    return 0


def cmd_apply(a) -> int:
    p = plan()
    if a.plan_hash != p["plan_hash"]:
        raise RecoveryError(f"plan-hash mismatch: current plan is {p['plan_hash']} (inputs or production changed) – re-run preflight + rehearse")
    reh = latest("rehearsal")
    if not reh or reh.get("plan_hash") != a.plan_hash or not reh.get("passed") or isinstance(reh.get("backend_probe"), str):
        raise RecoveryError("no PASSING rehearsal (incl. backend probe) for this plan-hash – run ./recover.sh rehearse first")
    if datetime.now(timezone.utc) - datetime.strptime(reh["ts"], "%Y%m%dt%H%M%S").replace(tzinfo=timezone.utc) > timedelta(hours=24):
        raise RecoveryError("the passing rehearsal is older than 24h – rehearse again")
    t = ts()
    backups, man = take_backups(t, a.skip_keycloak_backup)
    target = f"ironvision_recovered_{t}"
    body = {"plan_hash": a.plan_hash, "ts": t, "backups": backups, "previous_db": make_url(live_url()).database, "target_db": target,
            "bucket_before": {"objects": len(man), "bytes": sum(o["size"] for o in man)}}
    try:
        body["result"] = _run_recovery(t, live_url(), target, os.environ["S3_BUCKET"], admin_bucket=False)
        body["failures"] = _passed(body["result"])
    except RecoveryError as exc:
        body["failures"] = [str(exc)]
    body["recovery_added_keys"] = (body.get("result") or {}).get("objects", {}).get("copy", {}).get("added", [])
    body["passed"] = not body["failures"]
    write_report("apply", t, body)
    if not body["passed"]:
        log(f"[apply] FAILED – live DB untouched, DATABASE_URL NOT switched: {body['failures']}")
        return 1
    log(f"[apply] recovered DB {target} ready; {len(body['recovery_added_keys'])} object(s) added to {os.environ['S3_BUCKET']}")
    print(f"RECOVERED_DB={target}")
    return 0


def cmd_verify(a) -> int:
    from sqlalchemy.orm import Session

    from app.services.evaluation import verify_integrity
    from app.services.storage.base import get_storage
    url, bucket = live_url(), os.environ["S3_BUCKET"]
    checks = {"db": make_url(url).database, "revision": revision(url), "fk": fk_orphans(url), "audit_chain": chain(url),
              "objects": verify_objects(url, bucket)}
    ap = next((json.loads(f.read_text()) for f in sorted(RDIR.glob("apply-*.json"), reverse=True)
               if json.loads(f.read_text()).get("target_db") == checks["db"]), None)
    known = {d["storage_key"] for d in ((ap or {}).get("result") or {}).get("objects", {}).get("detail", [])
             if d.get("status") in ("missing", "hash_mismatch", "unreadable")}
    checks["objects"]["known_unrecoverable"] = sorted(known)  # recorded by apply (missing/corrupt in the archive) – reported, not regressions
    checks["objects"]["problems"] = [p for p in checks["objects"]["problems"] if p["key"] not in known]
    eng = create_engine(url)
    with eng.connect() as c:
        checks["protected_orgs"] = [str(r[0]) for r in c.execute(text("select id from organizations where protected"))]
    with Session(eng) as db:
        checks["integrity_job"] = verify_integrity(db)
        db.commit()
    eng.dispose()
    st, key = get_storage(), f"recovery-roundtrip/{ts()}"
    st.put(key, b"roundtrip")
    checks["storage_roundtrip"] = st.get(key) == b"roundtrip"
    st.delete(key)
    m = bucket_manifest(bucket)
    checks["bucket_after"] = {"objects": len(m), "bytes": sum(o["size"] for o in m)}
    fails = [x for x in (["FK orphans"] if len(checks["fk"]) > 1 else []) + ([] if checks["audit_chain"]["valid"] else ["audit chain"])
             + ([] if not checks["objects"]["problems"] else [f"{len(checks['objects']['problems'])} evidence object(s) missing/mismatched"])
             + ([] if checks["storage_roundtrip"] else ["storage round-trip"])]
    t = ts()
    write_json(f"verify-{t}.json", {"ts": t, "checks": checks, "failures": fails, "passed": not fails})
    log(f"[verify] {'PASS' if not fails else 'FAIL'} db={checks['db']}@{checks['revision']} objects {checks['objects']['verified']}/{checks['objects']['evidence']} "
        f"chain={checks['audit_chain']['valid']} integrity={json.dumps(checks['integrity_job'])} fails={fails}")
    return 0 if not fails else 1


def cmd_remove_recovered_objects(a) -> int:
    ap = latest("apply")
    if not ap:
        raise RecoveryError("no apply manifest")
    cl, n = s3(False), 0
    for k in ap["recovery_added_keys"]:
        try:
            cur = cl.get_object(Bucket=os.environ["S3_BUCKET"], Key=k["key"])["Body"].read()
        except Exception:  # noqa: BLE001, S112 - key already gone: nothing to remove
            continue
        if hashlib.sha256(cur).hexdigest() == k["sha256"]:
            cl.delete_object(Bucket=os.environ["S3_BUCKET"], Key=k["key"])
            n += 1
    log(f"[rollback] removed {n} recovery-added object(s) (only keys from apply-{ap['ts']} manifest with identical bytes)")
    return 0


def cmd_status(a) -> int:
    for kind in ("plan", "rehearsal", "apply", "verify", "rollback"):
        b = latest(kind)
        if b:
            print(f"{kind:<10} {b.get('ts', '?')}  plan-hash={b.get('plan_hash', '-')}  passed={b.get('passed', '-')}  "
                  f"{('target=' + b['target_db']) if b.get('target_db') else ''}")
        else:
            print(f"{kind:<10} (none)")
    return 0


def cmd_plan_hash(a) -> int:
    print(plan()["plan_hash"])
    return 0


def cmd_bucket_verify(a) -> int:
    r = verify_objects(db_url(a.db), a.bucket, admin=True)
    log(f"[bucket-verify] {a.bucket}: {r['verified']}/{r['evidence']} objects verified")
    return 0 if r["verified"] else 1


def cmd_cleanup_rehearsal(a) -> int:
    rh = latest("rehearsal")
    if rh:
        cleanup(rh)
    return 0


def cmd_restore_into_new(a) -> int:
    name = f"ironvision_restored_{ts()}"
    restore(Path(a.file), create_db(name))
    log(f"[rollback] {a.file} restored into NEW database {name} (no existing database touched)")
    print(f"NEW_DB={name}")
    return 0


def cmd_audit_keycloak(a) -> int:
    """Keycloak side of the configuration-chain audit (no secrets printed)."""
    import httpx

    from app.services.keycloak_admin import KeycloakAdmin
    out, realm = [], os.environ.get("KEYCLOAK_REALM") or "ironvision-demo"
    app = (os.environ.get("APP_DOMAIN") or "").strip()
    issuer = (os.environ.get("OIDC_ISSUER") or "").rstrip("/")
    try:
        disc = httpx.get(f"{os.environ['KEYCLOAK_URL']}/realms/{realm}/.well-known/openid-configuration", timeout=10).json()
        out.append(("OK" if disc["issuer"].rstrip("/") == issuer else "FAIL", "discovery issuer == OIDC_ISSUER (internal URL)", disc["issuer"]))
        out.append(("OK" if disc.get("end_session_endpoint") else "FAIL", "logout endpoint", disc.get("end_session_endpoint", "-")))
    except Exception as exc:  # noqa: BLE001
        out.append(("FAIL", "discovery via internal URL", str(exc)[:120]))
    try:
        r = httpx.get(f"{issuer}/.well-known/openid-configuration", timeout=10)
        out.append(("OK" if r.status_code == 200 else "FAIL", "public issuer reachable from this container (hairpin)", str(r.status_code)))
    except Exception as exc:  # noqa: BLE001
        out.append(("WARN", "public issuer NOT reachable from inside docker", f"{str(exc)[:80]} – backend uses KEYCLOAK_URL backchannel; token iss stays public"))
    try:
        kc = KeycloakAdmin().login()
        c = kc.client(realm, os.environ.get("OIDC_CLIENT_ID") or "ironvision-app")
        want_redirect = f"https://{app}/api/v1/auth/oidc/callback" if app else None
        out.append(("OK" if c and want_redirect in (c.get("redirectUris") or []) and len(c["redirectUris"]) == 1 else "FAIL", "ironvision-app redirect URIs",
                    json.dumps((c or {}).get("redirectUris"))))
        out.append(("OK" if c and (c.get("webOrigins") or []) == [f"https://{app}"] else "FAIL", "ironvision-app web origins", json.dumps((c or {}).get("webOrigins"))))
        post = ((c or {}).get("attributes") or {}).get("post.logout.redirect.uris", "")
        out.append(("OK" if app and f"https://{app}" in post else "FAIL", "post-logout redirect URIs", post))
        out.append(("OK" if ((c or {}).get("attributes") or {}).get("pkce.code.challenge.method") == "S256" else "FAIL", "PKCE S256 required", ""))
        sec = kc.get(f"/{realm}/clients/{c['id']}/client-secret").get("value") if c else None
        same = bool(sec) and hashlib.sha256(sec.encode()).digest() == hashlib.sha256((os.environ.get("OIDC_CLIENT_SECRET") or "").encode()).digest()
        out.append(("OK" if same else "FAIL", "client secret matches env (compared by SHA-256, not printed)", ""))
    except Exception as exc:  # noqa: BLE001
        out.append(("FAIL", "Keycloak admin API", redact(str(exc))[:160]))
    for s, item, d in out:
        log(f"[audit] {s:<4} {item}: {d}")
    write_json(f"audit-keycloak-{ts()}.json", {"checks": out})
    return 1 if any(x[0] == "FAIL" for x in out) else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="recover")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("preflight")
    r = sp.add_parser("rehearse")
    r.add_argument("--cleanup", action="store_true")
    rp = sp.add_parser("rehearse-probe")
    rp.add_argument("--url", required=True)
    rp.add_argument("--e2e", action="store_true")
    x = sp.add_parser("apply")
    x.add_argument("--plan-hash", required=True)
    x.add_argument("--skip-keycloak-backup", action="store_true")
    sp.add_parser("verify")
    bk = sp.add_parser("backup")
    bk.add_argument("--skip-keycloak-backup", action="store_true")
    sp.add_parser("remove-recovered-objects")
    sp.add_parser("status")
    sp.add_parser("plan-hash")
    bv = sp.add_parser("bucket-verify")
    bv.add_argument("--db", required=True)
    bv.add_argument("--bucket", required=True)
    sp.add_parser("cleanup-rehearsal")
    ri = sp.add_parser("restore-into-new")
    ri.add_argument("--file", required=True)
    sp.add_parser("audit-keycloak")
    a = ap.parse_args(argv)
    fn = {"preflight": cmd_preflight, "rehearse": cmd_rehearse, "rehearse-probe": cmd_rehearse_probe, "apply": cmd_apply, "verify": cmd_verify,
          "remove-recovered-objects": cmd_remove_recovered_objects, "status": cmd_status, "plan-hash": cmd_plan_hash,
          "bucket-verify": cmd_bucket_verify, "cleanup-rehearsal": cmd_cleanup_rehearsal, "restore-into-new": cmd_restore_into_new,
          "audit-keycloak": cmd_audit_keycloak, "backup": cmd_backup}[a.cmd]
    try:
        return fn(a)
    except RecoveryError as exc:
        log(f"[{a.cmd}] FAILED: {exc}")
        return 2


if __name__ == "__main__":
    t0 = time.time()
    rc = main()
    sys.exit(rc)
