#!/usr/bin/env bash
# AegisRMF backup: pg_dump (custom format) + evidence object storage copy + manifest (SHA-256 per artifact, row counts,
# audit-chain head hash). Usage: scripts/backup.sh [OUT_DIR]
# Env: DATABASE_URL (required), STORAGE_DRIVER=local|s3, STORAGE_LOCAL_ROOT (local), S3_BUCKET/S3_ENDPOINT_URL (s3, uses aws cli),
#      PG_BIN (dir with pg_dump matching the server major version, e.g. /usr/lib/postgresql/16/bin)
set -euo pipefail
OUT="${1:-./backups/aegisrmf-$(date -u +%Y%m%dT%H%M%SZ)}"
PG_BIN="${PG_BIN:-}"; [ -n "$PG_BIN" ] && PG_BIN="${PG_BIN%/}/"
: "${DATABASE_URL:?DATABASE_URL required}"
PGURL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
mkdir -p "$OUT"
echo "[backup] database -> $OUT/db.dump"
"${PG_BIN}pg_dump" --format=custom --no-owner --no-privileges --file="$OUT/db.dump" "$PGURL"
case "${STORAGE_DRIVER:-local}" in
  local) : "${STORAGE_LOCAL_ROOT:?STORAGE_LOCAL_ROOT required}"
         echo "[backup] objects (local) -> $OUT/objects.tar.gz"
         tar -C "$STORAGE_LOCAL_ROOT" -czf "$OUT/objects.tar.gz" . ;;
  s3)    : "${S3_BUCKET:?S3_BUCKET required}"
         echo "[backup] objects (s3://$S3_BUCKET) -> $OUT/objects/"
         aws s3 sync "s3://$S3_BUCKET" "$OUT/objects" ${S3_ENDPOINT_URL:+--endpoint-url "$S3_ENDPOINT_URL"}
         tar -C "$OUT/objects" -czf "$OUT/objects.tar.gz" . && rm -rf "$OUT/objects" ;;
  *) echo "unsupported STORAGE_DRIVER"; exit 2 ;;
esac
TABLES="organizations users systems assets findings finding_observations evidence poams approval_requests audit_events control_assignments implementations attestations policies"
python3 - "$OUT" "$PGURL" "$TABLES" <<'EOF'
import hashlib, json, subprocess, sys, datetime, pathlib
out, url, tables = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3].split()
q = lambda sql: subprocess.check_output(["psql", url, "-At", "-c", sql], text=True).strip()
counts = {t: int(q(f"select count(*) from {t}")) for t in tables}
head = q("select seq||':'||hash from audit_events order by seq desc limit 1")
arts = {p.name: {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size} for p in sorted(out.glob("*")) if p.name != "manifest.json"}
m = {"created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "alembic_revision": q("select version_num from alembic_version"),
     "artifacts": arts, "row_counts": counts, "audit_chain_head": head, "evidence_sha_sum": q("select md5(string_agg(sha256, ',' order by id)) from evidence")}
(out / "manifest.json").write_text(json.dumps(m, indent=1))
print(json.dumps({k: m[k] for k in ("alembic_revision", "audit_chain_head")}), "artifacts:", {k: v["sha256"][:12] for k, v in arts.items()})
EOF
echo "[backup] done: $OUT"
