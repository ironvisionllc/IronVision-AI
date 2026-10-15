#!/usr/bin/env bash
# IronVision recovery + deploy toolkit (customer Droplet). Idempotent, fail-safe, secrets redacted.
#   ./recover.sh preflight                         read-only checks + PLAN with plan-hash (also runs the config audit)
#   ./recover.sh rehearse [--cleanup] [--e2e]      isolated rehearsal: scratch DBs rec_*_<ts>, bucket evidence-rehearsal-<ts>,
#                                                  rehearsal backend on 127.0.0.1:8012 (not public), report in $RECOVERY_DIR
#   ./recover.sh apply --plan-hash H               needs a PASSING rehearsal (same hash, < 24h); fresh backups first; builds
#                                                  ironvision_recovered_<ts>, copy-only objects, switches DATABASE_URL, redeploys
#   ./recover.sh verify                            post-deploy checks (read-only except integrity job + round-trip probe)
#   ./recover.sh rollback [--remove-recovered-objects] [--restore-db-from FILE]
#   ./recover.sh status | audit | link --plan-hash H [keycloak-migrate flags]
# Env: RECOVER_ENV_FILE (deploy/digitalocean/.env.production), RECOVERY_DIR (/root/ironvision-recovery),
#      RECOVER_PREDEPLOY_DIR (/root/ironvision-predeploy), DATA_ROOT (/srv/ironvision). RECOVER_LOCAL=1: pod/test mode (no docker).
set -Eeuo pipefail
cd "$(dirname "$0")"
ENV_FILE=${RECOVER_ENV_FILE:-deploy/digitalocean/.env.production}
RDIR=${RECOVERY_DIR:-/root/ironvision-recovery}
PRE=${RECOVER_PREDEPLOY_DIR:-/root/ironvision-predeploy}
DATA_ROOT=${DATA_ROOT:-/srv/ironvision}
LOCAL=${RECOVER_LOCAL:-0}
mkdir -p "$RDIR" && chmod 700 "$RDIR"
LOG="$RDIR/recover.log"
TS=$(date -u +%Y%m%dt%H%M%S)
say() { printf '%s [recover] %s\n' "$(date -u +%FT%TZ)" "$*" | sed -E 's#(://[^:/@ ]+):[^@ ]+@#\1:***@#g' | tee -a "$LOG"; }
die() { say "FAILED: $*"; exit 1; }
envget() { python3 scripts/envget.py "$ENV_FILE" "$1" 2>/dev/null || true; }
trap 'say "aborted at line $LINENO (exit $?) – nothing after this point ran"' ERR

if [ "$LOCAL" != 1 ]; then
  [ -f "$ENV_FILE" ] || die "env file $ENV_FILE not found (run from /opt/ironvision/IronVision-AI)"
  [ -f "$DATA_ROOT/compose.env" ] || die "$DATA_ROOT/compose.env missing – deploy.sh writes it; run ./deploy.sh once first"
  for k in COMPOSE_PROJECT_NAME COMPOSE_FILE COMPOSE_PROFILES; do
    v=$(python3 scripts/envget.py "$DATA_ROOT/compose.env" "$k" 2>/dev/null || true); [ -n "$v" ] && export "$k=$v"
  done
  export COMPOSE_FILE="${COMPOSE_FILE:?COMPOSE_FILE missing in $DATA_ROOT/compose.env – run ./deploy.sh once}:deploy/compose/recovery.yml"
  DC=(docker compose --env-file "$ENV_FILE")
  RUNPY=("${DC[@]}" --profile recovery run --rm -T -e RECOVERY_DIR=/recovery -e RECOVER_PREDEPLOY_DIR=/predeploy recovery python -m app.tools.recovery)
else
  RUNPY=(bash -c 'cd backend && exec python -m app.tools.recovery "$@"' recovery)
fi
py() { "${RUNPY[@]}" "$@"; }

