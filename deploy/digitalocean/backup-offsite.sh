#!/usr/bin/env bash
# Nightly backup on the Droplet: scripts/backup.sh -> local retention -> optional off-droplet copy (rclone, e.g. DO Spaces).
# Run by ironvision-backup.service. Needs on the host: postgresql-client-16, aws-cli (MinIO sync), rclone (optional).
# STATUS: not yet executed on DigitalOcean.
set -euo pipefail
REPO="${REPO:-/opt/ironvision/app}"
ENV_FILE="${ENV_FILE:-$REPO/deploy/digitalocean/.env.production}"
set -a; . "$ENV_FILE"; set +a
TS="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="${BACKUP_DIR:?}/ironvision-$TS"
export DATABASE_URL="postgresql://${POSTGRES_USER}:${POSTGRES_PASSWORD}@127.0.0.1:5432/${POSTGRES_DB}"
export STORAGE_DRIVER=s3 S3_BUCKET S3_ENDPOINT_URL="${S3_ENDPOINT_URL:-http://127.0.0.1:9000}"
export AWS_ACCESS_KEY_ID="${S3_ACCESS_KEY_ID:-$MINIO_ROOT_USER}" AWS_SECRET_ACCESS_KEY="${S3_SECRET_ACCESS_KEY:-$MINIO_ROOT_PASSWORD}" AWS_DEFAULT_REGION="${S3_REGION:-us-east-1}"
bash "$REPO/scripts/backup.sh" "$OUT"
chmod -R go-rwx "$OUT"
find "$BACKUP_DIR" -maxdepth 1 -name 'ironvision-*' -type d -mtime +"${BACKUP_RETENTION_DAYS:-14}" -exec rm -rf {} +
if [ -n "${RCLONE_REMOTE:-}" ]; then
  rclone copy "$OUT" "$RCLONE_REMOTE/ironvision-$TS" --checksum
  rclone check "$OUT" "$RCLONE_REMOTE/ironvision-$TS" --one-way
fi
echo "[backup-offsite] OK $OUT"
