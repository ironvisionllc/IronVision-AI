#!/usr/bin/env bash
# Nightly backup on the Droplet: scripts/backup.sh -> local retention -> optional off-droplet copy to any S3 (DO Spaces / AWS S3).
# Run by ironvision-backup.service. Host needs: postgresql-client-16, docker. Object copies use our objsync helper inside the
# backend image (no mc, aws-cli or rclone). STATUS: not yet executed on DigitalOcean.
set -euo pipefail
REPO="${REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"   # repo root = wherever this checkout lives
ENV_FILE="${ENV_FILE:-$REPO/deploy/digitalocean/.env.production}"
# env files are data – read the keys we need, never source the file
# shellcheck source=scripts/lib/envfile.sh
. "$REPO/scripts/lib/envfile.sh"
env_export "$ENV_FILE" BACKUP_DIR BACKUP_RETENTION_DAYS POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB STORAGE_DRIVER DATA_ROOT \
  KEYCLOAK_DB_NAME KEYCLOAK_DB_USER KEYCLOAK_DB_PASSWORD AUTH_DOMAIN \
  OFFSITE_S3_ENDPOINT_URL OFFSITE_S3_BUCKET OFFSITE_S3_REGION OFFSITE_S3_ACCESS_KEY_ID OFFSITE_S3_SECRET_ACCESS_KEY OFFSITE_S3_ADDRESSING_STYLE
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${BACKUP_DIR:?}/ironvision-$TS"
mkdir -p "$OUT"
DC=(docker compose -p "${COMPOSE_PROJECT:-ironvision}" --project-directory "$REPO" --env-file "$ENV_FILE")
CF="$(env_get "${DATA_ROOT:?}/compose.env" COMPOSE_FILE 2>/dev/null || true)"   # written by scripts/deploy.sh (storage/keycloak overlays)
CF="${CF:-docker-compose.yml:docker-compose.prod.yml:deploy/digitalocean/docker-compose.do.yml}"
IFS=: read -r -a CFS <<<"$CF"
for f in "${CFS[@]}"; do DC+=(-f "$REPO/$f"); done
export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${POSTGRES_DB}"
if [ -n "${AUTH_DOMAIN:-}" ] && [ -n "${KEYCLOAK_DB_PASSWORD:-}" ]; then   # Keycloak realm/users/credentials DB, dumped next to the app DB
  export KEYCLOAK_DB_URL="postgresql://${KEYCLOAK_DB_USER:-keycloak}:${KEYCLOAK_DB_PASSWORD}@127.0.0.1:5432/${KEYCLOAK_DB_NAME:-keycloak}"
fi
if [ "${STORAGE_DRIVER:-s3}" = "local" ]; then
  export STORAGE_LOCAL_ROOT="${DATA_ROOT:?}/objects"
else
  export STORAGE_DRIVER=s3
  # objsync runs in the backend image on the compose network (reaches http://seaweedfs:8333); the backup dir is bind-mounted
  export OBJSYNC="${DC[*]} run --rm -T --no-deps -v $BACKUP_DIR:$BACKUP_DIR backend python -m app.tools.objsync"
fi
bash "$REPO/scripts/backup.sh" "$OUT"
chmod -R go-rwx "$OUT"
find "$BACKUP_DIR" -maxdepth 1 -name 'ironvision-*' -type d -mtime +"${BACKUP_RETENTION_DAYS:-14}" -exec rm -rf {} +
if [ -n "${OFFSITE_S3_BUCKET:-}" ]; then
  # copy + SHA-256 re-verification of every file at the destination (OFFSITE_S3_* variables)
  "${DC[@]}" run --rm -T --no-deps -v "$BACKUP_DIR:$BACKUP_DIR" \
    -e OFFSITE_S3_ENDPOINT_URL -e OFFSITE_S3_BUCKET -e OFFSITE_S3_REGION -e OFFSITE_S3_ACCESS_KEY_ID \
    -e OFFSITE_S3_SECRET_ACCESS_KEY -e OFFSITE_S3_ADDRESSING_STYLE \
    backend python -m app.tools.objsync copy "dir:$OUT" "s3:OFFSITE@ironvision-$TS/"
fi
echo "[backup-offsite] OK $OUT"