host_checks() {
  [ "$LOCAL" = 1 ] && { say "host checks: SKIPPED (RECOVER_LOCAL=1)"; return 0; }
  "${DC[@]}" ps --format '{{.Service}} {{.State}} {{.Health}}' | sed 's/^/  service /' | tee -a "$LOG"
  local cid img src owner free need
  cid=$("${DC[@]}" ps -q seaweedfs) || true
  [ -n "$cid" ] || die "seaweedfs container not running"
  [ "$(docker inspect -f '{{.State.Health.Status}}' "$cid")" = healthy ] || die "seaweedfs container not healthy"
  img=$(docker inspect -f '{{.Config.Image}}' "$cid"); case "$img" in *:latest|*[!:]) die "seaweedfs image not pinned: $img";; esac
  say "OK   seaweedfs image $img (pinned), healthy"
  src=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' "$cid")
  [ "$src" = "$DATA_ROOT/objectstore" ] || say "WARN seaweedfs /data is $src (expected $DATA_ROOT/objectstore on Block Storage)"
  owner=$(stat -c '%U:%G %a' "$src"); free=$(df -PB1 "$src" | awk 'NR==2{print $4}')
  need=$(( 2 * $(stat -c %s "$PRE/aegisrmf-minio-backup.tar.gz") ))
  [ "$free" -ge "$need" ] || die "objectstore free space $free < 2× archive ($need)"
  say "OK   objectstore $src owner $owner, free $((free>>20)) MiB (≥ 2× archive)"
  if docker port "$cid" 2>/dev/null | grep -vq '127.0.0.1'; then die "seaweedfs publishes a non-loopback port: $(docker port "$cid" | tr '\n' ' ')"; fi
  say "OK   seaweedfs: no public port"
  for s in backend worker; do
    if "${DC[@]}" exec -T "$s" python -c "import urllib.request as u;u.urlopen('http://seaweedfs:8333/healthz',timeout=5)" >/dev/null 2>&1; then
      say "OK   S3 endpoint reachable from $s"; else die "S3 endpoint http://seaweedfs:8333 NOT reachable from $s"; fi
  done
}

redeploy() {
  if [ "$LOCAL" = 1 ]; then eval "${RECOVER_REDEPLOY_CMD:-true}"; else ./deploy.sh "$ENV_FILE"; fi
}

switch_db() {  # $1 = database name; backs up the env file, sets DATABASE_URL in place
  local db=$1 u p
  u=$(envget POSTGRES_USER); p=$(envget POSTGRES_PASSWORD)
  if [ -z "$u" ] || [ -z "$p" ]; then die "POSTGRES_USER/POSTGRES_PASSWORD not in $ENV_FILE"; fi
  mkdir -p "$RDIR/backups/$TS"; cp -p "$ENV_FILE" "$RDIR/backups/$TS/env" && chmod 600 "$RDIR/backups/$TS/env"
  printf '{"ts":"%s","env_backup":"%s","previous_database_url_set":%s,"new_db":"%s"}\n' "$TS" "$RDIR/backups/$TS/env" \
    "$([ -n "$(envget DATABASE_URL)" ] && echo true || echo false)" "$db" > "$RDIR/env-switch-$TS.json"
  printf '%s' "postgresql+psycopg://$u:$p@postgres:5432/$db" | python3 scripts/envset.py "$ENV_FILE" DATABASE_URL >/dev/null
  say "DATABASE_URL switched to database $db (env backup $RDIR/backups/$TS/env)"
}

snapshot_objects() {
  [ "$LOCAL" = 1 ] && { say "objectstore snapshot: ${RECOVER_LOCAL_SNAPSHOT_CMD:-SKIPPED (local)}"; eval "${RECOVER_LOCAL_SNAPSHOT_CMD:-true}"; return 0; }
  local dst="$RDIR/backups/$TS/objectstore"
  "${DC[@]}" pause seaweedfs
  if ! cp -a "$DATA_ROOT/objectstore" "$dst"; then "${DC[@]}" unpause seaweedfs; die "SeaweedFS data-dir snapshot failed – apply refused"; fi
  "${DC[@]}" unpause seaweedfs
  say "OK   SeaweedFS data dir snapshot → $dst ($(du -sh "$dst" | cut -f1)) incl. filer metadata"
}

