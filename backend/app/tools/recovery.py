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
import secrets
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
SCRATCH = re.compile(r"^(rec_(src|prod|target|kc)_\d{8}t\d{6}|ironvision_recovered_\d{8}t\d{6})$")
# Part of every plan hash and recorded in every rehearsal: a plan/rehearsal produced by another tool version is refused by
# apply/cutover (bumped when rehearsal semantics change – 2026.10.17: probes run inside the rehearsal backend's namespace,
# full SSO e2e without a faked pass, per-record evidence integrity).
TOOL_VERSION = "2026.10.20-rehearsal-v7-readonly-verify"


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


def ro_engine(url: str):
    """Every session is a READ-ONLY transaction (as for the legacy reads): any INSERT/UPDATE/DELETE raises."""
    return create_engine(url, connect_args={"options": "-c default_transaction_read_only=on"})


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
    eng = ro_engine(url)
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
    eng = ro_engine(url)
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
    eng = ro_engine(url)
    with Session(eng) as db:
        r = audit.verify_chain(db)
        db.rollback()
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
    mans = objsync_manifests(work)
    return {"layout": layout, "index": index, "buckets": [json.loads(p.read_text()).get("bucket") for p in mans]}


def objsync_manifests(d: Path) -> list[Path]:
    """One bucket export (<dir>/.objsync-manifest.json) or several (<dir>/<bucket>/.objsync-manifest.json)."""
    return [d / ".objsync-manifest.json"] if (d / ".objsync-manifest.json").is_file() else sorted(d.glob("*/.objsync-manifest.json"))


def key_variants(key: str, buckets: set[str]) -> list[tuple[str, str]]:
    """Storage-key spellings seen in legacy data: exact, s3://bucket/ URL, leading '/', URL-encoded, '<bucket>/' prefix.
    A variant only locates the object – it counts as VERIFIED solely on a SHA-256 match."""
    from urllib.parse import unquote
    out, s = [(key, "exact")], key
    if s.startswith("s3://"):
        s = s[5:].split("/", 1)[1] if "/" in s[5:] else ""
        out.append((s, "s3:// URL prefix stripped"))
    if s.startswith("/"):
        s = s.lstrip("/")
        out.append((s, "leading / stripped"))
    if unquote(s) != s:
        out.append((unquote(s), "URL-decoded"))
    head, _, tail = s.partition("/")
    if tail and head in buckets:
        out.append((tail, f"bucket prefix '{head}/' stripped"))
    return out


def _locate(key: str, index: dict, buckets: set[str]) -> tuple[str | None, str | None]:
    for v, how in key_variants(key, buckets):
        if v in index:
            return v, how
        c = sorted((k for k in index if k.endswith("/" + v)), key=len)
        if c:
            return c[0], f"{how}; found under prefix {c[0][:-len(v)]}"
    return None, None


