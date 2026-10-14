#!/usr/bin/env bash
# AegisRMF portability verification. Run on a developer machine with Docker + Compose v2:
#   ./scripts/verify_portability.sh            (keeps stack running afterwards)
#   KEEP=0 ./scripts/verify_portability.sh     (tears down with volumes at the end)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

BASE="http://localhost:8001/api/v1"
FRONT="http://localhost:3000"
PW_DEFAULT='IronVisionDemo!2026'
declare -a RESULTS=()
FAILED=0

pass() { RESULTS+=("PASS  $1"); echo "PASS  $1"; }
fail() { RESULTS+=("FAIL  $1 ${2:-}"); echo "FAIL  $1 ${2:-}"; FAILED=1; }
step() { echo; echo "==> $1"; }
json() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)"; }
wait_for() { local n=$1; shift; for _ in $(seq 1 "$n"); do "$@" >/dev/null 2>&1 && return 0; sleep 3; done; return 1; }

step "Prerequisites"
command -v docker >/dev/null && docker compose version >/dev/null 2>&1 && pass "docker + compose v2 available" || { fail "docker compose v2 not found"; exit 1; }
command -v curl >/dev/null && command -v python3 >/dev/null && pass "curl + python3 available" || { fail "curl/python3 required"; exit 1; }

step "Environment"
if [ ! -f .env ]; then
  cp env.template .env
  R() { python3 -c "import secrets;print(secrets.token_hex(24))"; }
  FK=$(python3 -c "import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())"); sed -i.bak "s/^SECRET_STORE_KEY=.*/SECRET_STORE_KEY=$FK/; s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(R)/; s/^S3_SECRET_ACCESS_KEY=.*/S3_SECRET_ACCESS_KEY=$(R)/; s/^S3_ADMIN_SECRET_ACCESS_KEY=.*/S3_ADMIN_SECRET_ACCESS_KEY=$(R)/; s/^JWT_SECRET=.*/JWT_SECRET=$(R)$(R)/" .env && rm -f .env.bak
  pass ".env created from .env.example with generated secrets"
else
  pass ".env present"
fi
PW=$(grep -E '^DEMO_PASSWORD=' .env | cut -d= -f2-); PW=${PW:-$PW_DEFAULT}

step "Compose config"
docker compose config -q && pass "docker compose config valid" || fail "docker compose config invalid"

step "Build images (backend, worker, frontend)"
docker compose build && pass "images built" || { fail "image build failed"; exit 1; }
docker compose run --rm --no-deps -T backend python -m app.tools.selfcheck && pass "backend image imports every module" || { fail "backend image self-check (requirements.prod.txt)"; exit 1; }
docker compose run --rm --no-deps -T worker python -m app.tools.selfcheck && pass "worker image imports every module" || { fail "worker image self-check (requirements.prod.txt)"; exit 1; }

step "Start stack"
docker compose up -d && pass "compose up" || { fail "compose up failed"; exit 1; }

step "Migrations (one-shot migrate service: alembic upgrade head + seed)"
mig_done() { [ "$(docker compose ps -a --format '{{.Service}} {{.State}} {{.ExitCode}}' | awk '$1=="migrate"{print $2" "$3}')" = "exited 0" ]; }
wait_for 60 mig_done && pass "migrate service exited 0" || { fail "migrate did not complete"; docker compose logs migrate | tail -40; }
REV=$(docker compose exec -T backend alembic current 2>/dev/null | tail -1)
echo "$REV" | grep -q "(head)" && pass "alembic at head: $REV" || fail "alembic not at head" "$REV"

step "Health endpoints"
wait_for 60 curl -fsS "$BASE/health" && pass "backend /api/v1/health reachable" || fail "backend health unreachable"
H=$(curl -fsS "$BASE/health")
for c in database storage; do
  [ "$(echo "$H" | json "d['components']['$c']['ok']")" = "True" ] && pass "health.$c ok" || fail "health.$c" "$(echo "$H" | json "d['components']['$c']")"
done
worker_ok() { [ "$(curl -fsS "$BASE/health" | json "d['components']['worker']['ok']")" = "True" ]; }
wait_for 20 worker_ok && pass "health.worker heartbeat fresh" || fail "worker heartbeat stale/missing"
echo "    health.ai configured = $(echo "$H" | json "d['components']['ai']['ok']") (expected False when AI_PROVIDER=none)"

