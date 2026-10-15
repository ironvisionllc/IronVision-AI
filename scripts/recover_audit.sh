#!/usr/bin/env bash
# shellcheck disable=SC2015  # ok() always returns 0, so `A && ok || bad` is a safe if/else
# Configuration-chain audit (host side, read-only, secrets redacted): DNS, TLS, edge nginx, built frontend API URL, routes via
# the edge, docker networks, effective compose config, demo vs customer separation. Keycloak checks: ./recover.sh audit (python).
#   scripts/recover_audit.sh [ENV_FILE]
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
ENV_FILE=${1:-deploy/digitalocean/.env.production}
DATA_ROOT=${DATA_ROOT:-/srv/ironvision}
FAILS=0
ok() { printf '  OK   %s\n' "$*"; }
bad() { printf '  FAIL %s\n' "$*"; FAILS=$((FAILS + 1)); }
warn() { printf '  WARN %s\n' "$*"; }
envget() { python3 scripts/envget.py "$ENV_FILE" "$1" 2>/dev/null || true; }
red() { sed -E 's#(://[^:/@ ]+):[^@ ]+@#\1:***@#g; s#((SECRET|PASSWORD|_KEY|TOKEN)[A-Z_]*[:=] *)[^ ]+#\1***#g'; }
APP=$(envget APP_DOMAIN); AUTH=$(envget AUTH_DOMAIN); KIND=$(envget DEPLOYMENT_KIND)
IP=$(curl -s --max-time 5 https://api.ipify.org || hostname -I | awk '{print $1}')

echo "[audit] DNS (droplet public IP ${IP:-unknown})"
for d in "$APP" "$AUTH"; do
  [ -n "$d" ] || { bad "domain not set in $ENV_FILE"; continue; }
  a=$(getent ahostsv4 "$d" | awk '{print $1}' | sort -u | tr '\n' ' ')
  if [[ " $a " == *" $IP "* ]]; then ok "$d A → $a"; else bad "$d resolves to '$a' (expected $IP)"; fi
done

echo "[audit] TLS"
for d in "$APP" "$AUTH"; do
  [ -n "$d" ] || continue
  out=$(echo | timeout 10 openssl s_client -connect "$d:443" -servername "$d" -verify_return_error 2>/dev/null)
  cert=$(openssl x509 -noout -subject -enddate -ext subjectAltName 2>/dev/null <<<"$out")
  if grep -q "Verify return code: 0" <<<"$out" && grep -q "DNS:$d" <<<"$cert"; then
    end=$(sed -n 's/notAfter=//p' <<<"$cert"); days=$(( ($(date -d "$end" +%s) - $(date +%s)) / 86400 ))
    if [ "$days" -ge 14 ]; then ok "$d chain valid, SAN ok, expires in $days days"; else bad "$d certificate expires in $days days"; fi
  else bad "$d TLS chain/SAN invalid: $(head -c 200 <<<"$cert")"; fi
done

if [ -f "$DATA_ROOT/compose.env" ]; then
  for k in COMPOSE_PROJECT_NAME COMPOSE_FILE COMPOSE_PROFILES; do
    v=$(python3 scripts/envget.py "$DATA_ROOT/compose.env" "$k" 2>/dev/null || true); [ -n "$v" ] && export "$k=$v"
  done
  DC=(docker compose --env-file "$ENV_FILE")
  echo "[audit] edge nginx effective config"
  conf=$("${DC[@]}" exec -T edge nginx -T 2>/dev/null)
  for d in "$APP" "$AUTH"; do grep -q "server_name $d" <<<"$conf" && ok "server_name $d" || bad "server_name $d missing"; done
  grep -q "proxy_pass http://backend" <<<"$conf" && ok "/api → backend upstream" || bad "no backend upstream for /api"
  grep -qE "proxy_pass \\\$keycloak|keycloak:8080" <<<"$conf" && ok "auth domain → keycloak:8080" || bad "no Keycloak upstream"
  grep -q "X-Forwarded-Proto" <<<"$conf" && ok "X-Forwarded-* headers set" || bad "X-Forwarded-Proto not set"
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://$AUTH/admin/master/console/"); [ "$code" = 404 ] || [ "$code" = 403 ] && ok "public /admin blocked ($code)" || bad "public /admin returns $code"
  code=$(curl -s -o /dev/null -w '%{http_code}' "https://$AUTH/realms/master/"); [ "$code" = 404 ] || [ "$code" = 403 ] && ok "public /realms/master blocked ($code)" || bad "public /realms/master returns $code"

  echo "[audit] frontend bundle API base URL"
  urls=$("${DC[@]}" exec -T frontend sh -c 'cat /usr/share/nginx/html/static/js/*.js 2>/dev/null' | grep -oE 'https?://[a-zA-Z0-9.:-]+' | sort -u | grep -vE 'w3\.org|reactjs|github|schema|mozilla|ietf|example' | head -20 | tr '\n' ' ')
  if grep -qE 'localhost|127\.0\.0\.1|preview\.emergentagent|emergent' <<<"$urls"; then bad "bundle contains dev/preview URLs: $urls"; else ok "bundle URLs: ${urls:-(same-origin)}"; fi

  echo "[audit] routes via the edge"
  for p in /api/v1/health/live /api/v1/auth/provider; do c=$(curl -s -o /dev/null -w '%{http_code}' "https://$APP$p"); [ "$c" = 200 ] && ok "https://$APP$p → 200" || bad "https://$APP$p → $c"; done
  c=$(curl -s -o /dev/null -w '%{http_code}' "https://$APP/api/v1/auth/oidc/login"); [ "$c" = 307 ] && ok "oidc/login → 307" || bad "oidc/login → $c"
  c=$(curl -s -o /dev/null -w '%{http_code}' "https://$AUTH/realms/$(envget KEYCLOAK_REALM)/.well-known/openid-configuration"); [ "$c" = 200 ] && ok "public discovery → 200" || bad "public discovery → $c"

  echo "[audit] docker networks"
  for c in $("${DC[@]}" ps -q); do docker inspect -f '  {{.Name}}: {{range $k,$v := .NetworkSettings.Networks}}{{$k}} {{end}}' "$c"; done
  echo "[audit] effective compose config (redacted)"
  "${DC[@]}" config --format json 2>/dev/null | python3 -c '
import json,sys,re
c=json.load(sys.stdin)
for n,s in sorted(c["services"].items()):
    e=s.get("environment") or {}
    keep={k:("***" if re.search("SECRET|PASSWORD|_KEY$|TOKEN",k) else re.sub(r"://([^:/@]+):[^@]+@",r"://\1:***@",str(v))) for k,v in e.items()
          if re.search("DATABASE_URL|S3_ENDPOINT|S3_BUCKET|DOMAIN|OIDC_ISSUER|OIDC_REDIRECT|KEYCLOAK_URL|AUTH_PROVIDERS|DEPLOYMENT_KIND|ALLOW_DEMO|REGISTRATION|APP_ENV",k)}
    print(f"  {n}: image={s.get(\"image\",\"(build)\")} ports={[p.get(\"published\") and (p.get(\"host_ip\",\"0.0.0.0\")+\":\"+str(p[\"published\"])) for p in s.get(\"ports\",[])]}")
    for k,v in sorted(keep.items()): print(f"      {k}={v}")
'
else warn "$DATA_ROOT/compose.env missing – compose/edge/network checks skipped"; fi

echo "[audit] demo vs customer-production separation"
[ "$KIND" = demo ] && ok "DEPLOYMENT_KIND=demo" || warn "DEPLOYMENT_KIND=${KIND:-(empty)}"
c=deploy/digitalocean/env.customer-production.template
grep -q '^KEYCLOAK_ALLOW_REGISTRATION=false' "$c" && grep -q '^ALLOW_DEMO_LOGIN=false' "$c" && ok "customer template: signup/registration/demo disabled" || bad "customer template enables signup/demo"
if [ -f deploy/digitalocean/.env.customer-production ]; then
  for k in KEYCLOAK_REALM POSTGRES_DB S3_BUCKET OIDC_CLIENT_ID APP_DOMAIN; do
    [ "$(envget "$k")" != "$(python3 scripts/envget.py deploy/digitalocean/.env.customer-production "$k")" ] && ok "$k differs demo vs customer" || bad "$k identical in demo and customer env"
  done
fi
echo "[audit] $FAILS failing check(s)" | red
exit $(( FAILS > 0 ))