def match_evidence(url: str, scan: dict) -> dict:
    eng = create_engine(url)
    with eng.connect() as c:
        ev = [dict(r._mapping) for r in c.execute(text("select id, storage_key, sha256, content_type from evidence"))]
    eng.dispose()
    buckets = set(scan.get("buckets") or []) | {b for b in (os.environ.get("S3_BUCKET"), os.environ.get("RECOVER_LEGACY_BUCKET"), "evidence") if b}
    used, res = set(), []
    for e in ev:
        k, how = _locate(e["storage_key"], scan["index"], buckets)
        if k is None:
            res.append({**e, "status": "missing"})
            continue
        used.add(k)
        try:
            data = scan["index"][k]()
        except Exception as exc:  # noqa: BLE001
            res.append({**e, "status": "unreadable", "archive_path": k, "matched_by": how, "detail": str(exc)[:200]})
            continue
        h = hashlib.sha256(data).hexdigest()
        res.append({**e, "status": "recovered" if h == e["sha256"] else "hash_mismatch", "archive_path": k, "matched_by": how,
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


INTEGRITY = {"recovered": "VERIFIED", "present_in_production": "VERIFIED", "missing": "MISSING", "hash_mismatch": "MISMATCH",
             "unreadable": "UNREADABLE"}


def evidence_integrity(m: dict, scan: dict) -> dict:
    """Per evidence record: VERIFIED (SHA-256 of the recovered – or already-present production – bytes == evidence.sha256),
    MISSING, MISMATCH or UNREADABLE. Complete only when every record is VERIFIED; otherwise the exceptions are listed and
    their hash must be acknowledged explicitly at cutover (--accept-evidence-exceptions H). Never passes silently."""
    from collections import Counter
    by_sha = {x["sha256"]: x["key"] for x in m["extra"] if x.get("sha256")}
    recs = []
    for e in m["evidence"]:
        r = {"id": str(e["id"]), "storage_key": e["storage_key"], "sha256": e["sha256"], "status": INTEGRITY[e["status"]],
             "source": e.get("archive_path") or ("production bucket (same SHA-256)" if e["status"] == "present_in_production" else None),
             "matched_by": e.get("matched_by")}
        if e["status"] == "hash_mismatch":
            r["actual_sha256"] = e.get("actual_sha256")
        if e["status"] == "missing" and e["sha256"] in by_sha:
            r["hint"] = f"identical bytes exist in the source under key {by_sha[e['sha256']]} – key mapping problem, NOT counted"
        if e.get("detail"):
            r["detail"] = e["detail"]
        recs.append(r)
    exc = sorted([r["storage_key"], r["status"]] for r in recs if r["status"] != "VERIFIED")
    n = Counter(r["status"] for r in recs)
    return {"records": len(recs), "objects_in_source": len(scan["index"]), "verified": n["VERIFIED"], "missing": n["MISSING"],
            "verified_from_source": sum(e["status"] == "recovered" for e in m["evidence"]),
            "verified_in_production": sum(e["status"] == "present_in_production" for e in m["evidence"]),
            "mismatch": n["MISMATCH"], "unreadable": n["UNREADABLE"], "orphans": len(m["orphans"]), "complete": not exc,
            "exceptions": [{"storage_key": k, "status": s} for k, s in exc],
            "exceptions_hash": hashlib.sha256(json.dumps(exc).encode()).hexdigest()[:16] if exc else None, "per_record": recs}


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
    eng = ro_engine(url)
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
        mans = objsync_manifests(d)
        if not mans:
            raise RecoveryError(f"object_dir: no .objsync-manifest.json in {d} or {d}/<bucket>/ (objsync export incomplete)")
        out["object_dir"] = {"path": str(d), "size": sum(f.stat().st_size for f in d.rglob("*") if f.is_file()),
                             "sha256": hashlib.sha256(b"".join(bytes.fromhex(sha256_file(m)) for m in mans)).hexdigest(),
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
         "bucket": os.environ.get("S3_BUCKET"), "tool_version": TOOL_VERSION, "demo_account": demo_step_plan()}
    p["plan_hash"] = hashlib.sha256(json.dumps(p, sort_keys=True, default=str).encode()).hexdigest()[:16]
    return p


DEMO_EMAIL = "demo@ironvision.ai"
_DEMO_STEP = r'''
import json
from app.db import SessionLocal
from app.seed import ensure_demo_launcher_sandbox
with SessionLocal() as db:
    print("DEMO-STEP-JSON " + json.dumps(ensure_demo_launcher_sandbox(db)))
'''
# Protected (non-sandbox) scope: same row selection + id ordering as before; serialization = row_to_json joined by ',' in id order.
_FP_SCOPE = {
    "users": ("u", "users u join organizations o on o.id = u.org_id where not o.is_sandbox"),
    "organizations": ("o", "organizations o where not o.is_sandbox"),
    "role_assignments": ("r", "role_assignments r join users u on u.id = r.user_id join organizations o on o.id = u.org_id where not o.is_sandbox"),
    "evidence": ("e", "evidence e join systems s on s.id = e.system_id join organizations o on o.id = s.org_id where not o.is_sandbox"),
}
_FP_DIFF_CAP = 50


def prod_demo_flags() -> dict:
    """Demo decision inputs from the PRODUCTION env file (recover.sh → scripts/envget.py → app.envfile), passed as RECOVER_PRODENV_*.
    Never the tool process env: the recovery container only has x-recovery-env (no DEPLOYMENT_KIND/ALLOW_DEMO_LOGIN/…)."""
    src = os.environ.get("RECOVER_PRODENV_FILE")
    if not src:
        raise RecoveryError("production deployment flags missing (RECOVER_PRODENV_*): run through ./recover.sh, which reads them from the "
                            "production env file – the demo_account decision is never taken from the tool environment")
    return {"source": f"{src} (app.envfile parser via recover.sh)", "DEPLOYMENT_KIND": os.environ.get("RECOVER_PRODENV_DEPLOYMENT_KIND", ""),
            "ALLOW_DEMO_LOGIN": os.environ.get("RECOVER_PRODENV_ALLOW_DEMO_LOGIN", ""),
            "AUTH_PROVIDERS": os.environ.get("RECOVER_PRODENV_AUTH_PROVIDERS", ""),
            "demo_launcher_configured": os.environ.get("RECOVER_PRODENV_DEMO_LAUNCHER") == "yes"}


def demo_step_plan() -> dict:
    """Cutover step `demo_account` (part of the plan → plan hash + dry-run report): on a demo deployment the recovered DB gets
    demo@ironvision.ai + its sandbox org/personas from the SAME function app.seed uses, then the strict keycloak-migrate --link."""
    from app.seed import demo_launcher_decision
    f = prod_demo_flags()
    req = demo_launcher_decision(f["DEPLOYMENT_KIND"], f["ALLOW_DEMO_LOGIN"], f["AUTH_PROVIDERS"])
    return {"step": "app.seed.ensure_demo_launcher_sandbox (= app.seed for DEPLOYMENT_KIND=demo) on the target DB, before the switch",
            "email": DEMO_EMAIL, "required": req, "decision_inputs": f,
            "inconsistent": f["DEPLOYMENT_KIND"].lower() == "demo" and f["demo_launcher_configured"] and not req,
            "then": "keycloak-migrate --apply --link: exit 4 if the demo launcher would map 0 accounts; Explore Demo check after cutover"}


def demo_account_state(url: str) -> dict | None:
    """Separate read of what demo-login needs: the active demo user in a ready sandbox org (+ persona and mapping counts)."""
    eng = create_engine(url)
    with eng.connect() as c:
        row = c.execute(text("select u.id, u.is_active, o.id as org_id, o.is_sandbox, o.sandbox_status, "
                             "(select count(*) from users p where p.org_id = o.id and p.persona_role is not null) as personas, "
                             "(select count(*) from users d where lower(d.email) = :e) as demo_users, "
                             "(select count(*) from auth_identities ai where ai.user_id = u.id and ai.provider = 'oidc') as oidc_mappings "
                             "from users u join organizations o on o.id = u.org_id where lower(u.email) = :e"), {"e": DEMO_EMAIL}).first()
    eng.dispose()
    return {k: (str(v) if k in ("id", "org_id") else v) for k, v in row._mapping.items()} if row else None


def _sandbox_orgs(url: str) -> int:
    eng = create_engine(url)
    with eng.connect() as c:
        n = c.execute(text("select count(*) from organizations where is_sandbox")).scalar()
    eng.dispose()
    return n


def _fingerprint(url: str) -> dict:
    """Per category: count + SHA-256 of the deterministic serialization, plus per-row JSON (kept in memory only, for the safe diff)."""
    eng = create_engine(url)
    out = {}
    try:
        with eng.connect() as c:
            for cat, (a, frm) in _FP_SCOPE.items():
                rows = c.execute(text(f"select {a}.id::text, row_to_json({a})::text from {frm} order by {a}.id")).all()
                out[cat] = {"count": len(rows), "sha256": hashlib.sha256(",".join(j for _, j in rows).encode()).hexdigest(),
                            "rows": dict(rows)}
    finally:
        eng.dispose()
    return out


def _row_diff(before: dict, after: dict) -> dict:
    """Safe diff: primary-key ids added/removed/modified and, for modified rows, only the NAMES of changed columns."""
    added, removed = sorted(after.keys() - before.keys()), sorted(before.keys() - after.keys())
    modified = {}
    for i in sorted(before.keys() & after.keys()):
        if before[i] != after[i]:
            b, a = json.loads(before[i]), json.loads(after[i])
            modified[i] = sorted(k for k in b.keys() | a.keys() if b.get(k, object) != a.get(k, object))
    cols = sorted({c for v in modified.values() for c in v})
    return {"added_ids": added[:_FP_DIFF_CAP], "removed_ids": removed[:_FP_DIFF_CAP],
            "modified": dict(list(modified.items())[:_FP_DIFF_CAP]), "changed_columns": cols,
            "counts": {"added": len(added), "removed": len(removed), "modified": len(modified)}}


def fingerprint_compare(before: dict, after: dict) -> dict:
    res = {}
    for cat in _FP_SCOPE:
        b, a = before[cat], after[cat]
        changed = b["sha256"] != a["sha256"] or b["count"] != a["count"]
        res[cat] = {"before": {"count": b["count"], "sha256": b["sha256"]}, "after": {"count": a["count"], "sha256": a["sha256"]},
                    "changed": changed}
        if changed:
            res[cat]["diff"] = _row_diff(b["rows"], a["rows"])
    return res


def _fp_summary(cmp: dict) -> str:
    parts = []
    for cat, v in cmp.items():
        if v["changed"]:
            d = v["diff"]
            parts.append(f"{cat} (count {v['before']['count']}->{v['after']['count']}; added {d['counts']['added']}, removed "
                         f"{d['counts']['removed']}, modified {d['counts']['modified']}; changed columns {d['changed_columns']}; "
                         f"ids added {d['added_ids'][:5]} removed {d['removed_ids'][:5]} modified {list(d['modified'])[:5]})")
    return "; ".join(parts)


def demo_account_step(url: str, bucket: str, admin_bucket: bool) -> dict:
    """Runs for rehearse (scratch target, rehearsal bucket) and apply (recovered DB, production bucket) alike. Only the demo sandbox
    org changes: non-sandbox users + organizations (restored + admin) are fingerprinted before/after and must be identical."""
    d = demo_step_plan()
    src = d["decision_inputs"]["source"]
    if d["inconsistent"]:
        return d | {"ran": False, "ok": False, "error": f"production env ({src}) says DEPLOYMENT_KIND=demo with the demo launcher configured, "
                    f"but ALLOW_DEMO_LOGIN/AUTH_PROVIDERS make the demo_account step NOT required – refusing (Explore Demo would 403)"}
    if not d["required"]:
        return d | {"ran": False, "ok": True, "detail": f"not a demo deployment according to {src} – no demo account"}
    pre = "RECOVER_S3_ADMIN_" if admin_bucket and os.environ.get("RECOVER_S3_ADMIN_ACCESS_KEY_ID") else "S3_"
    fl = d["decision_inputs"]
    # the step's own process: production demo flags + a process-local JWT_SECRET (settings require one; the seed issues no tokens)
    env = {**os.environ, "DATABASE_URL": url, "S3_BUCKET": bucket, "S3_ACCESS_KEY_ID": os.environ.get(pre + "ACCESS_KEY_ID", ""),
           "S3_SECRET_ACCESS_KEY": os.environ.get(pre + "SECRET_ACCESS_KEY", ""), "DEPLOYMENT_KIND": fl["DEPLOYMENT_KIND"],
           "ALLOW_DEMO_LOGIN": fl["ALLOW_DEMO_LOGIN"], "AUTH_PROVIDERS": fl["AUTH_PROVIDERS"],
           "JWT_SECRET": os.environ.get("JWT_SECRET") or secrets.token_urlsafe(48), "IRONVISION_DOTENV": "0"}
    try:
        before, sbx_before = _fingerprint(url), _sandbox_orgs(url)
    except Exception as e:  # noqa: BLE001
        return d | {"ran": False, "ok": False, "protected_fingerprint": None,
                    "error": f"protected-data fingerprint collection failed (before): {redact(f'{type(e).__name__}: {e}')[:400]}"}
    p = subprocess.run([sys.executable, "-c", _DEMO_STEP], env=env, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2], check=False)
    m = re.search(r"^DEMO-STEP-JSON (.+)$", p.stdout, re.M)
    res = json.loads(m.group(1)) if m else None
    try:
        cmp = fingerprint_compare(before, _fingerprint(url))
        fp_err = None
    except Exception as e:  # noqa: BLE001
        cmp, fp_err = None, f"protected-data fingerprint collection failed (after): {redact(f'{type(e).__name__}: {e}')[:400]}"
    changed = [c for c, v in (cmp or {}).items() if v["changed"]]
    same = cmp is not None and not changed
    st = demo_account_state(url)  # separate query: it must PERSIST in the target DB
    persisted = bool(st and st["is_active"] and st["is_sandbox"] and st["sandbox_status"] == "ready" and st["demo_users"] == 1
                     and res and st["org_id"] == res["org_id"])
    ok = p.returncode == 0 and bool(res) and same and persisted
    out = d | {"ran": True, "ok": ok, "result": res, "persisted": st, "bucket": bucket, "restored_users_and_orgs_unchanged": same,
               "protected_fingerprint": cmp, "changed_categories": changed,
               "sandbox_orgs_before_after": [sbx_before, _sandbox_orgs(url)]}
    if not ok:
        out["error"] = (fp_err if fp_err else
                        f"protected (non-sandbox) data changed in: {', '.join(changed)} – {_fp_summary(cmp)}" if not same else
                        f"demo account not persisted in the target DB: {json.dumps(st)}" if p.returncode == 0 and res else
                        redact((p.stdout + p.stderr)[-600:]))
    log(f"[demo_account] {'OK' if ok else 'FAILED'} {json.dumps(res)} persisted={json.dumps(st)} restored users/orgs unchanged={same} changed={changed} "
        f"(decision from {src})")
    return out


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
        n = sum(len(json.loads(m.read_text())["objects"]) for m in objsync_manifests(Path(p["inputs"]["object_dir"]["path"])))
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
    integrity = evidence_integrity(m, scan)
    log(f"[objects] evidence integrity: {integrity['verified']}/{integrity['records']} VERIFIED, {integrity['missing']} MISSING, "
        f"{integrity['mismatch']} MISMATCH, {integrity['unreadable']} UNREADABLE; {integrity['objects_in_source']} objects in source, "
        f"{integrity['orphans']} not referenced by any evidence record")
    copied = copy_objects(bucket, m, admin=admin_bucket)
    demo = demo_account_step(b["url"], bucket, admin_bucket)  # after evidence matching: its synthetic evidence is not legacy data
    st = {s: sum(1 for e in m["evidence"] if e["status"] == s) for s in ("recovered", "present_in_production", "missing", "hash_mismatch", "unreadable")}
    return {"target_db": target_name, "build": {k: v for k, v in b.items() if k != "url"}, "reconciliation": rec, "demo_account": demo,
            "fk": fk_orphans(b["url"]), "audit_chain": chain(b["url"]), "objects": {
                "layout": scan["layout"], "bucket": bucket, "summary": {**st, "extra": len(m["orphans"])}, "orphans": m["orphans"],
                "extra": m["extra"], "versioned": scan.get("meta", {}), "copy": copied, "integrity": integrity,
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
    if not r["demo_account"]["ok"]:
        why.append(f"demo account step failed: {r['demo_account'].get('error') or r['demo_account'].get('result')}")
    return why


def kc_dry_run(url: str, t: str) -> str:
    if not os.environ.get("KEYCLOAK_URL"):
        return "skipped (KEYCLOAK_URL not set)"
    env = {**os.environ, "DATABASE_URL": url}
    r = subprocess.run([sys.executable, "-m", "app.cli", "keycloak-migrate", "--report", str(RDIR / f"keycloak-migrate-plan-{t}.json")],
                       env=env, capture_output=True, text=True, cwd=Path(__file__).resolve().parents[2], check=False)
    return redact((r.stdout + r.stderr)[-3000:])


def kc_link_scratch(url: str, t: str, env: dict) -> dict:
    """`keycloak-migrate --apply --link` (no --create-identities) into the SCRATCH rehearsal DB, against the SCRATCH Keycloak
    given in `env` (scratch_sso.setup) – never the production Keycloak. Maps the scratch demo-launcher identity."""
    if not SCRATCH.match(make_url(url).database or "") or make_url(url).database == make_url(live_url()).database:
        raise RecoveryError(f"refusing Keycloak link into non-scratch DB {make_url(url).database}")
    env, cwd = {**env, "DATABASE_URL": url}, Path(__file__).resolve().parents[2]
    rep = RDIR / f"keycloak-link-scratch-{t}.json"
    r = subprocess.run([sys.executable, "-m", "app.cli", "keycloak-migrate", "--report", str(rep)], env=env, capture_output=True, text=True, cwd=cwd, check=False)
    if r.returncode:
        return {"rc": r.returncode, "output": redact((r.stdout + r.stderr)[-3000:])}
    h = json.loads(rep.read_text())["plan_hash"]
    dry = json.loads(rep.read_text())
    demo_rows = [u for u in dry.get("users", []) if (u.get("email") or "").lower() == "demo@ironvision.ai"]
    ref = RDIR / "backups" / f"scratch-{t}"
    ref.mkdir(parents=True, exist_ok=True)
    write_json(f"backups/scratch-{t}/manifest.json", {"kind": "scratch-rehearsal-db", "db": make_url(url).database, "note": "throw-away rehearsal DB",
                                                      "created_at": datetime.now(timezone.utc).isoformat()})
    r = subprocess.run([sys.executable, "-m", "app.cli", "keycloak-migrate", "--apply", "--link", "--plan-hash", h, "--backup-ref", str(ref),
                        "--credentials-dir", str(RDIR / "credentials-scratch"), "--report", str(rep), "--yes"],
                       env=env, capture_output=True, text=True, cwd=cwd, check=False)
    out = redact((r.stdout + r.stderr)[-3000:])
    return {"rc": r.returncode, "plan_hash": h, "db": make_url(url).database, "keycloak_writes": "none (link only, no --create-identities)",
            "issuer": dry.get("issuer"), "demo_plan_rows": demo_rows,
            "links_planned": sum(1 for u in dry.get("users", []) if u.get("action") == "link"), "output": out}


def write_report(kind: str, t: str, body: dict) -> None:
    write_json(f"{kind}-{t}.json", body)
    lines = [f"# IronVision recovery {kind} {t}", "", f"- plan-hash: `{body.get('plan_hash')}`", f"- result: **{'PASS' if body.get('passed') else 'FAIL'}**"]
    for w in body.get("failures", []):
        lines.append(f"  - {w}")
    ss = body.get("scratch_sso")
    if ss:
        lines += ["", "## Scratch SSO stack (isolated Keycloak – production Keycloak not contacted)", "",
                  f"- issuer: `{ss.get('issuer')}`; scratch Keycloak DB/role: `{(ss.get('kc_db') or {}).get('database')}`",
                  (f"- e2e user: `{((ss.get('kc_users') or {}).get('e2e') or {}).get('username')}` (leadership_viewer, scratch org); "
                   f"demo launcher: `{((ss.get('kc_users') or {}).get('demo_launcher') or {}).get('username')}`"),
                  "- restored users (8 + admin) before/after: " + " / ".join(
                      f"{(ss.get(k) or {}).get('users')} users sha256 {str((ss.get(k) or {}).get('sha256'))[:12]}" for k in ("restored_before", "restored_after")),
                  "- cleanup: " + ("**OK**" if ss.get("cleanup_ok") else "**INCOMPLETE – see items; production untouched**")]
        lines += [f"  - {k}: **{v['status']}** – {v['detail']}" for k, v in (ss.get("cleanup_steps") or {}).items()]
    e2e = (body.get("backend_probe") or {}).get("e2e_sso") if isinstance(body.get("backend_probe"), dict) else None
    if e2e:
        lines += ["", "## SSO e2e steps (scratch stack)", "", "| step | result | detail |", "|---|---|---|"]
        lines += [f"| {s['step']} | {'PASS' if s['pass'] else 'FAIL'} | {s['detail'][:120]} |" for s in e2e.get("steps", [])]
    pc = body.get("production_keycloak_anonymous_check")
    if pc:
        lines += ["", "## Production Keycloak – anonymous read-only check (separate from the SSO e2e; no login)", "", f"- {json.dumps(pc)}"]
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
        fp = (r.get("demo_account") or {}).get("protected_fingerprint")
        if fp:
            lines += ["", "## Protected (non-sandbox) data fingerprint – demo_account step", "",
                      "| category | before count | before sha256 | after count | after sha256 | changed | safe diff (ids / column names) |",
                      "|---|---|---|---|---|---|---|"]
            lines += [f"| {c} | {v['before']['count']} | `{v['before']['sha256'][:16]}` | {v['after']['count']} | `{v['after']['sha256'][:16]}` | "
                      f"{'**YES**' if v['changed'] else 'no'} | {json.dumps(v['diff']) if v['changed'] else ''} |" for c, v in fp.items()]
        ig = o.get("integrity")
        if ig:
            lines += ["", "## Evidence integrity (storage key → SHA-256)", "",
                      f"- **{ig['verified']}/{ig['records']} VERIFIED**, {ig['missing']} MISSING, {ig['mismatch']} MISMATCH, {ig['unreadable']} UNREADABLE"
                      f" – {ig['objects_in_source']} objects in the source, {ig['orphans']} not referenced by any evidence record",
                      "- evidence recovery: " + ("**COMPLETE**" if ig["complete"] else
                                                 f"**INCOMPLETE** – cutover requires `--accept-evidence-exceptions {ig['exceptions_hash']}`"),
                      "", "| evidence id | storage key | status | source object | matched by | note |", "|---|---|---|---|---|---|"]
            lines += [f"| {r['id']} | `{r['storage_key']}` | {r['status']} | {r.get('source') or '-'} | {r.get('matched_by') or '-'} | "
                      f"{r.get('hint') or r.get('detail') or (('actual ' + r['actual_sha256'][:16]) if r.get('actual_sha256') else '')} |" for r in ig["per_record"]]
            lines += ["", f"### Objects not referenced by any evidence record ({len(o['extra'])})", "", "| key | bytes | classification |", "|---|---|---|"]
            lines += [f"| `{x['key']}` | {x.get('bytes', '?')} | {x['kind']}{' (' + str(x['versions']) + ')' if x.get('versions') else ''} |" for x in o["extra"]]
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
    body = {"plan_hash": p["plan_hash"], "tool_version": TOOL_VERSION, "ts": t, "scratch": {"dbs": [src, prodc, f"rec_target_{t}"], "bucket": bucket}}
    try:
        body["result"] = _run_recovery(t, db_url(prodc), f"rec_target_{t}", bucket, admin_bucket=True)
        body["failures"] = _passed(body["result"])
        # no production-Keycloak admin access in the rehearsal: identity planning/conflicts are checked by cutover's own
        # keycloak-migrate dry run before any change; SSO is tested against an isolated scratch Keycloak (scratch_sso)
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
    for d in [*body["scratch"]["dbs"], f"rec_kc_{body['ts']}"]:
        drop_scratch_db(d)
    with create_engine(admin_url(), isolation_level="AUTOCOMMIT").connect() as c:  # scratch Keycloak role leftover
        c.exec_driver_sql(f'drop role if exists "rec_kc_{body["ts"]}"') if SCRATCH.match(f"rec_kc_{body['ts']}") else None
    cl = s3(True)
    for o in bucket_manifest(body["scratch"]["bucket"]):
        cl.delete_object(Bucket=body["scratch"]["bucket"], Key=o["key"])
    cl.delete_bucket(Bucket=body["scratch"]["bucket"])
    log("[rehearse] scratch databases and rehearsal bucket dropped (--cleanup)")


def latest(kind: str) -> dict | None:
    fs = sorted(RDIR.glob(f"{kind}-*.json"))
    return json.loads(fs[-1].read_text()) if fs else None


def cmd_rehearse_probe(a) -> int:
    """Probes run WHERE the rehearsal backend is reachable without Docker DNS (recover.sh execs this inside the rehearsal-backend
    container → http://127.0.0.1:8001). Every step must really pass; nothing is downgraded. Full e2e transcript → report dir."""
    import httpx
    fs = sorted(RDIR.glob("rehearsal-*.json"))
    body = json.loads(fs[-1].read_text())
    url = a.url.rstrip("/")
    res = {}
    for path in ("/api/v1/health/live", "/api/v1/ready", "/api/v1/auth/provider"):
        try:
            res[path] = httpx.get(url + path, timeout=15).status_code
        except httpx.HTTPError as exc:
            res[path] = f"error {type(exc).__name__}: {exc}"
    ctx = {"url": url, "runs_in": a.where or "unspecified"}
    if a.netdiag and Path(a.netdiag).is_file():
        ctx["netdiag"] = json.loads(Path(a.netdiag).read_text())
    body["probe_context"] = ctx
    if a.e2e:
        env = dict(os.environ)
        cred = RDIR / ".e2e-credentials"  # written 0600 by scratch_sso setup (scratch user, random password); read once, deleted
        if cred.is_file():
            user, _, pw = cred.read_text().partition("\n")
            cred.unlink()
            env["E2E_USER"], env["E2E_PASSWORD"] = user.strip(), pw.rstrip("\n")
            ctx["login_account"] = user.strip()
        tr = RDIR / f"e2e-sso-{body['ts']}.transcript.log"
        cmd = [sys.executable, str(Path(__file__).resolve().parents[3] / "scripts" / "e2e_sso.py"), "--base", url, "--demo", "--json",
               "--rehearsal", "--transcript", str(tr), "--user", env.get("E2E_USER", "")]
        for h in filter(None, (os.environ.get("REHEARSAL_FORBIDDEN_HOSTS") or "").split(",")):
            cmd += ["--forbid-host", h.strip()]
        if (env.get("OIDC_ISSUER") or "").startswith("http://"):  # plain-http TEST Keycloak only (Secure cookies); never for https
            cmd.append("--insecure-cookies")
        r = subprocess.run(cmd, capture_output=True, text=True, check=False, env=env, timeout=600)
        out = RDIR / f"e2e-sso-{body['ts']}.out"
        out.write_text(redact(f"$ {' '.join(cmd[1:])}\nexit {r.returncode}\n--- stdout\n{r.stdout}\n--- stderr\n{r.stderr}\n"))
        os.chmod(out, 0o600)
        try:
            steps = json.loads(r.stdout)
        except ValueError:
            steps = [{"step": "e2e_sso.py output", "pass": False, "detail": redact((r.stderr or r.stdout)[-300:])}]
        res["e2e_sso"] = {"rc": r.returncode, "steps": steps, "stdout_stderr": str(out), "transcript": str(tr)}
    body["backend_probe"] = res
    body["probe_passed"] = all(v == 200 for k, v in res.items() if k.startswith("/")) and (not a.e2e or res["e2e_sso"]["rc"] == 0)
    body["e2e_ran"] = bool(a.e2e)
    if not body["probe_passed"]:
        bad = {k: v for k, v in res.items() if k.startswith("/") and v != 200}
        bad.update({s["step"]: s["detail"] for s in (res.get("e2e_sso") or {}).get("steps", []) if not s["pass"]})
        body["failures"].append(f"rehearsal backend probe failed ({ctx['runs_in']}, {url}): {json.dumps(bad)[:600]}")
    body["passed"] = not body["failures"]
    write_report("rehearsal", body["ts"], body)
    log(f"[rehearse-probe] {'PASS' if body['passed'] else 'FAIL'} at {url} ({ctx['runs_in']}): "
        f"{json.dumps({k: (v if k.startswith('/') else v['rc']) for k, v in res.items()})}")
    return 0 if body["passed"] else 1


def cmd_probe_unreachable(a) -> int:
    """recover.sh: the rehearsal backend never became healthy – record the diagnostic as a rehearsal failure (no probe can pass)."""
    fs = sorted(RDIR.glob("rehearsal-*.json"))
    body = json.loads(fs[-1].read_text())
    body["backend_probe"] = {"unreachable": a.reason}
    body["probe_passed"] = False
    if a.netdiag and Path(a.netdiag).is_file():
        body["probe_context"] = {"netdiag": json.loads(Path(a.netdiag).read_text())}
    body["failures"].append(f"rehearsal backend unreachable: {a.reason}")
    body["passed"] = False
    write_report("rehearsal", body["ts"], body)
    return 1


def rehearsal_gate(reh: dict | None, plan_hash: str) -> None:
    """Explicit cutover gate: the rehearsal of THIS plan-hash, by THIS tool version, with every step (recovery, backend probes and
    the full SSO e2e) passed. Older plan hashes (e.g. e4c831f4a432b3b4, pre-v2 tool) are refused."""
    if not reh or reh.get("plan_hash") != plan_hash:
        raise RecoveryError(f"no rehearsal recorded for plan-hash {plan_hash} – run ./recover.sh run")
    if reh.get("tool_version") != TOOL_VERSION:
        raise RecoveryError(f"plan-hash {plan_hash} was rehearsed by tool version {reh.get('tool_version') or '(pre-versioning)'}, "
                            f"current is {TOOL_VERSION} – re-run ./recover.sh run")
    if not reh.get("passed") or reh.get("failures"):
        raise RecoveryError(f"the rehearsal of plan-hash {plan_hash} did not pass: {reh.get('failures')}")
    if not reh.get("probe_passed") or not reh.get("e2e_ran"):
        raise RecoveryError(f"the rehearsal of plan-hash {plan_hash} has no passing backend probe + SSO e2e")


def evidence_gate(ig: dict | None, ack: str | None) -> None:
    """Complete evidence (every record VERIFIED) passes; documented exceptions only with their exact hash acknowledged."""
    if not ig:
        raise RecoveryError("the rehearsal has no evidence-integrity result – re-run ./recover.sh run")
    if not ig["complete"] and ack != ig["exceptions_hash"]:
        raise RecoveryError(f"evidence recovery INCOMPLETE ({ig['verified']}/{ig['records']} VERIFIED; exceptions {json.dumps(ig['exceptions'])[:400]}) – "
                            f"review the rehearsal report, then acknowledge explicitly: --accept-evidence-exceptions {ig['exceptions_hash']}")
    if ig["complete"] and ack:
        raise RecoveryError("--accept-evidence-exceptions given but evidence is complete – nothing to acknowledge")


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
    rehearsal_gate(reh, a.plan_hash)
    if datetime.now(timezone.utc) - datetime.strptime(reh["ts"], "%Y%m%dt%H%M%S").replace(tzinfo=timezone.utc) > timedelta(hours=24):
        raise RecoveryError("the passing rehearsal is older than 24h – rehearse again")
    ig = ((reh.get("result") or {}).get("objects") or {}).get("integrity")
    evidence_gate(ig, a.accept_evidence_exceptions)
    t = ts()
    backups, man = take_backups(t, a.skip_keycloak_backup)
    target = f"ironvision_recovered_{t}"
    body = {"plan_hash": a.plan_hash, "ts": t, "backups": backups, "previous_db": make_url(live_url()).database, "target_db": target,
            "bucket_before": {"objects": len(man), "bytes": sum(o["size"] for o in man)},
            # verify after the switch treats ONLY these known-unrecoverable keys as accepted, and only if acknowledged here
            "evidence_exceptions": {"exceptions_hash": (ig or {}).get("exceptions_hash"), "accepted_by_operator": bool(
                ig and not ig.get("complete") and a.accept_evidence_exceptions and a.accept_evidence_exceptions == ig.get("exceptions_hash"))}}
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


RT_PREFIX = ".ironvision-recovery-roundtrip/"   # never an evidence key: evidence keys are "evidence/…" (checked against the DB too)


def evidence_check_ro(url: str, bucket: str, accepted_keys: set) -> dict:
    """Independent READ-ONLY integrity check: object bytes from storage → SHA-256 → evidence.sha256. Writes nothing (DB or bucket).
    accepted_keys: known-unrecoverable keys apply recorded AND the operator acknowledged – reported separately, never as verified."""
    from botocore.exceptions import ClientError
    cl = s3(False)
    eng = ro_engine(url)
    with eng.connect() as c:
        rows = list(c.execute(text("select id::text, storage_key, sha256 from evidence order by id")))
    eng.dispose()
    counts = {k: 0 for k in ("verified", "hash_mismatch", "missing", "unreadable")}
    failures, accepted = [], []
    for eid, key, sha in rows:
        try:
            st = "verified" if hashlib.sha256(cl.get_object(Bucket=bucket, Key=key)["Body"].read()).hexdigest() == sha else "hash_mismatch"
        except ClientError as e:
            st = "missing" if str(e.response.get("Error", {}).get("Code")) in ("NoSuchKey", "404", "NotFound") else "unreadable"
        except Exception:  # noqa: BLE001
            st = "unreadable"
        counts[st] += 1
        if st != "verified":
            (accepted if key in accepted_keys else failures).append({"evidence_id": eid, "storage_key": key, "status": st})
    return {"evidence": len(rows), "verified": counts["verified"], "counts": counts, "failures": failures,
            "accepted_exceptions": accepted, "read_only": True}


def storage_roundtrip(url: str, bucket: str) -> dict:
    """The ONLY write of verify: one namespaced temp object in the live bucket (proves the app key can still store new evidence,
    e.g. after the SeaweedFS restart), refused if the key exists or the namespace is referenced by evidence; deleted in finally."""
    from botocore.exceptions import ClientError
    cl, key = s3(False), f"{RT_PREFIX}{ts()}-{secrets.token_hex(6)}"
    out = {"key": key, "put": False, "read_back": False, "deleted": False}
    eng = ro_engine(url)
    with eng.connect() as c:
        clash = c.execute(text("select count(*) from evidence where storage_key like :p"), {"p": RT_PREFIX + "%"}).scalar()
    eng.dispose()
    if clash:
        return out | {"ok": False, "error": f"{clash} evidence row(s) use the round-trip namespace – refusing to write"}
    try:
        cl.head_object(Bucket=bucket, Key=key)
        return out | {"ok": False, "error": "round-trip key already exists – refusing to overwrite"}
    except ClientError:
        pass
    try:
        cl.put_object(Bucket=bucket, Key=key, Body=b"roundtrip")
        out["put"] = True
        out["read_back"] = cl.get_object(Bucket=bucket, Key=key)["Body"].read() == b"roundtrip"
    except Exception as e:  # noqa: BLE001
        out["error"] = redact(f"{type(e).__name__}: {e}")[:200]
    finally:
        try:
            cl.delete_object(Bucket=bucket, Key=key)
            try:
                cl.head_object(Bucket=bucket, Key=key)
            except ClientError:
                out["deleted"] = True
        except Exception as e:  # noqa: BLE001
            out["delete_error"] = redact(f"{type(e).__name__}: {e}")[:200]
    out["ok"] = out["put"] and out["read_back"] and out["deleted"]
    return out


def cmd_verify(a) -> int:
    """READ-ONLY verify of the live DB + bucket (default_transaction_read_only=on). Never runs the app's verify_integrity job
    (it writes integrity_checks/evidence/freshness for every org). Only write: storage_roundtrip's temp object, always deleted."""
    url, bucket = live_url(), os.environ["S3_BUCKET"]
    db = make_url(url).database
    ap = next((json.loads(f.read_text()) for f in sorted(RDIR.glob("apply-*.json"), reverse=True)
               if json.loads(f.read_text()).get("target_db") == db), None)
    known = {d["storage_key"] for d in ((ap or {}).get("result") or {}).get("objects", {}).get("detail", [])
             if d.get("status") in ("missing", "hash_mismatch", "unreadable")}
    ex = (ap or {}).get("evidence_exceptions") or {}
    acked = bool(known) and ex.get("accepted_by_operator") is True
    checks = {"db": db, "revision": revision(url), "fk": fk_orphans(url), "audit_chain": chain(url),
              "objects": evidence_check_ro(url, bucket, known if acked else set()),
              "known_unrecoverable": {"keys": sorted(known), "acknowledged": acked, "exceptions_hash": ex.get("exceptions_hash")}}
    eng = ro_engine(url)
    with eng.connect() as c:
        checks["protected_orgs"] = [str(r[0]) for r in c.execute(text("select id from organizations where protected"))]
    eng.dispose()
    checks["storage_roundtrip"] = storage_roundtrip(url, bucket)
    m = bucket_manifest(bucket)
    checks["bucket_after"] = {"objects": len(m), "bytes": sum(o["size"] for o in m)}
    o = checks["objects"]
    fails = ((["FK orphans"] if len(checks["fk"]) > 1 else []) + ([] if checks["audit_chain"]["valid"] else ["audit chain"])
             + ([f"{len(o['failures'])} evidence object(s) failed (" + ", ".join(f"{k} {v}" for k, v in o["counts"].items() if k != "verified" and v)
                 + ")" + (" – known-unrecoverable keys NOT acknowledged at apply" if known and not acked else "")] if o["failures"] else [])
             + ([] if checks["storage_roundtrip"]["ok"] else ["storage round-trip"]))
    t = ts()
    write_json(f"verify-{t}.json", {"ts": t, "checks": checks, "failures": fails, "passed": not fails})
    log(f"[verify] {'PASS' if not fails else 'FAIL'} db={db}@{checks['revision']} (read-only) evidence {o['verified']}/{o['evidence']} verified "
        f"{json.dumps(o['counts'])}; accepted known-unrecoverable {len(o['accepted_exceptions'])} (NOT counted as verified); "
        f"chain={checks['audit_chain']['valid']} round-trip={checks['storage_roundtrip']['ok']} fails={fails}")
    for f in o["failures"]:
        log(f"[verify]   FAIL {f['status']}: evidence {f['evidence_id']} key {f['storage_key']}")
    for f in o["accepted_exceptions"]:
        log(f"[verify]   ACCEPTED-EXCEPTION {f['status']}: evidence {f['evidence_id']} key {f['storage_key']}")
    return 0 if not fails else 1


def cmd_health(a) -> int:
    """Post-rollback (or post-switch) health, VERIFIED not assumed: /health/live + /ready 200, and pg_stat_activity shows the app's
    connections (application_name=ironvision-app) on --expect-db and none on --not-db; --retained-db must still exist."""
    import httpx
    res, fails = {"url": a.url, "expect_db": a.expect_db, "not_db": a.not_db, "retained_db": a.retained_db}, ["not checked"]
    for _ in range(a.tries):
        fails, res["checks"] = [], {}
        try:
            lv = httpx.get(f"{a.url}/api/v1/health/live", timeout=10)
            rd = httpx.get(f"{a.url}/api/v1/ready", timeout=10)
            res["checks"]["live"], res["checks"]["ready"] = lv.status_code, rd.status_code
            res["checks"]["migration"] = rd.json().get("migration") if rd.status_code == 200 else None
            fails += [] if lv.status_code == 200 else [f"/health/live {lv.status_code}"]
            fails += [] if rd.status_code == 200 else [f"/ready {rd.status_code}"]
        except httpx.HTTPError as e:
            fails.append(f"app unreachable: {type(e).__name__}")
        eng = ro_engine(live_url())
        with eng.connect() as c:
            dbs = {r[0]: r[1] for r in c.execute(text("select datname, count(*) from pg_stat_activity where application_name = 'ironvision-app' group by 1"))}
            kept = c.execute(text("select count(*) from pg_database where datname = :n"), {"n": a.retained_db}).scalar() if a.retained_db else None
        eng.dispose()
        res["checks"]["app_connections_by_db"] = dbs
        fails += [] if dbs.get(a.expect_db) else [f"no app connection on {a.expect_db}"]
        fails += [f"app still connected to {a.not_db}"] if a.not_db and dbs.get(a.not_db) else []
        if a.retained_db:
            res["checks"]["retained_db_exists"] = bool(kept)
            fails += [] if kept else [f"recovered DB {a.retained_db} missing"]
        if not fails:
            break
        time.sleep(2)
    res["failures"], res["passed"] = fails, not fails
    write_json(f"health-{ts()}.json", res)
    log(f"[health] {'PASS' if not fails else 'FAIL'} app on db={a.expect_db} {json.dumps(res['checks'])} fails={fails}")
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


def cmd_samples_check(a) -> int:
    """Gate: the tool container (demo_account step) sees every required demo sandbox sample file. Demo deployments only."""
    from app.services import sandbox as sbx
    d = demo_step_plan()
    if not d["required"]:
        log(f"[samples-check] SKIP not a demo deployment ({d['decision_inputs']['source']})")
        return 0
    try:
        r = sbx.check_samples()
    except sbx.SamplesMissing as exc:
        log(f"[samples-check] FAIL {exc}")
        return 1
    log(f"[samples-check] OK {r['samples_dir']}: {len(r['files'])} files ({', '.join(r['files'])})")
    return 0


def cmd_demo_check(a) -> int:
    """After cutover: Explore Demo against the production backend must return 200 (+ role switch); else cutover fails → rollback."""
    import httpx
    t, d = ts(), demo_step_plan()
    if not d["required"]:
        log("[demo-check] SKIP not a demo deployment (Explore Demo disabled)")
        return 0
    if os.environ.get("RECOVER_LOCAL") == "1" and os.environ.get("RECOVER_CUTOVER_FAULT") == "demo-403":  # test only: forced 403
        eng = create_engine(live_url())
        with eng.begin() as c:
            c.execute(text("delete from auth_identities where provider = 'oidc' and user_id in (select id from users where email = :e)"),
                      {"e": DEMO_EMAIL})
        eng.dispose()
    res: dict = {"url": a.url}
    try:
        with httpx.Client(base_url=a.url, timeout=30) as c:
            r = c.post("/api/v1/auth/demo-login")
            res |= {"demo_login": r.status_code, "detail": r.text[:200] if r.status_code != 200 else ""}
            if r.status_code == 200:
                h = {"Authorization": f"Bearer {r.json()['access_token']}"}
                res["role_switch"] = c.post("/api/v1/sandbox/act-as", json={"role": "issm"}, headers=h).status_code
                c.post("/api/v1/auth/logout", headers=h)
    except httpx.HTTPError as exc:
        res["error"] = f"{type(exc).__name__}: {exc}"
    ok = res.get("demo_login") == 200 and res.get("role_switch") == 200
    write_json(f"demo-check-{t}.json", {**res, "ts": t, "passed": ok})
    log(f"[demo-check] {'PASS' if ok else 'FAIL'} Explore Demo against {a.url}: demo-login {res.get('demo_login')}, role switch "
        f"{res.get('role_switch')} {res.get('detail') or res.get('error') or ''}")
    return 0 if ok else 1


def tool_process_defaults() -> None:
    """The recovery container has only x-recovery-env: app settings still require JWT_SECRET (get_settings → verify_integrity →
    get_storage). The tool signs nothing, so it gets a process-local throwaway value, never written anywhere."""
    os.environ.setdefault("JWT_SECRET", secrets.token_urlsafe(48))


def main(argv=None) -> int:
    tool_process_defaults()
    ap = argparse.ArgumentParser(prog="recover")
    sp = ap.add_subparsers(dest="cmd", required=True)
    sp.add_parser("preflight")
    r = sp.add_parser("rehearse")
    r.add_argument("--cleanup", action="store_true")
    rp = sp.add_parser("rehearse-probe")
    rp.add_argument("--url", required=True)
    rp.add_argument("--e2e", action="store_true")
    rp.add_argument("--where", default="")
    rp.add_argument("--netdiag", default="")
    pu = sp.add_parser("probe-unreachable")
    pu.add_argument("--reason", required=True)
    pu.add_argument("--netdiag", default="")
    x = sp.add_parser("apply")
    x.add_argument("--plan-hash", required=True)
    x.add_argument("--accept-evidence-exceptions", default=None)
    x.add_argument("--skip-keycloak-backup", action="store_true")
    sp.add_parser("verify")
    x = sp.add_parser("health")
    x.add_argument("--url", required=True)
    x.add_argument("--expect-db", required=True)
    x.add_argument("--not-db", default="")
    x.add_argument("--retained-db", default="")
    x.add_argument("--tries", type=int, default=30)
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
    sp.add_parser("samples-check")
    dc = sp.add_parser("demo-check")
    dc.add_argument("--url", required=True)
    a = ap.parse_args(argv)
    fn = {"preflight": cmd_preflight, "rehearse": cmd_rehearse, "rehearse-probe": cmd_rehearse_probe, "probe-unreachable": cmd_probe_unreachable,
          "apply": cmd_apply, "verify": cmd_verify, "health": cmd_health, "demo-check": cmd_demo_check, "samples-check": cmd_samples_check,
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
    if sys.argv[1:2] == ["scratch-sso"]:  # recover.sh `py scratch-sso …` → isolated rehearsal SSO stack
        from app.tools import scratch_sso
        sys.argv = [sys.argv[0], *sys.argv[2:]]
        sys.exit(scratch_sso.main())
    rc = main()
    sys.exit(rc)
