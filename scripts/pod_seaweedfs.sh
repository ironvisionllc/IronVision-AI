#!/usr/bin/env bash
# EMERGENT PREVIEW POD ONLY: SeaweedFS 4.48 (S3 on 127.0.0.1:18333) for the recovery tests – it also stands in for the
# legacy MinIO S3 API. Keys: recapp (scoped to evidence-live), recadmin (admin), legacyminio (admin, "legacy MinIO" role).
set -euo pipefail
D=${RECWEED_DIR:-/tmp/recweed}
mkdir -p "$D/data"
cat > "$D/s3.json" <<'EOF'
{"identities": [
 {"name": "recapp", "credentials": [{"accessKey": "recapp", "secretKey": "rec-app-secret-0123456789abcdef"}],
  "actions": ["Read:evidence-live", "Write:evidence-live", "List:evidence-live", "Tagging:evidence-live"]},
 {"name": "recadmin", "credentials": [{"accessKey": "recadmin", "secretKey": "rec-admin-secret-0123456789abcdef"}], "actions": ["Admin", "Read", "Write", "List", "Tagging"]},
 {"name": "legacyminio", "credentials": [{"accessKey": "legacyminio", "secretKey": "legacy-minio-secret-0123456789"}], "actions": ["Admin", "Read", "Write", "List", "Tagging"]}]}
EOF
pkill -f "weed server -dir=$D/data" || true
while pgrep -f "weed server -dir=$D/data" >/dev/null; do sleep 1; done
setsid nohup /root/tools/weed server -dir="$D/data" -ip=127.0.0.1 -master.port=19333 -volume.port=18080 -filer -filer.port=18888 \
  -s3 -s3.port=18333 -s3.config="$D/s3.json" -volume.max=0 -master.volumeSizeLimitMB=64 > "$D/weed.log" 2>&1 < /dev/null &
for _ in $(seq 1 60); do curl -sf -o /dev/null http://127.0.0.1:18333/healthz && exit 0; sleep 1; done
tail -5 "$D/weed.log"; exit 1
