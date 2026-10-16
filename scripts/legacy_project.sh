#!/usr/bin/env bash
# Legacy compose project (default aegisrmf): inspect | backup | stop | preserve-and-stop. See scripts/legacy_project.py.
# Never runs docker rm / down / -v; volumes are never touched.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 scripts/legacy_project.py "$@"