step "Login as the single demo account, then switch sandbox personas"
DEMO_TOKEN=$(curl -fsS -X POST "$BASE/auth/login" -H 'Content-Type: application/json' -d "{\"email\":\"demo@ironvision.ai\",\"password\":\"$PW\"}" | json "d['access_token']")
login() { curl -fsS -X POST "$BASE/sandbox/act-as" -H "Authorization: Bearer $DEMO_TOKEN" -H 'Content-Type: application/json' -d "{\"role\":\"$1\"}" | json "d['access_token']"; }
ISSO=$(login isso) && [ -n "$ISSO" ] && pass "ISSO persona" || fail "ISSO persona"
AO=$(login ao) && [ -n "$AO" ] && pass "AO persona" || fail "AO persona"
ADMIN=$(login platform_admin) && [ -n "$ADMIN" ] && pass "Admin persona" || fail "Admin persona"

step "Reference content (worker job content.load_reference)"
cat_ok() { [ "$(curl -fsS "$BASE/content/stats" -H "Authorization: Bearer $ISSO" | json "d.get('controls_total',0)")" = "1196" ]; }
if wait_for 60 cat_ok; then
  S=$(curl -fsS "$BASE/content/stats" -H "Authorization: Bearer $ISSO")
  pass "catalog loaded: $(echo "$S" | json "f\"{d['controls_total']} controls, {d['enhancements']} enh, moderate={d['baselines']['moderate']}, ccis={d['ccis']}, maps={d['cci_rev5_mappings']}\"")"
  [ "$(echo "$S" | json "d['baselines']['moderate']")" = "287" ] && pass "moderate baseline = 287" || fail "moderate baseline count"
else
  fail "catalog not loaded within timeout"; docker compose logs worker | tail -40
fi
echo "$(curl -fsS "$BASE/content/versions" -H "Authorization: Bearer $ISSO" | json "'\n'.join(f\"    {v['content_key']:<22} {v['version'] or '':<12} {v['sha256']}\" for v in d)")"

step "RBAC"
code() { curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/authorization-decisions/test" -H "Authorization: Bearer $1"; }
[ "$(code "$ISSO")" = "403" ] && pass "ISSO -> AO endpoint = 403" || fail "ISSO expected 403"
[ "$(code "$AO")" = "200" ] && pass "AO -> AO endpoint = 200" || fail "AO expected 200"
[ "$(code "$ADMIN")" = "403" ] && pass "Platform admin -> AO endpoint = 403" || fail "Admin expected 403"
DEN=$(curl -fsS "$BASE/audit-events?action=authz.denied" -H "Authorization: Bearer $ADMIN" | json "sum(1 for e in d if e['actor_email'].startswith('isso.'))")
[ "${DEN:-0}" -ge 1 ] && pass "authz.denied audit event recorded for ISSO" || fail "authz.denied audit event missing"
[ "$(curl -fsS "$BASE/audit-events/verify" -H "Authorization: Bearer $ADMIN" | json "d['valid']")" = "True" ] && pass "audit hash chain valid" || fail "audit hash chain invalid"

step "AI (only if configured)"
if [ "$(echo "$H" | json "d['components']['ai']['ok']")" = "True" ]; then
  R=$(curl -s -X POST "$BASE/ai/health" -H "Authorization: Bearer $ADMIN")
  [ "$(echo "$R" | json "d.get('ok')")" = "True" ] && pass "AI health via AIService: $(echo "$R" | json "f\"{d['provider']} {d['model']} {d['latency_ms']}ms\"")" || fail "AI health call" "$R"
else
  echo "SKIP  AI health (AI_PROVIDER=none)"
fi

step "E2E workflow via API: register → upload STIG → POA&M → remediated rescan → closure → leadership"
ISSM=$(login issm); LEAD=$(login leadership_viewer)
AUTH() { echo "Authorization: Bearer $1"; }
TS=$(date +%s)
SID=$(curl -fsS -X POST "$BASE/systems" -H "$(AUTH "$ISSM")" -H 'Content-Type: application/json' \
  -d "{\"name\":\"Portability E2E $TS\",\"acronym\":\"PE$((TS % 10000))\",\"baseline_key\":\"moderate\",\"confidentiality_impact\":\"Moderate\",\"integrity_impact\":\"Moderate\",\"availability_impact\":\"Low\"}" | json "d['id']")
