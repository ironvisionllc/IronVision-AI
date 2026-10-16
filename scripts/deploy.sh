#!/usr/bin/env bash
# IronVision AI – the one supported deploy command (DigitalOcean Droplet or any Docker host).
#   scripts/deploy.sh [ENV_FILE] [--staging] [--project NAME] [--skip-edge-check] [--no-pull] [--no-cache] [--force-tls] [--install-systemd|--no-systemd] [--apply-realm] [--no-backup]
# ENV_FILE defaults to deploy/digitalocean/.env.production. Stops at the first failure with a non-zero exit;
# "DEPLOYMENT SUCCEEDED" is printed only after /api/v1/ready answered. Works as root or as a docker-group user.
set -Eeuo pipefail

ENV_FILE="deploy/digitalocean/.env.production"
PROJECT=""
STAGING=0
SKIP_EDGE=0
PULL=1
SYSTEMD=auto
BUILD_ARGS=()
APPLY_REALM=0
BACKUP=1
READY_TIMEOUT="${READY_TIMEOUT:-240}"
LEGACY_PROJECT="aegisrmf"

usage() { sed -n '2,5p' "$0"; }
while [ $# -gt 0 ]; do
  case "$1" in
    --staging) STAGING=1 ;;
    --project) PROJECT="${2:?--project needs a name}"; shift ;;
    --skip-edge-check) SKIP_EDGE=1 ;;
    --no-pull) PULL=0 ;;
    --no-cache) BUILD_ARGS+=(--no-cache) ;;
    --force-tls) export FORCE_TLS=1 ;;
    --install-systemd) SYSTEMD=yes ;;
    --no-systemd) SYSTEMD=no ;;
    --apply-realm) APPLY_REALM=1 ;;
    --no-backup) BACKUP=0 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
    *) ENV_FILE="$1" ;;
  esac
  shift
done

cd "$(dirname "${BASH_SOURCE[0]}")/.."
STEP="preflight"
HINT=""
STARTED=$(date +%s)

finish() {
  local rc=$?
  if [ "$rc" -ne 0 ]; then
    printf '\n#### DEPLOYMENT FAILED at step "%s" (exit %s). Later steps were NOT run.\n' "$STEP" "$rc" >&2
    if [ -n "$HINT" ]; then printf '#### %s\n' "$HINT" >&2; fi
  fi
}
trap finish EXIT

step() { STEP="$1"; HINT="${2:-}"; printf '\n==== [%s] %s\n' "$(date +%H:%M:%S)" "$1"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
warn() { printf 'WARN: %s\n' "$*" >&2; }
# env files are data: read single keys, never source them
# shellcheck source=scripts/lib/envfile.sh
. scripts/lib/envfile.sh
envget() { env_get "$ENV_FILE" "$1"; }
has_profile() { case ",$PROFILES," in *",$1,"*) return 0 ;; esac; return 1; }

# ---------------------------------------------------------------- preflight
step "preflight"
[ -f "$ENV_FILE" ] || die "env file not found: $ENV_FILE
  create it:  cp deploy/digitalocean/env.production.template $ENV_FILE && python3 scripts/gen_env_secrets.py $ENV_FILE"
case "$(stat -c %a "$ENV_FILE")" in 600|400) ;; *) warn "$ENV_FILE is readable by others – run: chmod 600 $ENV_FILE" ;; esac
if [ "$(id -u)" -eq 0 ]; then
  SUDO=()
  if id ironvision >/dev/null 2>&1; then OPERATOR=ironvision; else OPERATOR=root; fi
  warn "running as root – supported. Recommended: a dedicated 'ironvision' user in the docker group (guide §2)."
else
  SUDO=(sudo)
  OPERATOR="$(id -un)"
