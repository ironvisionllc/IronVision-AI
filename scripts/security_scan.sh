#!/usr/bin/env bash
# Dependency + static security scans. Reports -> docs/security/. Tools that are not installed are reported as SKIPPED.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; OUT="$ROOT/docs/security"; mkdir -p "$OUT"
run() { local name="$1"; shift; if command -v "$1" >/dev/null 2>&1; then echo "[scan] $name"; "$@" > "$OUT/$name.txt" 2>&1; echo "exit=$?" >> "$OUT/$name.txt"; else echo "SKIPPED: $1 not installed" > "$OUT/$name.txt"; echo "[scan] $name SKIPPED"; fi; }
run pip-audit pip-audit -r "$ROOT/backend/requirements.prod.txt" --progress-spinner off
run bandit bandit -r "$ROOT/backend/app" "$ROOT/backend/worker" -ll -f txt
(cd "$ROOT/frontend" && run yarn-audit yarn audit --groups dependencies --summary)
for img in aegisrmf-backend aegisrmf-frontend; do run "trivy-$img" trivy image --severity HIGH,CRITICAL "$img:latest"; done
echo "[scan] reports in $OUT"
