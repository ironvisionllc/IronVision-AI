#!/usr/bin/env bash
# AegisRMF restore + verification. Usage: scripts/restore.sh BACKUP_DIR
# Env: TARGET_DATABASE_URL (empty database), TARGET_STORAGE_ROOT (empty dir, local driver) – or STORAGE_DRIVER=s3 + S3_BUCKET,
#      PG_BIN as for backup.sh. Verification: artifact hashes vs manifest, row counts, every evidence object re-hashed against
#      its ledger SHA-256, and the audit hash chain recomputed end-to-end. Exit code != 0 on any mismatch.
set -euo pipefail
B="${1:?backup dir}"
PG_BIN="${PG_BIN:-}"; [ -n "$PG_BIN" ] && PG_BIN="${PG_BIN%/}/"
: "${TARGET_DATABASE_URL:?TARGET_DATABASE_URL required}"
PGURL="${TARGET_DATABASE_URL/postgresql+psycopg:/postgresql:}"
python3 - "$B" <<'EOF'
import hashlib, json, pathlib, sys
b = pathlib.Path(sys.argv[1]); m = json.loads((b / "manifest.json").read_text())
for n, a in m["artifacts"].items():
    if hashlib.sha256((b / n).read_bytes()).hexdigest() != a["sha256"]:
        sys.exit(f"[restore] FAIL artifact hash mismatch: {n}")
print("[restore] PASS artifact hashes match manifest")
EOF
"${PG_BIN}pg_restore" --no-owner --no-privileges --exit-on-error --dbname="$PGURL" "$B/db.dump"
echo "[restore] database restored"
case "${STORAGE_DRIVER:-local}" in
  local) : "${TARGET_STORAGE_ROOT:?TARGET_STORAGE_ROOT required}"; mkdir -p "$TARGET_STORAGE_ROOT"; tar -C "$TARGET_STORAGE_ROOT" -xzf "$B/objects.tar.gz" ;;
  s3)    T=$(mktemp -d); tar -C "$T" -xzf "$B/objects.tar.gz"; aws s3 sync "$T" "s3://$S3_BUCKET" ${S3_ENDPOINT_URL:+--endpoint-url "$S3_ENDPOINT_URL"} ;;
esac
echo "[restore] objects restored"
cd "$(dirname "$0")/../backend"
DATABASE_URL="$TARGET_DATABASE_URL" STORAGE_LOCAL_ROOT="${TARGET_STORAGE_ROOT:-}" python3 - "$B" <<'EOF'
import hashlib, json, pathlib, sys
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session
import os
b = pathlib.Path(sys.argv[1]); m = json.loads((b / "manifest.json").read_text())
eng = create_engine(os.environ["DATABASE_URL"])
ok = True
with Session(eng) as db:
    for t, n in m["row_counts"].items():
        got = db.execute(text(f"select count(*) from {t}")).scalar()
        if got != n:
            ok = False; print(f"[verify] FAIL row count {t}: {got} != {n}")
    print(f"[verify] row counts checked for {len(m['row_counts'])} tables")
    from app.models import Evidence
    from app.services.audit import verify_chain
    from app.services.storage import get_storage
    st, bad, n = get_storage(), 0, 0
    for e in db.scalars(select(Evidence)):
        n += 1
        try:
            if hashlib.sha256(st.get(e.storage_key)).hexdigest() != e.sha256:
                bad += 1
        except Exception:
            bad += 1
    print(f"[verify] evidence re-hashed: {n - bad}/{n} match ledger SHA-256"); ok &= bad == 0
    ch = verify_chain(db)
    head = db.execute(text("select seq||':'||hash from audit_events order by seq desc limit 1")).scalar()
    print(f"[verify] audit chain valid={ch['valid']} checked={ch['checked']} head_matches_manifest={head == m['audit_chain_head']}")
    ok &= ch["valid"] and head == m["audit_chain_head"]
    rev = db.execute(text("select version_num from alembic_version")).scalar()
    print(f"[verify] alembic revision {rev} (manifest {m['alembic_revision']})"); ok &= rev == m["alembic_revision"]
print("RESTORE_VERIFY:", "PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)
EOF