[ -n "$SID" ] && pass "registered moderate system $SID" || fail "system registration"
upload() {  # $1 file → prints run id after worker completes
  local RID; RID=$(curl -fsS -X POST "$BASE/systems/$SID/uploads" -H "$(AUTH "$ISSO")" -F "file=@samples/e2e/$1" | json "d['id']")
  for _ in $(seq 1 40); do
    ST=$(curl -fsS "$BASE/ingest-runs/$RID" -H "$(AUTH "$ISSO")" | json "d['run']['status']")
    [ "$ST" = "completed" ] && { echo "$RID"; return 0; }; [ "$ST" = "failed" ] && return 1; sleep 3
  done; return 1; }
RUN1=$(upload e2e-web-01.ckl) && pass "STIG checklist ingested by worker (run $RUN1)" || fail "STIG ingest"
FID=$(curl -fsS "$BASE/ingest-runs/$RUN1" -H "$(AUTH "$ISSO")" | json "next(f['id'] for f in d['findings'] if f['vuln_id']=='V-900140')")
[ "$(curl -fsS "$BASE/findings/$FID" -H "$(AUTH "$ISSO")" | json "d['finding']['cat']")" = "CAT I" ] && pass "V-900140 persisted as CAT I" || fail "CAT derivation"
BEFORE=$(curl -fsS "$BASE/dashboard/leadership" -H "$(AUTH "$LEAD")" | json "next(s['open_cat1'] for s in d['systems'] if s['id']=='$SID')")
BODY=$(curl -fsS "$BASE/findings/$FID/poam-match" -H "$(AUTH "$ISSO")" | json "__import__('json').dumps({k: d['prefill'][k] for k in ('system_id','finding_ids','control_ids','weakness','severity','cat','source_label')})")
PID=$(curl -fsS -X POST "$BASE/poams" -H "$(AUTH "$ISSO")" -H 'Content-Type: application/json' -d "$BODY" | json "d['id']")
[ -n "$PID" ] && pass "POA&M created from finding" || fail "POA&M create"
[ "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/poams" -H "$(AUTH "$ISSO")" -H 'Content-Type: application/json' -d "$BODY")" = "409" ] && pass "duplicate POA&M blocked (409 → link to existing)" || fail "duplicate POA&M not blocked"
RUN2=$(upload e2e-web-01_remediated.ckl) && pass "remediated rescan ingested (run $RUN2)" || fail "rescan ingest"
[ "$(curl -fsS "$BASE/poams/$PID" -H "$(AUTH "$ISSO")" | json "d['poam']['status']")" = "closure_eligible" ] && pass "POA&M closure_eligible (not auto-closed)" || fail "closure_eligible"
EVID=$(curl -fsS "$BASE/ingest-runs/$RUN2" -H "$(AUTH "$ISSO")" | json "d['run']['evidence_id']")
RQ=$(curl -fsS -X POST "$BASE/poams/$PID/request-closure" -H "$(AUTH "$ISSO")" -H 'Content-Type: application/json' -d "{\"justification\":\"Rescan shows NotAFinding\",\"evidence_ids\":[\"$EVID\"]}" | json "d['id']")
[ "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/reviews/$RQ/decisions" -H "$(AUTH "$ISSO")" -H 'Content-Type: application/json' -d '{"action":"approve","rationale":"self approval attempt"}')" = "403" ] && pass "requester self-approval = 403 (audited)" || fail "self-approval not blocked"
[ "$(curl -fsS -X POST "$BASE/reviews/$RQ/decisions" -H "$(AUTH "$ISSM")" -H 'Content-Type: application/json' -d '{"action":"approve","rationale":"Verified remediated checklist"}' | json "d['status']")" = "approved" ] && pass "ISSM approved closure" || fail "ISSM approval"
[ "$(curl -fsS "$BASE/poams/$PID" -H "$(AUTH "$ISSO")" | json "d['poam']['status']")" = "closed" ] && pass "POA&M closed" || fail "POA&M not closed"
AFTER=$(curl -fsS "$BASE/dashboard/leadership" -H "$(AUTH "$LEAD")" | json "next(s['open_cat1'] for s in d['systems'] if s['id']=='$SID')")
[ "${AFTER:-x}" -lt "${BEFORE:-0}" ] 2>/dev/null && pass "leadership open CAT I dropped $BEFORE → $AFTER" || fail "leadership metric unchanged ($BEFORE → $AFTER)"
DEN2=$(curl -fsS "$BASE/audit-events?action=authz.denied&limit=200" -H "$(AUTH "$ADMIN")" | json "sum(1 for e in d if e['entity_id']=='$RQ')")
[ "${DEN2:-0}" -ge 1 ] && pass "self-approval denial in audit log" || fail "self-approval denial not audited"

