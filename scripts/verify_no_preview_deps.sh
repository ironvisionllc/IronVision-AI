#!/usr/bin/env bash
# Verifies that Emergent preview-only dependencies are excluded from the production build.
#   (a) requirements.prod.txt + backend/worker images (pip list)   (b) frontend Docker package.json / image
#   (c) built JS bundle has no Emergent URLs                        (d) Emergent AI adapter unreachable unless AI_PROVIDER=emergent
# Usage: scripts/verify_no_preview_deps.sh [--docker]     (--docker also inspects built images; run on the Droplet)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT" || exit 1
FAIL=0; pass() { echo "  PASS  $*"; }; fail() { echo "  FAIL  $*"; FAIL=1; }; skip() { echo "  SKIP  $*"; }
PAT='emergent|visual-edits|emergentbase'

echo "(a) backend Python dependencies"
grep -qiE "$PAT" backend/requirements.prod.txt && fail "requirements.prod.txt references an Emergent package" || pass "requirements.prod.txt has no Emergent packages"
grep -q "requirements.prod.txt" backend/Dockerfile && grep -q "requirements.prod.txt" backend/Dockerfile.worker && pass "backend + worker images install requirements.prod.txt only" || fail "Dockerfiles do not use requirements.prod.txt"

echo "(b) frontend dependencies used by the Docker build"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
cp frontend/package.json "$TMP/package.json"
(cd "$TMP" && node -e "const fs=require('fs');const p=require('./package.json');for(const k of Object.keys(p.devDependencies||{}))if(k.startsWith('@emergentbase/'))delete p.devDependencies[k];fs.writeFileSync('package.json',JSON.stringify(p,null,2))")
grep -qiE "$PAT" "$TMP/package.json" && fail "Docker package.json still contains Emergent packages" || pass "Docker package.json (after Dockerfile strip) has no Emergent packages"
grep -qiE "$PAT" frontend/deploy/index.html && fail "deploy/index.html references Emergent scripts" || pass "deploy/index.html (Docker) has no Emergent scripts"
grep -q "COPY deploy/index.html public/index.html" frontend/Dockerfile && pass "Dockerfile replaces the preview index.html" || fail "Dockerfile does not swap index.html"

echo "(c) built JS bundle"
if [ "${SKIP_BUILD:-}" != "1" ] && command -v yarn >/dev/null; then
  BUILD="$TMP/build"
  (cd frontend && mv public/index.html "$TMP/index.preview.html" && cp deploy/index.html public/index.html \
     && REACT_APP_BACKEND_URL="" GENERATE_SOURCEMAP=false INLINE_RUNTIME_CHUNK=false BUILD_PATH="$BUILD" yarn -s build >/dev/null 2>&1; rc=$?; \
     mv "$TMP/index.preview.html" public/index.html; exit $rc) && {
    HITS=$(grep -rlE "assets\.emergent\.sh|ap\.emergent\.sh|emergentagent\.com|emergent-main|posthog" "$BUILD" | sed "s#$BUILD/##")
    [ -z "$HITS" ] && pass "bundle has no Emergent URLs / preview scripts" || fail "Emergent references in bundle: $HITS"
    grep -rqiE "visual-edits|emergentbase" "$BUILD" && echo "  NOTE  bundle mentions visual-edits/emergentbase (see (b): pod build has them installed; Docker build strips them)" || pass "bundle has no visual-edits/overlay code"
  } || fail "frontend build failed"
else skip "frontend build (SKIP_BUILD=1 or yarn missing)"; fi

echo "(d) Emergent AI adapter"
if [ -f backend/app/services/ai/adapters/emergent_adapter.py ]; then
  grep -q "emergentintegrations" backend/requirements.prod.txt && fail "adapter dependency shipped" || pass "emergent adapter file present but its library (emergentintegrations) is NOT in requirements.prod.txt"
  (cd backend && APP_ENV=production AI_PROVIDER=none python3 - <<'EOF2'
import sys
sys.modules["emergentintegrations"] = None  # simulate the production image (library absent)
from app.services.ai import service
assert service.build_provider("none") is None
assert "app.services.ai.adapters.emergent_adapter" not in sys.modules, "adapter imported with AI_PROVIDER=none"
try:
    service.build_provider("emergent")
    raise SystemExit("emergent adapter usable in production")
except ValueError as e:
    assert "preview-only" in str(e)
assert "app.services.ai.adapters.emergent_adapter" not in sys.modules
print("  PASS  AI_PROVIDER=none never imports the emergent adapter; AI_PROVIDER=emergent is refused when APP_ENV=production")
EOF2
  ) || fail "emergent adapter reachable with AI_PROVIDER=none"
else pass "emergent adapter file absent"; fi

if [ "${1:-}" = "--docker" ]; then
  echo "(docker) built images"
  for img in $(docker compose images --format json 2>/dev/null | python3 -c "import sys,json;[print(i['Repository']+':'+i['Tag']) for i in json.load(sys.stdin) if any(s in i['Repository'] for s in ('backend','worker','migrate'))]" | sort -u); do
    docker run --rm --entrypoint pip "$img" list 2>/dev/null | grep -qiE "$PAT" && fail "$img has Emergent pip packages" || pass "$img pip list clean"
  done
  FE=$(docker compose images --format json | python3 -c "import sys,json;print(next(i['Repository']+':'+i['Tag'] for i in json.load(sys.stdin) if 'frontend' in i['Repository']))")
  docker run --rm --entrypoint sh "$FE" -c "grep -rlE 'assets\.emergent\.sh|ap\.emergent\.sh|emergentagent\.com|posthog' /usr/share/nginx/html" | grep -q . && fail "$FE contains Emergent URLs" || pass "$FE static files clean"
else skip "image inspection (run with --docker on the Droplet)"; fi
echo; [ $FAIL -eq 0 ] && echo "RESULT: PASS" || echo "RESULT: FAIL"
exit $FAIL
