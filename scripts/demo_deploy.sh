#!/usr/bin/env bash
# ./deploy.sh --demo-without-recovery : deploy the CURRENT checkout as the demo against the original `ironvision` DB,
# recovery DEFERRED. Never touches legacy (aegisrmf) containers/volumes, /root/ironvision-predeploy or the recovery dir.
#   scripts/demo_deploy.sh prepare ENV_FILE        read-only preflight + rollback snapshot (env + running app images) → prints SNAP dir
#   scripts/demo_deploy.sh run ENV_FILE SNAP [deploy flags]   settings check → deploy (verified backup, migrate + demo seed,
#                                                   realm apply, readiness) → launcher-only link → smoke; any failure → rollback
set -Eeuo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
MODE="${1:?prepare|run}"; F="${2:?ENV_FILE}"; shift 2
RDIR="${RECOVERY_DIR:-/root/ironvision-recovery}"
say() { printf '\n#### [demo-without-recovery] %s\n' "$*" >&2; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
get() { python3 scripts/envget.py "$F" "$1"; }
DATA_ROOT="$(get DATA_ROOT)"
dc() {  # compose set of the previous deploy (written by scripts/deploy.sh)
  local ce="$DATA_ROOT/compose.env" f; DC=(docker compose --env-file "$F")
  [ -f "$ce" ] || return 1
  IFS=: read -r -a CFS <<<"$(python3 scripts/envget.py "$ce" COMPOSE_FILE)"
  for f in "${CFS[@]}"; do DC+=(-f "$f"); done
  DC+=(-p "$(python3 scripts/envget.py "$ce" COMPOSE_PROJECT_NAME)")
}

if [ "$MODE" = prepare ]; then
  say "1 preflight (read-only)"
  python3 scripts/demo_preflight.py "$F" --recovery-dir "$RDIR" >&2 || exit $?
  SNAP="$DATA_ROOT/backups/demo-deploy-$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$SNAP"; chmod 700 "$SNAP"
  python3 scripts/envset.py --copy "$F" "$SNAP/env" || die "env snapshot failed – nothing changed"
  : > "$SNAP/images"
  if dc; then
    for s in backend worker frontend edge; do
      cid="$("${DC[@]}" ps -q "$s" 2>/dev/null | head -n1 || true)"; [ -n "$cid" ] || continue
      ref="$(docker inspect -f '{{.Config.Image}}' "$cid")"; id="$(docker inspect -f '{{.Image}}' "$cid")"
      docker image tag "$id" "ironvision-rollback/$s:$(basename "$SNAP")"   # keeps the old image from being pruned
      printf '%s %s %s\n' "$s" "$ref" "$id" >> "$SNAP/images"
    done
  fi
  echo "rollback snapshot $SNAP: env + $(wc -l < "$SNAP/images") running app image(s)" >&2
  echo "$SNAP"; exit 0
fi

SNAP="${1:?SNAP}"; shift
FAILED_STEP=""
rollback() {
  local rc=$?; trap - ERR; set +e
  say "ROLLBACK (failed step: $FAILED_STEP)"
  python3 scripts/envset.py --copy "$SNAP/env" "$F" && echo "  env restored from $SNAP/env" >&2
  if [ -s "$SNAP/images" ] && dc; then
    svcs=()
    while read -r s ref id; do docker image tag "$id" "$ref" && svcs+=("$s"); done < "$SNAP/images"
    "${DC[@]}" up -d --no-deps --no-build "${svcs[@]}" && echo "  previous images restarted: ${svcs[*]}" >&2
    for _ in $(seq 1 30); do
      "${DC[@]}" exec -T backend python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8001/api/v1/ready', timeout=5)" >/dev/null 2>&1 \
        && { echo "  backend ready on the previous images" >&2; break; }; sleep 4
    done
  else
    echo "  no previous app images recorded – only the env file was restored" >&2
  fi
  echo "  database: NOT rolled back (migrations/demo seed are forward-only); pre-deploy backup: ${BK:-none} – restore only manually (docs/BACKUP_RESTORE.md)" >&2
  echo "  legacy containers, volumes, /root/ironvision-predeploy and $RDIR were not touched" >&2
  exit "${rc:-1}"
}
trap rollback ERR
step() { FAILED_STEP="$1"; say "$1"; }

step "2 demo settings check"
declare -A WANT=([DEPLOYMENT_KIND]=demo [ALLOW_DEMO_LOGIN]=true [KEYCLOAK_ALLOW_REGISTRATION]=true [SEED_DEMO_DATA]=false
                 [ALLOW_SIGNUP]=false [APP_ENV]=production)
for k in "${!WANT[@]}"; do [ "$(get "$k")" = "${WANT[$k]}" ] || { echo "  $k must be ${WANT[$k]} (is '$(get "$k")')" >&2; false; }; done
case "$(get ALLOW_INSECURE_PRODUCTION)" in ""|false) ;; *) echo "  ALLOW_INSECURE_PRODUCTION must be unset or false" >&2; false ;; esac
echo "  OK ${!WANT[*]} + ALLOW_INSECURE_PRODUCTION off" >&2

step "3 deploy current checkout (legacy retained, verified pre-deploy backup, migrate + demo seed, realm apply, readiness)"
DEPLOY_REQUIRE_BACKUP=1 scripts/deploy.sh "$F" --apply-realm "$@"
BK="$(find "$DATA_ROOT/backups" -maxdepth 1 -name 'ironvision-*' -type d -newer "$SNAP/env" | sort | tail -n1)"

step "4 Keycloak: link the demo launcher identity ONLY (dry run → review → apply)"
before="$(ls "$DATA_ROOT/secrets"/keycloak-migrate-*.json 2>/dev/null | sort | tail -n1 || true)"
scripts/keycloak.sh "$F" migrate --link </dev/null >&2
REPORT="$(ls "$DATA_ROOT/secrets"/keycloak-migrate-*.json 2>/dev/null | sort | tail -n1 || true)"
[ -n "$REPORT" ] && [ "$REPORT" != "$before" ] || { echo "  dry-run report not written" >&2; false; }
DECISION="$(python3 scripts/demo_link_guard.py "$REPORT")"
if [ "${DECISION%% *}" = apply ]; then
  scripts/keycloak.sh "$F" migrate --apply --link --plan-hash "${DECISION#apply }" --yes </dev/null >&2
fi

step "5 smoke test https://$(get APP_DOMAIN)"
python3 scripts/demo_smoke.py "${DEMO_SMOKE_URL:-https://$(get APP_DOMAIN)}" >&2

trap - ERR
say "DEMO DEPLOYED (recovery deferred) – https://$(get APP_DOMAIN)"
echo "  pre-deploy backup: ${BK:-none}; rollback snapshot: $SNAP" >&2
echo "  untouched: legacy aegisrmf containers + volumes, /root/ironvision-predeploy, $RDIR (recovery can still be rehearsed later)" >&2
