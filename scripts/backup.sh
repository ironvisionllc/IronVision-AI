#!/usr/bin/env bash
# AegisRMF backup: pg_dump (custom format) + evidence object storage copy + manifest (SHA-256 per artifact, row counts,
# audit-chain head hash). Usage: scripts/backup.sh [OUT_DIR]
# Env: DATABASE_URL (required), KEYCLOAK_DB_URL (optional – also dumps the Keycloak DB to keycloak.dump), STORAGE_DRIVER=local|s3, STORAGE_LOCAL_ROOT (local), S3_* (s3 – copied with our objsync helper, no mc/aws cli),
#      OBJSYNC (command prefix; default `python3 -m app.tools.objsync` run from backend/, or e.g. `docker compose run --rm -T backend python -m app.tools.objsync`),
#      PG_BIN (dir with pg_dump matching the server major version, e.g. /usr/lib/postgresql/16/bin)
set -euo pipefail
OUT="${1:-./backups/aegisrmf-$(date -u +%Y%m%dT%H%M%SZ)}"
PG_BIN="${PG_BIN:-}"; [ -n "$PG_BIN" ] && PG_BIN="${PG_BIN%/}/"
: "${DATABASE_URL:?DATABASE_URL required}"
PGURL="${DATABASE_URL/postgresql+psycopg:/postgresql:}"
mkdir -p "$OUT"
echo "[backup] database -> $OUT/db.dump"
"${PG_BIN}pg_dump" --format=custom --no-owner --no-privileges --file="$OUT/db.dump" "$PGURL"
if [ -n "${KEYCLOAK_DB_URL:-}" ]; then   # optional: Keycloak database (separate DB/role on the same server)
  echo "[backup] keycloak database -> $OUT/keycloak.dump"
  "${PG_BIN}pg_dump" --format=custom --no-owner --no-privileges --file="$OUT/keycloak.dump" "$KEYCLOAK_DB_URL"
fi
case "${STORAGE_DRIVER:-local}" in
  local) : "${STORAGE_LOCAL_ROOT:?STORAGE_LOCAL_ROOT required}"
         echo "[backup] objects (local) -> $OUT/objects.tar.gz"
         tar -C "$STORAGE_LOCAL_ROOT" -czf "$OUT/objects.tar.gz" . ;;
  s3)    : "${S3_BUCKET:?S3_BUCKET required}"
         echo "[backup] objects (s3://$S3_BUCKET) -> $OUT/objects/"
         OUT_ABS="$(cd "$OUT" && pwd)"
         (cd "$(dirname "$0")/../backend" && ${OBJSYNC:-python3 -m app.tools.objsync} copy s3 "dir:$OUT_ABS/objects")
         cp "$OUT/objects/.objsync-manifest.json" "$OUT/objects-manifest.json"
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