fi
OPGROUP="$(id -gn "$OPERATOR")"
command -v python3 >/dev/null || die "python3 is required on the host (apt-get install -y python3)"
command -v docker >/dev/null || die "docker is not installed (guide §2)"
docker info >/dev/null 2>&1 || die "cannot reach the Docker daemon – run as root or as a user in the docker group"
CV="$(docker compose version --short 2>/dev/null || true)"
[ -n "$CV" ] || die "the Docker Compose plugin is missing (apt-get install -y docker-compose-plugin)"
[ "$(printf '%s\n%s\n' 2.24.0 "${CV#v}" | sort -V | head -n 1)" = "2.24.0" ] || die "Docker Compose >= 2.24 is required (found $CV)"
echo "docker compose $CV, operator=$OPERATOR"
if [ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$LEGACY_PROJECT")$(docker ps -aq --filter "name=^$LEGACY_PROJECT-")" ]; then
  step "legacy containers ($LEGACY_PROJECT)" "read-only analysis: sudo ./recover.sh run"
  lrc=0; python3 scripts/legacy_project.py inspect "$LEGACY_PROJECT" --env-file "$ENV_FILE" || lrc=$?
  case "$lrc" in
    0) warn "legacy '$LEGACY_PROJECT' containers are RETAINED for recovery (no dependency, no port conflict) – continuing. Stop them after cutover with: sudo ./recover.sh finalize" ;;
    10) die "PORT_CONFLICT: a legacy container holds a port the ironvision stack needs (see !! lines). Resolve it (verified backup first, then stops only that container): sudo ./recover.sh resolve-conflict" ;;
    11) die "PRODUCTION_DEPENDS_ON_LEGACY: the live stack uses a legacy container (see !! lines) – do NOT stop it. Read-only analysis + plan: sudo ./recover.sh run" ;;
    *) die "legacy inspection failed (exit $lrc) – fail-safe stop. Details: scripts/legacy_project.sh inspect $LEGACY_PROJECT" ;;
  esac
fi

# ---------------------------------------------------------------- env validation
step "check_env" "fix every ERROR line above in $ENV_FILE, then re-run: scripts/deploy.sh $ENV_FILE"
python3 scripts/check_env.py "$ENV_FILE"

# ---------------------------------------------------------------- storage plan + compose command
step "storage plan" "fix the storage settings in $ENV_FILE (guide §0 / §12.2)"
DRIVER="$(envget STORAGE_DRIVER)"
ENDPOINT="$(envget S3_ENDPOINT_URL)"
PROFILES="$(envget COMPOSE_PROFILES | tr -d '[:space:]')"
DATA_ROOT="$(envget DATA_ROOT)"
APP_DOMAIN="$(envget APP_DOMAIN)"
[ -n "$DATA_ROOT" ] || die "DATA_ROOT must be set in $ENV_FILE (e.g. /srv/ironvision)"
FILES=(-f docker-compose.yml)
if [ "$STAGING" -eq 1 ]; then
  FILES+=(-f deploy/digitalocean/docker-compose.do.yml -f deploy/digitalocean/docker-compose.staging.yml)
  PROJECT="${PROJECT:-ironvision-staging}"
else
  FILES+=(-f docker-compose.prod.yml -f deploy/digitalocean/docker-compose.do.yml)
  PROJECT="${PROJECT:-ironvision}"
fi
BUILTIN=0
case "$DRIVER" in
  local)
    has_profile seaweedfs && die "STORAGE_DRIVER=local does not use the object store – remove seaweedfs from COMPOSE_PROFILES in $ENV_FILE"
    MODE="local disk ($DATA_ROOT/objects)" ;;
  s3)
    FILES+=(-f deploy/compose/storage-s3.yml)
    if [ -z "$ENDPOINT" ]; then
      has_profile seaweedfs || die "COMPOSE_PROFILES=seaweedfs is required when using the built-in object store (STORAGE_DRIVER=s3 with S3_ENDPOINT_URL empty).
  Add COMPOSE_PROFILES=seaweedfs to $ENV_FILE, or set S3_ENDPOINT_URL for external S3, or use STORAGE_DRIVER=local."
      BUILTIN=1
      FILES+=(-f deploy/compose/storage-seaweedfs.yml)
      MODE="built-in SeaweedFS ($DATA_ROOT/objectstore)"
    else
      has_profile seaweedfs && die "S3_ENDPOINT_URL points to external S3 ($ENDPOINT) – remove seaweedfs from COMPOSE_PROFILES in $ENV_FILE"
      MODE="external S3 ($ENDPOINT)"
    fi ;;
  *) die "STORAGE_DRIVER must be s3 or local in $ENV_FILE (got '$DRIVER')" ;;