cmd=${1:-}; shift || true
case "$cmd" in
  preflight) host_checks; py preflight; "$0" audit || say "WARN audit reported problems (see above)";;
  rehearse)
    cleanup=0; e2e=""; for a in "$@"; do case $a in --cleanup) cleanup=1;; --e2e) e2e=--e2e;; esac; done
    out=$(py rehearse | tee -a "$LOG"); echo "$out"
    rts=$(sed -n 's/^REHEARSAL_TS=//p' <<<"$out" | tail -1); [ -n "$rts" ] || die "rehearsal did not produce a report"
    if [ "$LOCAL" = 1 ]; then py rehearse-probe --url "${RECOVER_REHEARSAL_URL:?RECOVER_REHEARSAL_URL}" $e2e
    else
      REHEARSAL_DB="rec_target_$rts" REHEARSAL_BUCKET="evidence-rehearsal-${rts/t/-}" "${DC[@]}" --profile recovery up -d --no-deps rehearsal-backend
      for _ in $(seq 1 60); do curl -sf -o /dev/null http://127.0.0.1:8012/api/v1/health/live && break; sleep 2; done
      py rehearse-probe --url http://rehearsal-backend:8001 $e2e || true
      if "${DC[@]}" restart seaweedfs && sleep 5 && py bucket-verify --db "rec_target_$rts" --bucket "evidence-rehearsal-${rts/t/-}"; then
        say "OK   SeaweedFS survived 'docker compose restart seaweedfs' (rehearsal bucket intact)"; else say "FAIL SeaweedFS restart check"; fi
      "${DC[@]}" --profile recovery stop rehearsal-backend >/dev/null
    fi
    [ "$cleanup" = 1 ] && py cleanup-rehearsal
    py status;;
  apply)
    if [ "${1:-}" != --plan-hash ] || [ -z "${2:-}" ]; then die "usage: ./recover.sh apply --plan-hash H"; fi
    [ "$(py plan-hash | tail -1)" = "$2" ] || die "plan-hash mismatch – run preflight + rehearse again"
    mkdir -p "$RDIR/backups/$TS"; cp -p "$ENV_FILE" "$RDIR/backups/$TS/env.pre-apply" 2>/dev/null || [ "$LOCAL" = 1 ] || die "env backup failed"
    snapshot_objects
    out=$(py apply --plan-hash "$2" | tee -a "$LOG"); echo "$out"
    db=$(sed -n 's/^RECOVERED_DB=//p' <<<"$out" | tail -1); [ -n "$db" ] || die "apply did not produce a recovered database – live system unchanged"
    switch_db "$db"; redeploy; py verify || die "verify failed after switch – run ./recover.sh rollback";;
  verify) py verify;;
  rollback)
    rm_obj=0; restore_from=""; while [ $# -gt 0 ]; do case $1 in --remove-recovered-objects) rm_obj=1;; --restore-db-from) restore_from=$2; shift;; esac; shift; done
    if [ -n "$restore_from" ]; then
      out=$(py restore-into-new --file "$restore_from"); echo "$out"; switch_db "$(sed -n 's/^NEW_DB=//p' <<<"$out" | tail -1)"
    else
      last=$(find "$RDIR" -maxdepth 1 -name 'env-switch-*.json' | sort | tail -1); [ -n "$last" ] || die "no env switch recorded – nothing to roll back"
      bk=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["env_backup"])' "$last")
      cp -p "$ENV_FILE" "$RDIR/backups/$TS-before-rollback.env"; cp -p "$bk" "$ENV_FILE"; say "env restored from $bk (recovered DB kept intact)"
      mv "$last" "${last%.json}.rolled-back.json"
    fi
    [ "$rm_obj" = 1 ] && py remove-recovered-objects
    redeploy; py verify;;
  status) py status; find "$RDIR" -maxdepth 1 -name '*.md' | sort | tail -5;;
  audit) scripts/recover_audit.sh "$ENV_FILE"; py audit-keycloak;;
  link)
    if [ "${1:-}" != --plan-hash ] || [ -z "${2:-}" ]; then die "usage: ./recover.sh link --plan-hash H  (hash from the keycloak-migrate dry run in the report)"; fi
    h=$2; shift 2
    exec scripts/keycloak.sh "$ENV_FILE" migrate --apply --create-identities --link --plan-hash "$h" "$@";;
  *) sed -n '2,13p' "$0"; exit 2;;
esac
