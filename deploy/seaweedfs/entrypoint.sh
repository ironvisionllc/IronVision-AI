#!/bin/sh
# SeaweedFS single-container S3 server for IronVision AI (replaces MinIO).
# Generates the S3 identities file from env (never written to the data volume), then execs `weed server`.
#   admin identity  (S3_ADMIN_ACCESS_KEY_ID / S3_ADMIN_SECRET_ACCESS_KEY): bucket bootstrap + backups only
#   app identity    (S3_ACCESS_KEY_ID / S3_SECRET_ACCESS_KEY): Read/Write/List/Tagging on S3_BUCKET only (least privilege)
set -eu
WEED_BIN="${WEED_BIN:-weed}"
DATA_DIR="${DATA_DIR:-/data}"
CONF="${S3_CONFIG_PATH:-/tmp/ironvision-s3.json}"
: "${S3_BUCKET:?S3_BUCKET required}"
ADMIN_KEY="${S3_ADMIN_ACCESS_KEY_ID:-${MINIO_ROOT_USER:-}}"
ADMIN_SECRET="${S3_ADMIN_SECRET_ACCESS_KEY:-${MINIO_ROOT_PASSWORD:-}}"
: "${ADMIN_KEY:?S3_ADMIN_ACCESS_KEY_ID required}" "${ADMIN_SECRET:?S3_ADMIN_SECRET_ACCESS_KEY required}"
: "${S3_ACCESS_KEY_ID:?S3_ACCESS_KEY_ID required}" "${S3_SECRET_ACCESS_KEY:?S3_SECRET_ACCESS_KEY required}"
for v in "$ADMIN_KEY" "$ADMIN_SECRET" "$S3_ACCESS_KEY_ID" "$S3_SECRET_ACCESS_KEY" "$S3_BUCKET"; do
  case "$v" in *[!A-Za-z0-9._+/=-]*) echo "[seaweedfs] refusing credential/bucket with characters outside [A-Za-z0-9._+/=-]" >&2; exit 2 ;; esac
done
[ "$ADMIN_KEY" = "$S3_ACCESS_KEY_ID" ] && { echo "[seaweedfs] admin and app access keys must differ" >&2; exit 2; }
umask 077
mkdir -p "$DATA_DIR" "$(dirname "$CONF")"
cat > "$CONF" <<EOF
{"identities": [
  {"name": "ironvision-admin", "credentials": [{"accessKey": "$ADMIN_KEY", "secretKey": "$ADMIN_SECRET"}],
   "actions": ["Admin", "Read", "List", "Tagging", "Write"]},
  {"name": "ironvision-app", "credentials": [{"accessKey": "$S3_ACCESS_KEY_ID", "secretKey": "$S3_SECRET_ACCESS_KEY"}],
   "actions": ["Read:$S3_BUCKET", "Write:$S3_BUCKET", "List:$S3_BUCKET", "Tagging:$S3_BUCKET"]}
]}
EOF
exec "$WEED_BIN" server -dir="$DATA_DIR" -ip=127.0.0.1 -ip.bind=0.0.0.0 \
  -master.volumeSizeLimitMB="${SEAWEEDFS_VOLUME_SIZE_LIMIT_MB:-1024}" -volume.max=0 \
  -s3 -s3.port=8333 -s3.config="$CONF" ${SEAWEEDFS_EXTRA_ARGS:-}