esac
AUTH_DOMAIN="$(envget AUTH_DOMAIN)"
KEYCLOAK=0
if [ -n "$AUTH_DOMAIN" ]; then KEYCLOAK=1; FILES+=(-f deploy/compose/keycloak.yml); fi
export COMPOSE_PROFILES="$PROFILES"
DC=(docker compose -p "$PROJECT" --env-file "$ENV_FILE" "${FILES[@]}")
echo "project=$PROJECT  storage=$MODE  profiles=${PROFILES:-none}  keycloak=$([ "$KEYCLOAK" -eq 1 ] && echo "https://$AUTH_DOMAIN" || echo off)"
echo "compose: ${DC[*]}"

# ---------------------------------------------------------------- directories (root or ironvision operator)
step "data directories" "could not prepare $DATA_ROOT – run as root or a sudo-capable user"
mk() { "${SUDO[@]}" install -d -m "$1" -o "$2" -g "$3" "$4"; printf '  %-40s %s:%s %s\n' "$4" "$2" "$3" "$1"; }
"${SUDO[@]}" mkdir -p "$DATA_ROOT"
mk 700 70 70 "$DATA_ROOT/postgres"                      # postgres:16-alpine uid/gid 70
if [ "$BUILTIN" -eq 1 ]; then mk 750 0 0 "$DATA_ROOT/objectstore"; fi
mk 750 10001 10001 "$DATA_ROOT/objects"                 # backend/worker uid 10001 (STORAGE_DRIVER=local)
mk 755 0 0 "$DATA_ROOT/letsencrypt"
mk 755 0 0 "$DATA_ROOT/certbot"
mk 755 0 0 "$DATA_ROOT/certbot/www"
mk 750 "$OPERATOR" "$OPGROUP" "$DATA_ROOT/backups"
if [ "$KEYCLOAK" -eq 1 ]; then
  mk 700 10001 10001 "$DATA_ROOT/secrets"               # one-time credential files (keycloak-migrate / keycloak-user rotate)
  mk 755 0 0 "$DATA_ROOT/edge"
  # Keycloak admin console allowlist for the public auth domain (default: nobody → SSH tunnel only)
  ALLOW_FILE="$(mktemp)"
  for c in $(envget KEYCLOAK_ADMIN_ALLOWED_CIDRS | tr ',' ' '); do printf 'allow %s;\n' "$c" >> "$ALLOW_FILE"; done
  printf 'deny all;\n' >> "$ALLOW_FILE"
  "${SUDO[@]}" install -m 644 "$ALLOW_FILE" "$DATA_ROOT/edge/auth-admin-allow.conf"; rm -f "$ALLOW_FILE"
  echo "  keycloak admin allowlist: $(grep -c '^allow' "$DATA_ROOT/edge/auth-admin-allow.conf") CIDR(s), everything else denied"
fi
# the resolved compose set, read by the systemd units (boot start, renewals, backups)
CF=""
for x in "${FILES[@]}"; do [ "$x" = -f ] || CF="${CF:+$CF:}$x"; done
printf 'COMPOSE_PROJECT_NAME=%s\nCOMPOSE_FILE=%s\nCOMPOSE_PROFILES=%s\n' "$PROJECT" "$CF" "$PROFILES" | "${SUDO[@]}" tee "$DATA_ROOT/compose.env" >/dev/null

# ---------------------------------------------------------------- compose validation
step "compose config" "the message above names the missing or invalid variable – set it in $ENV_FILE"
"${DC[@]}" config -q
SERVICES="$("${DC[@]}" config --services)"
if [ "$BUILTIN" -eq 1 ] && ! grep -qx seaweedfs <<<"$SERVICES"; then
  die "seaweedfs is not in the service set although the built-in object store is configured – COMPOSE_PROFILES=seaweedfs is required"
fi
echo "services: $(tr '\n' ' ' <<<"$SERVICES")"

# ---------------------------------------------------------------- images
if [ "$PULL" -eq 1 ]; then
  step "pull images" "registry pull failed – check network/DNS and the image tags in $ENV_FILE (SEAWEEDFS_IMAGE)"
  "${DC[@]}" pull --ignore-buildable