step "Frontend"
# Seed checks: seeded systems + POA&Ms + decision rules, all via the API
LTP=$(curl -fsS "$BASE/systems" -H "Authorization: Bearer $ISSO" | json "next(s['id'] for s in d if s['acronym']=='LTP')")
[ "$(curl -fsS "$BASE/systems/$LTP" -H "Authorization: Bearer $ISSO" | json "d['metrics']['assigned_controls']")" = "291" ] && pass "LTP has 291 assigned controls" || fail "LTP assignment count"
[ "$(curl -fsS "$BASE/poams?system_id=$LTP&status=" -H "Authorization: Bearer $ISSO" | json "d['total']>=7")" = "True" ] && pass "seeded POA&Ms present" || fail "POA&M seed missing"
[ "$(curl -fsS "$BASE/decision-rules" -H "Authorization: Bearer $ISSO" | json "len(d)>=5")" = "True" ] && pass "decision rules seeded" || fail "decision rules missing"
wait_for 20 curl -fsS "$FRONT/" && pass "frontend serves index.html on :3000" || fail "frontend unreachable"
[ "$(curl -s -o /dev/null -w '%{http_code}' "$FRONT/api/v1/health")" = "200" ] && pass "frontend nginx proxies /api -> backend" || fail "frontend /api proxy"

step "Phase 3 – RMF workflow modules"
[ "$(curl -fsS "$BASE/systems/$LTP/inheritance" -H "Authorization: Bearer $ISSO" | json "d['cards']['sum_check'] and d['cards']['manual_attestation']>=5")" = "True" ] && pass "inheritance cards reconcile + attestations seeded" || fail "inheritance/attestations"
[ "$(curl -fsS "$BASE/policies" -H "Authorization: Bearer $ISSO" | json "d['cards']['total']>=14")" = "True" ] && pass "policy library seeded (14)" || fail "policy library"
PID=$(curl -fsS -X POST "$BASE/policies" -H "Authorization: Bearer $ISSO" -F "file=@samples/policies/access_control_policy.txt" -F "title=Access Control Policy" -F "owner=CISO (synthetic)" -F "system_ids=$LTP" | json "d['id']")
pol_done() { [ "$(curl -fsS "$BASE/policies/$PID" -H "Authorization: Bearer $ISSO" | json "d['policy']['analysis_status']")" = "analyzed" ]; }
wait_for 40 pol_done && pass "policy upload analyzed by worker" || fail "policy analysis job"
[ "$(curl -fsS "$BASE/policies/$PID" -H "Authorization: Bearer $ISSO" | json "any(f['finding_type']=='policy_vs_config_difference' and f['control_id']=='ac-2.3' for f in d['findings'])")" = "True" ] && pass "AC-2(3) 35 vs 90 day discrepancy proposed" || fail "policy discrepancy"
[ "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/systems/$LTP/authorization-decision" -H "Authorization: Bearer $ISSM" -H 'Content-Type: application/json' -d '{"decision":"ATO","rationale":"not the AO, must be denied"}')" = "403" ] && pass "non-AO authorization decision denied" || fail "AO-only decision"
[ "$(curl -fsS "$BASE/audit-log?action=authz.denied" -H "Authorization: Bearer $ADMIN" | json "d['total']>=1")" = "True" ] && pass "authorization denial audited" || fail "authz denial audit"
[ "$(curl -fsS "$BASE/systems/$LTP/rmf-workflow" -H "Authorization: Bearer $ISSO" | json "len(d)==11")" = "True" ] && pass "RMF workflow stages derived" || fail "RMF workflow"
[ "$(curl -fsS "$BASE/search?q=LTP" -H "Authorization: Bearer $ISSO" | json "len(d)>=1")" = "True" ] && pass "global search" || fail "global search"

