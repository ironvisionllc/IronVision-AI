#!/usr/bin/env bash
# Migration check for the RMF accuracy release: copy the database, put the copy at 0023 (as deployed), then run
# 0023 → head → 0023 → head and compare legacy data. Never touches the source database.
set -euo pipefail
cd "$(dirname "$0")/../backend"
SRC_URL="$(grep '^DATABASE_URL=' .env | cut -d= -f2- | tr -d '"')"
PG_URL="${SRC_URL/postgresql+psycopg/postgresql}"
BASE="${PG_URL%/*}"
COPY_DB="mig_check_$(date +%s)"
psql "$BASE/postgres" -qc "CREATE DATABASE $COPY_DB" >/dev/null
trap 'psql "$BASE/postgres" -qc "DROP DATABASE IF EXISTS $COPY_DB" >/dev/null' EXIT
pg_dump --no-owner "$PG_URL" | psql -q "$BASE/$COPY_DB" >/dev/null
COPY_URL="${SRC_URL%/*}/$COPY_DB"
q() { psql "$BASE/$COPY_DB" -tAc "$1"; }
DATABASE_URL="$COPY_URL" alembic downgrade 0023 >/dev/null 2>&1
echo "copy at: $(q 'select version_num from alembic_version')"
BEFORE="$(q "select count(*), md5(string_agg(id::text||coalesce(confidentiality_impact,'')||coalesce(information_types::text,''), ',' order by id)) from systems")"
EV_BEFORE="$(q "select count(*), md5(string_agg(id::text||sha256||version, ',' order by id)) from evidence")"
DATABASE_URL="$COPY_URL" alembic upgrade head >/dev/null 2>&1
echo "upgraded to: $(q 'select version_num from alembic_version')"
echo "legacy categorizations copied (revision 1, legacy_unreviewed): $(q "select count(*) from categorization_records where submitted_by='migration 0024'")"
echo "systems with categorization data:                            $(q "select count(*) from systems where information_types is not null or confidentiality_impact is not null")"
echo "evidence version rows created: $(q "select count(*) from evidence_versions") for $(q "select count(*) from evidence") evidence records"
DATABASE_URL="$COPY_URL" alembic downgrade 0023 >/dev/null 2>&1
echo "downgraded to: $(q 'select version_num from alembic_version')"
[ "$BEFORE" = "$(q "select count(*), md5(string_agg(id::text||coalesce(confidentiality_impact,'')||coalesce(information_types::text,''), ',' order by id)) from systems")" ] && echo "systems unchanged after down: OK"
[ "$EV_BEFORE" = "$(q "select count(*), md5(string_agg(id::text||sha256||version, ',' order by id)) from evidence")" ] && echo "evidence unchanged after down: OK"
DATABASE_URL="$COPY_URL" alembic upgrade head >/dev/null 2>&1
echo "re-upgraded to: $(q 'select version_num from alembic_version')"