fi
step "build images" "image build failed – see the build output above"
"${DC[@]}" build "${BUILD_ARGS[@]}"
step "image self-check (imports every module, before anything starts)" "an import failed – a package is missing from backend/requirements.prod.txt; run: python3 scripts/check_requirements.py"
"${DC[@]}" run --rm --no-deps -T backend python -m app.tools.selfcheck
"${DC[@]}" run --rm --no-deps -T worker python -m app.tools.selfcheck

# ---------------------------------------------------------------- backup of the running deployment (before anything changes)
if [ "$BACKUP" -eq 1 ] && [ -n "$("${DC[@]}" ps -q postgres 2>/dev/null)" ]; then
  step "backup (existing deployment: app DB$([ "$KEYCLOAK" -eq 1 ] && echo ' + keycloak DB') + objects)" "backup failed – nothing was changed. Fix it or re-run with --no-backup (not recommended)"
  REPO="$PWD" ENV_FILE="$ENV_FILE" COMPOSE_PROJECT="$PROJECT" bash deploy/digitalocean/backup-offsite.sh
fi

# ---------------------------------------------------------------- ordered start
step "start postgres" "logs: ${DC[*]} logs --tail 100 postgres"
"${DC[@]}" up -d --wait --wait-timeout 180 postgres
if [ "$KEYCLOAK" -eq 1 ]; then
  step "keycloak-db-init (role + database if missing; never drops)" "see the [keycloak-db-init] line above"
  "${DC[@]}" run --rm --no-deps keycloak-db-init
  step "start keycloak (https://$AUTH_DOMAIN)" "logs: ${DC[*]} logs --tail 200 keycloak"
  "${DC[@]}" up --no-deps -d --wait --wait-timeout 300 keycloak
  step "keycloak realm $(envget KEYCLOAK_REALM) – plan$([ "$APPLY_REALM" -eq 1 ] && echo ' + apply' || echo ' (applied automatically only if the realm is absent)')" \
       "read the [keycloak-config] lines above; admin access: docs/KEYCLOAK.md"
  if [ "$APPLY_REALM" -eq 1 ]; then KC_ARGS=(apply --yes); else KC_ARGS=(apply --if-realm-absent --yes); fi
  "${DC[@]}" run --rm --no-deps -T keycloak-config python -m app.tools.keycloak_config "${KC_ARGS[@]}"
fi
if [ "$BUILTIN" -eq 1 ]; then
  step "start object store (seaweedfs)" "logs: ${DC[*]} logs --tail 100 seaweedfs"
  "${DC[@]}" up -d --wait --wait-timeout 180 seaweedfs
fi
step "objectstore-init" "read the '[s3-bootstrap] FAIL' line above – it names the setting to fix"
"${DC[@]}" run --rm --no-deps objectstore-init
step "migrate (alembic upgrade head + reference content)" "see the migration output above; database logs: ${DC[*]} logs postgres"
"${DC[@]}" run --rm --no-deps migrate
mapfile -t APP < <(grep -vxE 'postgres|seaweedfs|objectstore-init|migrate|certbot|keycloak|keycloak-db-init|keycloak-config' <<<"$SERVICES")
if grep -qx edge <<<"$SERVICES" && [ "$SKIP_EDGE" -eq 0 ]; then
  step "TLS certificate for $APP_DOMAIN${AUTH_DOMAIN:+ + $AUTH_DOMAIN}" "fix the TLS message above (DNS A record, port 80, LETSENCRYPT_EMAIL) – guide §4"
  scripts/ensure_tls.sh ensure "$ENV_FILE" -- "${DC[@]}"
fi
step "start application (${APP[*]})" "logs: ${DC[*]} logs --tail 200 ${APP[*]}"
"${DC[@]}" up -d --no-deps "${APP[@]}"

# ---------------------------------------------------------------- readiness
step "wait for /api/v1/ready (max ${READY_TIMEOUT}s)" "backend not ready – logs: ${DC[*]} logs --tail 200 backend"
deadline=$(( $(date +%s) + READY_TIMEOUT ))
until "${DC[@]}" exec -T backend python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8001/api/v1/ready', timeout=5)" >/dev/null 2>&1; do
  [ "$(date +%s)" -lt "$deadline" ] || die "backend did not report ready within ${READY_TIMEOUT}s"
  sleep 3
