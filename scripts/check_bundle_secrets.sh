#!/usr/bin/env bash
# Fails if the demo password (or any DEMO/STAGING password env value) appears in frontend source or a built bundle.
set -euo pipefail
cd "$(dirname "$0")/.."
vals=()
for k in DEMO_PASSWORD STAGING_DEMO_PASSWORD DEMO_USER_PASSWORD; do
  v="${!k:-$(grep -h "^$k=" backend/.env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '"' || true)}"
  [ -n "$v" ] && vals+=("$v")
done
[ ${#vals[@]} -eq 0 ] && { echo "bundle secret check: no demo passwords configured – nothing to check"; exit 0; }
targets=(frontend/src frontend/public)
[ -d frontend/build ] && targets+=(frontend/build)
for v in "${vals[@]}"; do
  if grep -rlF -- "$v" "${targets[@]}" 2>/dev/null | grep -v node_modules; then
    echo "bundle secret check: FAIL – a demo password appears in the files above"; exit 1
  fi
done
echo "bundle secret check: OK (${#vals[@]} value(s), ${targets[*]})"
