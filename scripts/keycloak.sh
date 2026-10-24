#!/usr/bin/env bash
# Keycloak operator commands on the Droplet (run from the repo root; never sources the env file):
#   scripts/keycloak.sh [ENV_FILE] plan|apply                       realm/admin configurator (shows the plan first)
#   scripts/keycloak.sh [ENV_FILE] migrate [keycloak-migrate args]  user migration – DRY RUN unless --apply
#   scripts/keycloak.sh [ENV_FILE] user list|set-password|rotate|disable|enable|reset-mfa [EMAIL] [--temporary]
#   scripts/keycloak.sh [ENV_FILE] identity-list
#   scripts/keycloak.sh [ENV_FILE] rotate-demo                     new demo launcher password: Keycloak + env file (backup) + backend restart
#   scripts/keycloak.sh [ENV_FILE] doctor                          Explore-the-demo / registration diagnosis with exact fix commands
# migrate --apply first runs the full backup (app DB + keycloak DB + objects) and refuses to continue if it fails.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
F="deploy/digitalocean/.env.production"
if [ $# -gt 0 ] && [ -f "$1" ]; then F="$1"; shift; fi
CMD="${1:?usage: scripts/keycloak.sh [ENV_FILE] plan|apply|migrate|user|identity-list [args]}"
shift
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
get() { python3 scripts/envget.py "$F" "$1"; }
DATA_ROOT="$(get DATA_ROOT)"
[ -n "$(get AUTH_DOMAIN)" ] || die "AUTH_DOMAIN is not set in $F – run ./deploy.sh --set-auth-domain auth.<your-domain> first"
[ -f "$DATA_ROOT/compose.env" ] || die "$DATA_ROOT/compose.env missing – run ./deploy.sh once first"
DC=(docker compose --profile seaweedfs --env-file "$F")
CF="$(python3 scripts/envget.py "$DATA_ROOT/compose.env" COMPOSE_FILE)"
IFS=: read -r -a CFS <<<"$CF"
for f in "${CFS[@]}"; do DC+=(-f "$f"); done
DC+=(-p "$(python3 scripts/envget.py "$DATA_ROOT/compose.env" COMPOSE_PROJECT_NAME)")
RUN=("${DC[@]}" --profile keycloak-tools run --rm keycloak-config)

case "$CMD" in
  plan|apply)
    if [ "$CMD" = apply ]; then exec "${RUN[@]}" python -m app.tools.keycloak_config apply "$@"; fi
    exec "${RUN[@]}" python -m app.tools.keycloak_config plan ;;
  migrate)
    EXTRA=(--report "/secrets/keycloak-migrate-$(date -u +%Y%m%dT%H%M%SZ).json")
    if printf '%s\n' "$@" | grep -qx -- --apply; then
      BACKUP_DIR="$(get BACKUP_DIR)"
      [ "${BACKUP_DIR:-$DATA_ROOT/backups}" = "$DATA_ROOT/backups" ] || die "BACKUP_DIR must be $DATA_ROOT/backups for keycloak-migrate (mounted into the tool container)"
      echo "==== backup before migration (refuses to continue on failure)"
      REPO="$PWD" ENV_FILE="$F" bash deploy/digitalocean/backup-offsite.sh || die "backup failed – migration NOT started"
      LATEST="$(find "$DATA_ROOT/backups" -maxdepth 1 -name 'ironvision-*' -type d | sort | tail -n 1)"
      [ -f "$LATEST/manifest.json" ] || die "backup manifest missing in $LATEST – migration NOT started"
      EXTRA+=(--backup-ref "$LATEST")
    fi
    exec "${RUN[@]}" python -m app.cli keycloak-migrate "${EXTRA[@]}" "$@" ;;
  user) exec "${RUN[@]}" python -m app.cli keycloak-user "$@" ;;
  identity-list) exec "${RUN[@]}" python -m app.cli identity-list ;;
  clients) exec "${RUN[@]}" python -m app.tools.keycloak_config clients ;;
  doctor) exec "${DC[@]}" --profile keycloak-tools run --rm -T -e DOCTOR_ENV_FILE="$F" keycloak-config python -m app.tools.keycloak_doctor ;;
  rotate-demo)
    NEW="$(python3 -c 'import secrets; print(secrets.token_urlsafe(24))')"
    printf '%s\n' "$NEW" | "${DC[@]}" --profile keycloak-tools run --rm -T keycloak-config python -m app.cli keycloak-user set-password demo@ironvision.ai \
      || die "Keycloak password update failed – env file NOT changed"
    printf '%s' "$NEW" | python3 scripts/envset.py "$F" KEYCLOAK_DEMO_PASSWORD
    "${DC[@]}" up -d --no-deps backend   # recreate with the new value
    echo "demo launcher password rotated (value only in $F)" ;;
  *) die "unknown command $CMD" ;;
esac