done
echo "backend: ready"
RUNNING="$("${DC[@]}" ps --status running --services)"
for s in "${APP[@]}"; do
  if [ "$s" = edge ] && [ "$SKIP_EDGE" -eq 1 ]; then continue; fi
  grep -qx "$s" <<<"$RUNNING" || die "service '$s' is not running – logs: ${DC[*]} logs --tail 200 $s"
done
if grep -qx edge <<<"$SERVICES" && [ "$SKIP_EDGE" -eq 0 ]; then
  step "public check https://$APP_DOMAIN${AUTH_DOMAIN:+ + https://$AUTH_DOMAIN} (certificates, /api/v1/ready, OIDC discovery, /admin blocked)" "public endpoint failed – check DNS for $APP_DOMAIN, the DO firewall (80/443) and: ${DC[*]} logs edge"
  scripts/ensure_tls.sh verify "$ENV_FILE"
fi

# ---------------------------------------------------------------- systemd (start on boot, certificate renewal, backups)
install_systemd() {
  local dir="${SYSTEMD_DIR:-/etc/systemd/system}" u
  command -v systemctl >/dev/null || { warn "systemctl not found – skipping systemd units"; return 0; }
  for u in deploy/digitalocean/systemd/*.service deploy/digitalocean/systemd/*.timer; do
    sed -e "s|/opt/ironvision/app|$PWD|g" -e "s|^User=ironvision\$|User=$OPERATOR|" -e "s|/srv/ironvision/compose.env|$DATA_ROOT/compose.env|g" \
        -e "s|deploy/digitalocean/.env.production|$ENV_FILE|g" "$u" > "$dir/$(basename "$u")"
    echo "  installed $dir/$(basename "$u")"
  done
  systemctl daemon-reload
  systemctl enable ironvision.service
  systemctl enable --now ironvision-certbot-renew.timer ironvision-backup.timer
}
if [ "$SYSTEMD" = yes ] || { [ "$SYSTEMD" = auto ] && [ "$(id -u)" -eq 0 ] && [ "$STAGING" -eq 0 ]; }; then
  step "systemd units (start on boot, twice-daily certificate renewal + edge reload, nightly backup)" "systemd install failed – re-run with --no-systemd to skip"
  install_systemd
fi

# ---------------------------------------------------------------- summary
STEP="summary"
"${DC[@]}" ps
printf '\n#### DEPLOYMENT SUCCEEDED in %ss\n' "$(( $(date +%s) - STARTED ))"
printf '  project   %s\n  env file  %s\n  storage   %s\n  profiles  %s\n  url       https://%s\n' \
  "$PROJECT" "$ENV_FILE" "$MODE" "${PROFILES:-none}" "$APP_DOMAIN"
if [ "$KEYCLOAK" -eq 1 ]; then
  printf '  keycloak  https://%s/realms/%s  (admin console: SSH tunnel, docs/KEYCLOAK.md)\n' "$AUTH_DOMAIN" "$(envget KEYCLOAK_REALM)"
  printf '  migrate   users are NOT migrated by deploy – dry run: scripts/keycloak.sh %s migrate\n' "$ENV_FILE"
  if [ "$(envget ALLOW_DEMO_LOGIN)" = true ] && { [ -z "$(envget KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET)" ] || [ -z "$(envget KEYCLOAK_DEMO_USERNAME)" ] || [ -z "$(envget KEYCLOAK_DEMO_PASSWORD)" ]; }; then
    warn "ALLOW_DEMO_LOGIN=true but KEYCLOAK_DEMO_* launcher values are empty – 'Explore the demo' cannot work (re-run ./deploy.sh to generate them)"
  fi
  printf '\n'
  "${DC[@]}" --profile keycloak-tools run --rm --no-deps -T -e DOCTOR_ENV_FILE="$ENV_FILE" keycloak-config python -m app.tools.keycloak_doctor \
    || warn "Explore-the-demo / registration is NOT fully working – fix the FAIL lines above (re-check: scripts/keycloak.sh $ENV_FILE doctor)"
fi
printf '  manage    %s ps | logs -f backend | stop\n' "${DC[*]}"
printf '\nReady: https://%s  (API: https://%s/api/v1/ready)\n' "$(envget APP_DOMAIN)" "$(envget APP_DOMAIN)"