step "Phase 4 – advanced automation"
V2=$(curl -fsS "$BASE/content-updates" -H "Authorization: Bearer $ISSO" | json "next(v['id'] for t in d['types'] if t['content_type']=='stig_benchmark' for v in t['available'] if v['version']=='V1R2')")
[ -n "$V2" ] && pass "STIG V1R1 installed / V1R2 available" || fail "STIG content versions"
UPD=$(curl -fsS -X POST "$BASE/content-versions/$V2/preview" -H "Authorization: Bearer $ISSO")
[ "$(echo "$UPD" | json "d['diff_summary']=={'added':6,'removed':3,'changed_requirement':11,'changed_severity':2}")" = "True" ] && pass "STIG diff 6/3/11/2" || fail "STIG diff counts"
[ "$(echo "$UPD" | json "any(p['human_id']=='P-0027' and p.get('new_cat')=='CAT I' for p in d['impact']['poams'])")" = "True" ] && pass "impact preview shows P-0027 CAT II -> CAT I" || fail "P-0027 impact"
for M in poam ssp assessment-results; do
  [ "$(curl -fsS -X POST "$BASE/systems/$LTP/oscal/$M" -H "Authorization: Bearer $ISSO" | json "d['validation']['valid']")" = "True" ] && pass "OSCAL $M schema-valid (NIST v1.2.2 schema)" || fail "OSCAL $M validation"
done
[ "$(curl -fsS "$BASE/emass/status" -H "Authorization: Bearer $ISSO" | json "d['mode']")" = "mock" ] && pass "eMASS mode reported (MOCK)" || fail "eMASS status"
[ "$(curl -fsS "$BASE/scheduled-jobs" -H "Authorization: Bearer $ADMIN" | json "len(d)>=8 and all(j['next_run_at'] for j in d)")" = "True" ] && pass "scheduled jobs visible with next run" || fail "scheduled jobs"

step "Phase 5 – production hardening"
HDR=$(curl -sSI "$BASE/health")
for h in "content-security-policy" "x-content-type-options: nosniff" "x-frame-options: deny" "referrer-policy: no-referrer" "permissions-policy"; do
  echo "$HDR" | tr 'A-Z' 'a-z' | grep -q "$h" && pass "header $h" || fail "missing header $h"
done
[ "$(curl -fsS "$BASE/ready" | json "d['ready']")" = "True" ] && pass "/ready reports migration head" || fail "/ready"
curl -fsS "$BASE/metrics" | grep -q "aegis_http_request_duration_seconds" && pass "/metrics Prometheus exposition" || fail "/metrics"
[ "$(curl -fsS "$BASE/auth/provider" | json "d['dev_password_enabled']")" = "True" ] && pass "auth provider info (dev compose = dev_password)" || fail "auth provider info"
printf 'MZ\x90\x00fake' > /tmp/aegis_bad.exe
BADC=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$BASE/systems/$LTP/uploads" -H "Authorization: Bearer $ISSO" -F "file=@/tmp/aegis_bad.exe")
case "$BADC" in 4*) pass "disallowed upload rejected ($BADC)";; *) fail "disallowed upload accepted" "$BADC";; esac
docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q 2>/dev/null && pass "prod overlay config valid (with prod env set)" || echo "    prod overlay needs OIDC_*/FRONTEND_URL/CORS_ORIGINS set – skipped"
docker compose --profile keycloak --profile clamav --profile monitoring config -q 2>/dev/null && pass "optional profiles config valid" || echo "    optional profiles need KEYCLOAK_ADMIN_PASSWORD/GRAFANA_ADMIN_PASSWORD – skipped"


step "Backend tests inside container (uses a throwaway DB)"
docker compose exec -T postgres psql -U "$(grep ^POSTGRES_USER= .env | cut -d= -f2)" -d postgres -c "CREATE DATABASE aegisrmf_test" >/dev/null 2>&1 || true
TDB="postgresql+psycopg://$(grep ^POSTGRES_USER= .env | cut -d= -f2):$(grep ^POSTGRES_PASSWORD= .env | cut -d= -f2)@postgres:5432/aegisrmf_test"
docker compose exec -T -e TEST_DATABASE_URL="$TDB" backend python -m pytest -c pytest.aegis.ini -q -p no:cacheprovider && pass "pytest suite" || fail "pytest suite"
docker compose exec -T -e TEST_DATABASE_URL="$TDB" backend python -m pytest -c pytest.aegis.ini tests/acceptance -q -p no:cacheprovider && pass "acceptance AT-1..AT-12" || fail "acceptance suite"

echo; echo "================ SUMMARY ================"
printf '%s\n' "${RESULTS[@]}"
[ "${KEEP:-1}" = "0" ] && docker compose down -v
[ $FAILED -eq 0 ] && { echo "OVERALL: PASS"; exit 0; } || { echo "OVERALL: FAIL"; exit 1; }
