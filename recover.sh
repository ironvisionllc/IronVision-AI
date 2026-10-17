#!/usr/bin/env bash
# IronVision recovery + deploy toolkit (customer Droplet). Idempotent, fail-safe, secrets redacted.
# Minimal operator flow:
#   sudo ./recover.sh run                          READ-ONLY vs production: legacy inspection + verified backups (prod DB,
#                                                  Keycloak DB, bucket manifest, SeaweedFS data, env, legacy DBs, legacy MinIO
#                                                  export) + preflight + isolated rehearsal + SSO probe → report + PLAN-HASH
#   sudo ./recover.sh cutover --plan-hash H        apply (new DB, copy-only objects) → switch → deploy → Keycloak link →
#                                                  verify + live e2e SSO + doctor + SeaweedFS restart; any failure → auto rollback
#   sudo ./recover.sh finalize                     reboot-persistence check, then gracefully stop legacy containers (optional)
#   sudo ./recover.sh rollback [--remove-recovered-objects] [--restore-db-from FILE]
#   sudo ./recover.sh resolve-conflict             verified legacy backup, then stop ONLY port-conflicting legacy containers
# Building blocks: preflight | rehearse [--cleanup] [--e2e] | apply --plan-hash H | verify | status | audit | link --plan-hash H
# Env: RECOVER_ENV_FILE (deploy/digitalocean/.env.production), RECOVERY_DIR (/root/ironvision-recovery),
#      RECOVER_PREDEPLOY_DIR (/root/ironvision-predeploy), DATA_ROOT (/srv/ironvision), RECOVER_LEGACY_PROJECT (aegisrmf).
#      RECOVER_LOCAL=1: pod/test mode (no compose; docker only for legacy containers).
set -Eeuo pipefail
cd "$(dirname "$0")"
ENV_FILE=${RECOVER_ENV_FILE:-deploy/digitalocean/.env.production}
case $ENV_FILE in /*) RECOVER_ENV_FILE=$ENV_FILE;; *) RECOVER_ENV_FILE=$PWD/$ENV_FILE;; esac; export RECOVER_ENV_FILE  # rehearsal-backend env_file
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
  RUNPY=("${DC[@]}" --profile recovery run --rm -T -e RECOVERY_DIR=/recovery -e RECOVER_PREDEPLOY_DIR=/predeploy)
else
  RUNPY=()
fi
LEGACY_PROJECT=${RECOVER_LEGACY_PROJECT:-aegisrmf}
image_gate() {  # host: static manifest check → build the recovery image → package check INSIDE the image (fail-safe)
  [ "$LOCAL" = 1 ] && return 0
  python3 scripts/check_requirements.py | tee -a "$LOG" || die "requirements static check (host) failed – nothing was built or changed"
  "${DC[@]}" --profile recovery build recovery 2>&1 | tee -a "$LOG" || die "recovery image build failed – nothing was changed"
  "${DC[@]}" --profile recovery run --rm --no-deps -T -v "$PWD:/repo:ro" recovery \
    python /repo/scripts/check_requirements.py --in-env --target recovery --app-dir /app/backend | tee -a "$LOG" \
    || die "recovery image package check (in image: pip check, installed == pinned == lock, imports) failed – nothing was changed"
}
cpath() {  # host path → path inside the recovery container
  if [ "$LOCAL" = 1 ]; then echo "$1"; return; fi
  case $1 in "$PRE"*) echo "/predeploy${1#"$PRE"}";; "$RDIR"*) echo "/recovery${1#"$RDIR"}";; *) echo "$1";; esac
}
SRC_E=()
load_sources() {  # sources chosen by `run` (snapshots), so cutover uses exactly what was rehearsed
  SRC_E=()
  [ -f "$RDIR/sources.env" ] || return 0
  while IFS='=' read -r k v; do
    case $k in ''|\#*) continue;; esac
    if [ "$LOCAL" = 1 ]; then export "$k=$v"; else SRC_E+=(-e "$k=$(cpath "$v")"); fi
  done < "$RDIR/sources.env"
}
load_sources
sync_db_env() {  # local/test mode: follow the env file's DATABASE_URL (the cutover switches it)
  [ "$LOCAL" = 1 ] || return 0
  local d; d=$(envget DATABASE_URL); [ -z "$d" ] || export DATABASE_URL="$d"
}
py() {
  if [ "$LOCAL" = 1 ]; then sync_db_env; (cd backend && exec python -m app.tools.recovery "$@")
  else "${RUNPY[@]}" "${SRC_E[@]}" recovery python -m app.tools.recovery "$@"; fi
}
legacy() { python3 scripts/legacy_project.py "$@" --env-file "$ENV_FILE"; }
legacy_present() { [ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$LEGACY_PROJECT" 2>/dev/null)$(docker ps -aq --filter "name=^$LEGACY_PROJECT-" 2>/dev/null)" ]; }
legacy_backup_dir() { sed -n 's/^RECOVER_LEGACY_BACKUP=//p' "$RDIR/sources.env" 2>/dev/null | tail -1; }

image_pin() {  # service container configured-ref running-ref strict|warn
  local ref=${3:-$4} digs rc=0 msg fix="docker compose --env-file $ENV_FILE pull $1 && docker compose --env-file $ENV_FILE up -d $1"
  digs=$(docker image inspect "$(docker inspect -f '{{.Image}}' "$2")" -f '{{join .RepoDigests " "}}' 2>/dev/null || true)
  msg=$(python3 scripts/image_digest.py check "$ref" "$digs") || rc=$?
  case $rc in
    0) say "OK   $1 image: $msg";;
    3) if [ "$5" = strict ] && [ "$(envget DEPLOYMENT_KIND)" = customer ]; then die "$1 image $ref is tag-only – customer production requires a digest pin (env.customer-production.template)"; fi
       say "WARN $1 image $ref is tag-only (allowed on demo) – pin it by digest (demo: ./deploy.sh --apply-demo-settings --yes)";;
    4) say "WARN $1: $msg";;
    *) [ "$5" = strict ] && die "$1: $msg – fix: $fix"; say "WARN $1: $msg – fix: $fix";;
  esac
}

host_checks() {
  [ "$LOCAL" = 1 ] && { say "host checks: SKIPPED (RECOVER_LOCAL=1)"; return 0; }
  "${DC[@]}" ps --format '{{.Service}} {{.State}} {{.Health}}' | sed 's/^/  service /' | tee -a "$LOG"
  local cid img src owner free need
  cid=$("${DC[@]}" ps -q seaweedfs) || true
  [ -n "$cid" ] || die "seaweedfs container not running"
  [ "$(docker inspect -f '{{.State.Health.Status}}' "$cid")" = healthy ] || die "seaweedfs container not healthy"
  img=$(docker inspect -f '{{.Config.Image}}' "$cid")
  image_pin seaweedfs "$cid" "$(envget SEAWEEDFS_IMAGE)" "$img" strict
  local s c
  for s in postgres:POSTGRES_IMAGE edge:EDGE_NGINX_IMAGE; do
    c=$("${DC[@]}" ps -q "${s%%:*}" 2>/dev/null) || true
    [ -n "$c" ] && image_pin "${s%%:*}" "$c" "$(envget "${s#*:}")" "$(docker inspect -f '{{.Config.Image}}' "$c")" warn
  done
  say "OK   seaweedfs healthy"
  src=$(docker inspect -f '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' "$cid")
  [ "$src" = "$DATA_ROOT/objectstore" ] || say "WARN seaweedfs /data is $src (expected $DATA_ROOT/objectstore on Block Storage)"
  owner=$(stat -c '%U:%G %a' "$src"); free=$(df -PB1 "$src" | awk 'NR==2{print $4}')
  need=$(( 2 * $(stat -c %s "$PRE/aegisrmf-minio-backup.tar.gz" 2>/dev/null || echo 0) ))
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

load_kv() {  # export plain KEY=VALUE lines written by scratch_sso (0600); parsed, never sourced/executed
  local k v
  while IFS='=' read -r k v; do [[ $k =~ ^[A-Z_][A-Z0-9_]*$ ]] && export "$k=$v"; done < "$1"
}

sso_up() {  # $1 rts: isolated scratch Keycloak + ephemeral identities; SCRATCH_* exported for the rehearsal backend only (never in the env file)
  local sd="$RDIR/scratch-sso-$1"
  py scratch-sso prepare --ts "$1" || return 1
  load_kv "$sd/kc.env"
  if [ "$LOCAL" = 1 ]; then
    kcu=${RECOVER_SCRATCH_KC_URL:?RECOVER_SCRATCH_KC_URL}; app=${RECOVER_REHEARSAL_URL:?RECOVER_REHEARSAL_URL}
    eval "${RECOVER_LOCAL_SCRATCH_KC_START:?RECOVER_LOCAL_SCRATCH_KC_START}" || return 1
  else
    kcu=http://rehearsal-keycloak:8080; app=http://127.0.0.1:8001
    "${DC[@]}" --profile recovery up -d --no-deps --wait --wait-timeout 300 rehearsal-keycloak 2>&1 | tee -a "$LOG" || return 1
  fi
  py scratch-sso setup --ts "$1" --kc-url "$kcu" --app-url "$app" || return 1
  load_kv "$sd/backend.env"
}

sso_down() {  # always (pass, fail or abort): scratch users → scratch container → scratch DB/role + secret files → report
  local rc=0
  trap - EXIT
  py scratch-sso cleanup-users --ts "$1" --kc-url "${kcu:-}" || true
  if [ "$LOCAL" = 1 ]; then eval "${RECOVER_LOCAL_SCRATCH_KC_STOP:-true}" || rc=$?
  else "${DC[@]}" --profile recovery rm -sf rehearsal-keycloak >/dev/null 2>&1 || rc=$?; fi   # the scratch service only
  py scratch-sso cleanup-finish --ts "$1" --container-rc "$rc" | tee -a "$LOG" || true
  unset KC_DB_PASSWORD KC_BOOTSTRAP_ADMIN_PASSWORD SCRATCH_OIDC_CLIENT_SECRET SCRATCH_DEMO_PASSWORD SCRATCH_DEMO_LAUNCHER_CLIENT_SECRET SCRATCH_BACKEND_CLIENT_SECRET
}

rb_cid() { "${DC[@]}" --profile recovery ps -aq rehearsal-backend 2>/dev/null | head -1; }
rb_state() { docker inspect -f '{{.State.Status}} exit={{.State.ExitCode}} health={{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$(rb_cid)" 2>/dev/null || echo "no container"; }
rb_nets() { docker inspect -f '{{range $k,$v := .NetworkSettings.Networks}}{{$k}}={{$v.IPAddress}} {{end}}' "$(rb_cid)" 2>/dev/null || true; }
rehearsal_diag() {  # $1 rehearsal ts, $2 OIDC issuer host: container, state, networks, DNS seen from BOTH containers, backend log
  local cid; cid=$(rb_cid)
  say "rehearsal-backend: container ${cid:-<none>}, state $(rb_state), networks: $(rb_nets)"
  [ -n "$cid" ] && docker logs --tail 150 "$cid" 2>&1 | sed -E 's#(://[^:/@ ]+):[^@ ]+@#\1:***@#g' > "$RDIR/rehearsal-backend-$1.log" && chmod 600 "$RDIR/rehearsal-backend-$1.log"
  "${RUNPY[@]}" recovery python -m app.tools.netdiag --out "/recovery/netdiag-$1-recovery-container.json" rehearsal-backend postgres keycloak seaweedfs "$2" 2>&1 >/dev/null | tee -a "$LOG" || true
  if [ "$(docker inspect -f '{{.State.Running}}' "$cid" 2>/dev/null)" = true ]; then
    "${DC[@]}" --profile recovery exec -T rehearsal-backend python -m app.tools.netdiag --out "/recovery/netdiag-$1.json" postgres keycloak seaweedfs "$2" 2>&1 >/dev/null | tee -a "$LOG" || true
  fi
}

switch_db() {  # $1 = database name; backs up the env file, sets DATABASE_URL in place
  local db=$1 u p
  u=$(envget POSTGRES_USER); p=$(envget POSTGRES_PASSWORD)
  if [ -z "$u" ] || [ -z "$p" ]; then die "POSTGRES_USER/POSTGRES_PASSWORD not in $ENV_FILE"; fi
  mkdir -p "$RDIR/backups/$TS"; cp -p "$ENV_FILE" "$RDIR/backups/$TS/env" && chmod 600 "$RDIR/backups/$TS/env"
  printf '{"ts":"%s","env_backup":"%s","previous_database_url_set":%s,"new_db":"%s"}\n' "$TS" "$RDIR/backups/$TS/env" \
    "$([ -n "$(envget DATABASE_URL)" ] && echo true || echo false)" "$db" > "$RDIR/env-switch-$TS.json"
  printf '%s' "postgresql+psycopg://$u:$p@${RECOVER_DB_HOST:-postgres}:${RECOVER_DB_PORT:-5432}/$db" | python3 scripts/envset.py "$ENV_FILE" DATABASE_URL >/dev/null
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
    piss=$(envget OIDC_ISSUER 2>/dev/null || true); piss=${piss:-${OIDC_ISSUER:-}}
    if [ "$LOCAL" = 1 ]; then forbid=${RECOVER_FORBIDDEN_HOSTS:-}
    else h=${piss#*://}; forbid="${h%%/*},$(envget APP_DOMAIN)"; fi
    export REHEARSAL_FORBIDDEN_HOSTS=$forbid
    if [ -n "$e2e" ]; then
      trap 'sso_down "$rts"' EXIT
      sso_up "$rts" || say "FAIL scratch SSO stack setup (rehearsal will FAIL; cleanup follows)"
    fi
    if [ "$LOCAL" = 1 ]; then
      if [ -n "${RECOVER_LOCAL_REHEARSAL_BACKEND_CMD:-}" ]; then
        export REHEARSAL_DB="rec_target_$rts" REHEARSAL_BUCKET="evidence-rehearsal-${rts/t/-}"; eval "$RECOVER_LOCAL_REHEARSAL_BACKEND_CMD"
      fi
      py rehearse-probe --url "${RECOVER_REHEARSAL_URL:?RECOVER_REHEARSAL_URL}" --where "local rehearsal backend (RECOVER_LOCAL=1)" $e2e || true
    else
      # Probes run INSIDE the rehearsal-backend container → http://127.0.0.1:8001 (its own network namespace): no Docker DNS
      # needed to reach the app. Before: probed http://rehearsal-backend:8001 from a separate `run` container, unchecked `up`.
      export REHEARSAL_DB="rec_target_$rts" REHEARSAL_BUCKET="evidence-rehearsal-${rts/t/-}"
      iss=$(envget OIDC_ISSUER); iss=${iss#*://}; iss=${iss%%[:/]*}
      if ! "${DC[@]}" --profile recovery up -d --no-deps --wait --wait-timeout 240 rehearsal-backend 2>&1 | tee -a "$LOG"; then
        rehearsal_diag "$rts" "$iss"
        py probe-unreachable --reason "rehearsal-backend did not become healthy ($(rb_state); networks $(rb_nets))" --netdiag "/recovery/netdiag-$rts-recovery-container.json" || true
        "${DC[@]}" --profile recovery stop rehearsal-backend >/dev/null 2>&1 || true
        die "rehearsal backend not healthy – see $RDIR/rehearsal-backend-$rts.log and netdiag-$rts*.json"
      fi
      rehearsal_diag "$rts" "$iss"
      "${DC[@]}" --profile recovery exec -T -e RECOVERY_DIR=/recovery -e REHEARSAL_FORBIDDEN_HOSTS rehearsal-backend python -m app.tools.recovery rehearse-probe \
        --url http://127.0.0.1:8001 --where "inside rehearsal-backend container; networks $(rb_nets)" --netdiag "/recovery/netdiag-$rts.json" $e2e | tee -a "$LOG" || true
      if [ "${RECOVER_SKIP_LIVE_RESTART:-0}" = 1 ]; then say "SeaweedFS restart check: deferred to cutover (run never restarts production services)"
      elif "${DC[@]}" restart seaweedfs && sleep 5 && py bucket-verify --db "rec_target_$rts" --bucket "evidence-rehearsal-${rts/t/-}"; then
        say "OK   SeaweedFS survived 'docker compose restart seaweedfs' (rehearsal bucket intact)"; else say "FAIL SeaweedFS restart check"; fi
      "${DC[@]}" --profile recovery stop rehearsal-backend >/dev/null
    fi
    [ -n "$piss" ] && { py scratch-sso prod-oidc-check --issuer "$piss" | tee -a "$LOG" || true; }
    [ -n "$e2e" ] && sso_down "$rts"
    [ "$cleanup" = 1 ] && py cleanup-rehearsal
    py status;;
  apply)
    if [ "${1:-}" != --plan-hash ] || [ -z "${2:-}" ]; then die "usage: ./recover.sh apply --plan-hash H [--accept-evidence-exceptions E]"; fi
    ack=(); [ "${3:-}" = --accept-evidence-exceptions ] && [ -n "${4:-}" ] && ack=(--accept-evidence-exceptions "$4")
    [ "$(py plan-hash | tail -1)" = "$2" ] || die "plan-hash mismatch (or produced by an older recovery tool version) – run ./recover.sh run again"
    mkdir -p "$RDIR/backups/$TS"; cp -p "$ENV_FILE" "$RDIR/backups/$TS/env.pre-apply" 2>/dev/null || [ "$LOCAL" = 1 ] || die "env backup failed"
    snapshot_objects
    if ! out=$(py apply --plan-hash "$2" "${ack[@]}" 2>&1 | tee -a "$LOG"); then
      echo "$out"; die "apply refused or failed (reason above) – live system unchanged"
    fi
    echo "$out"
    db=$(sed -n 's/^RECOVERED_DB=//p' <<<"$out" | tail -1); [ -n "$db" ] || die "apply did not produce a recovered database – live system unchanged"
    switch_db "$db"; redeploy; py verify || die "verify failed after switch – run ./recover.sh rollback";;
  run)
    say "run: READ-ONLY against the production DB, bucket and Keycloak; legacy containers stay running"
    image_gate
    lrc=0; legacy inspect "$LEGACY_PROJECT" | tee -a "$LOG" || lrc=$?
    say "legacy verdict exit $lrc (0 safe · 10 port conflict · 11 production depends on legacy) – nothing is stopped by run"
    lb=""
    if legacy_present; then
      lb="$PRE/legacy-$TS"
      legacy backup "$LEGACY_PROJECT" --out "$lb" | tee -a "$LOG" || die "legacy backup failed – nothing changed"
    fi
    python3 scripts/legacy_project.py sources --backup "$lb" --default-db "${RECOVER_DEFAULT_SOURCE_BACKUP:-$PRE/aegisrmf-old-db.backup}" \
      --default-archive "${RECOVER_DEFAULT_OBJECT_ARCHIVE:-$PRE/aegisrmf-minio-backup.tar.gz}" > "$RDIR/sources.env.new"
    mv "$RDIR/sources.env.new" "$RDIR/sources.env"; chmod 600 "$RDIR/sources.env"; sed 's/^/  sources: /' "$RDIR/sources.env" | tee -a "$LOG"
    load_sources
    mkdir -p "$RDIR/backups/run-$TS"; cp -p "$ENV_FILE" "$RDIR/backups/run-$TS/env" 2>/dev/null || [ "$LOCAL" = 1 ] || die "env backup failed"
    py backup || die "pre-run backups failed – nothing changed"
    if [ "$LOCAL" != 1 ]; then
      cp -a "$DATA_ROOT/objectstore" "$RDIR/backups/run-$TS/objectstore" || die "SeaweedFS data snapshot failed"
      say "OK   SeaweedFS data dir copied (live, not paused – cutover takes a paused snapshot)"
    fi
    host_checks; py preflight || die "preflight FAILED – see above"
    if [ "$LOCAL" != 1 ]; then "$0" audit || say "WARN audit reported problems (see above)"; fi
    RECOVER_SKIP_LIVE_RESTART=1 "$0" rehearse --e2e || die "rehearsal FAILED – see report"
    passed=$(python3 -c 'import json,glob,sys;print(json.load(open(sorted(glob.glob(sys.argv[1]+"/rehearsal-*.json"))[-1]))["passed"])' "$RDIR")
    [ "$passed" = True ] || die "rehearsal did not pass – see $RDIR/report-*.md"
    ph=$(py plan-hash | tail -1)
    read -r ev_ok ev_n ev_h < <(python3 -c 'import json,glob,sys;b=json.load(open(sorted(glob.glob(sys.argv[1]+"/rehearsal-*.json"))[-1]));i=b["result"]["objects"]["integrity"];print(i["verified"],i["records"],i["exceptions_hash"] or "-")' "$RDIR")
    say "PLAN-HASH $ph"
    if [ "$ev_h" = - ]; then say "evidence integrity: $ev_ok/$ev_n VERIFIED – COMPLETE"; cut="sudo ./recover.sh cutover --plan-hash $ph"
    else say "evidence integrity: $ev_ok/$ev_n VERIFIED – INCOMPLETE (exceptions listed in the report)"; cut="sudo ./recover.sh cutover --plan-hash $ph --accept-evidence-exceptions $ev_h"; fi
    say "Review $(find "$RDIR" -maxdepth 1 -name 'report-*.md' | sort | tail -1), then run: $cut";;
  cutover)
    if [ "${1:-}" != --plan-hash ] || [ -z "${2:-}" ]; then die "usage: sudo ./recover.sh cutover --plan-hash H [--accept-evidence-exceptions E]  (H, E printed by ./recover.sh run)"; fi
    h=$2; ack=(); [ "${3:-}" = --accept-evidence-exceptions ] && [ -n "${4:-}" ] && ack=(--accept-evidence-exceptions "$4")
    [ -f "$RDIR/sources.env" ] || die "no ./recover.sh run recorded – run it first"
    image_gate
    switches() { find "$RDIR" -maxdepth 1 -name 'env-switch-*.json' ! -name '*rolled-back*' | wc -l; }
    before=$(switches)
    fail() {
      if [ "$(switches)" -gt "$before" ]; then say "cutover FAILED: $1 – automatic rollback to the previous env/DB"; "$0" rollback || say "ROLLBACK FAILED – run: sudo ./recover.sh rollback"
      else say "cutover FAILED: $1 – before the DATABASE_URL switch, production unchanged"; fi
      exit 1
    }
    "$0" apply --plan-hash "$h" "${ack[@]}" || fail "apply / deploy / verify"
    if [ "$LOCAL" = 1 ]; then
      sync_db_env
      (cd backend && python -m app.cli keycloak-migrate --report "$RDIR/kc-migrate-$TS.json") >> "$LOG" 2>&1 || fail "keycloak-migrate dry run"
      kh=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("plan_hash",""))' "$RDIR/kc-migrate-$TS.json")
      bk=$(dirname "$(find "$RDIR/backups" -maxdepth 2 -name manifest.json | sort | tail -1)")
      (cd backend && python -m app.cli keycloak-migrate --apply --create-identities --link --plan-hash "$kh" --backup-ref "$bk" --credentials-dir "$RDIR/credentials" --report "$RDIR/kc-link-$TS.json" --yes) | tee -a "$LOG" || fail "Keycloak identity link"
      python3 scripts/e2e_sso.py --base "${RECOVER_LIVE_URL:?RECOVER_LIVE_URL}" --register --demo ${RECOVER_E2E_INSECURE:+--insecure-cookies} | tee -a "$LOG" || fail "live end-to-end SSO"
      (cd backend && python -m app.tools.keycloak_doctor) | tee -a "$LOG" || fail "keycloak doctor"
      eval "${RECOVER_LOCAL_RESTART_CMD:-true}" || fail "SeaweedFS restart"
    else
      out=$(scripts/keycloak.sh "$ENV_FILE" migrate 2>&1) || fail "keycloak-migrate dry run"; printf '%s\n' "$out" >> "$LOG"
      kh=$(grep -oE -- '--plan-hash [0-9a-f]+' <<<"$out" | tail -1 | awk '{print $2}')
      if [ -n "$kh" ]; then scripts/keycloak.sh "$ENV_FILE" migrate --apply --create-identities --link --plan-hash "$kh" --yes | tee -a "$LOG" || fail "Keycloak identity link"
      else say "keycloak-migrate: nothing to link"; fi
      "${DC[@]}" --profile recovery run --rm -T recovery python /app/scripts/e2e_sso.py --base "https://$(envget APP_DOMAIN)" --register --demo | tee -a "$LOG" || fail "live end-to-end SSO"
      scripts/keycloak.sh "$ENV_FILE" doctor | tee -a "$LOG" || fail "keycloak doctor"
      "${DC[@]}" restart seaweedfs >/dev/null || fail "SeaweedFS restart"; sleep 10
    fi
    py verify || fail "verify after SeaweedFS restart"
    printf '{"ts":"%s","epoch":%s,"plan_hash":"%s"}\n' "$TS" "$(date +%s)" "$h" > "$RDIR/cutover-ok-$TS.json"
    say "CUTOVER SUCCEEDED (verify, live SSO, doctor, SeaweedFS restart). Optional: sudo reboot, then sudo ./recover.sh finalize";;
  finalize)
    ok=$(find "$RDIR" -maxdepth 1 -name 'cutover-ok-*.json' | sort | tail -1); [ -n "$ok" ] || die "no successful cutover recorded – finalize only runs after cutover"
    py verify || die "verify failed – not finalizing (legacy containers left running)"
    cut_epoch=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["epoch"])' "$ok")
    boot=${RECOVER_BOOT_EPOCH:-$(( $(date +%s) - $(cut -d. -f1 /proc/uptime) ))}
    if [ "$boot" -gt "$cut_epoch" ]; then say "OK   reboot persistence: booted after the cutover and verify passed (DB + SeaweedFS objects)"
    else say "REMINDER reboot persistence not proven yet: sudo reboot, then sudo ./recover.sh finalize"; fi
    lb=$(legacy_backup_dir); if [ -z "$lb" ]; then say "no legacy containers were found by run – nothing to stop"; exit 0; fi
    legacy stop "$LEGACY_PROJECT" --backup "$lb" --yes | tee -a "$LOG" || die "legacy containers NOT stopped (see above)";;
  resolve-conflict)
    lb=$(legacy_backup_dir)
    if [ -z "$lb" ] || [ ! -f "$lb/manifest.json" ]; then
      lb="$PRE/legacy-$TS"; legacy backup "$LEGACY_PROJECT" --out "$lb" | tee -a "$LOG" || die "legacy backup failed – nothing stopped"
    fi
    say "stopping ONLY legacy containers holding ports the ironvision stack needs; their data is in the verified backup $lb, which (or the backup files) is the recovery source from now on"
    legacy stop "$LEGACY_PROJECT" --backup "$lb" --only-conflicting --yes | tee -a "$LOG" || die "not stopped (see above)";;
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
