#!/usr/bin/env bash
# IronVision AI – one-command deploy on the Droplet:
#   ./deploy.sh [ENV_FILE] [--set-domain DOMAIN [--email LETSENCRYPT_EMAIL]] [--skip-edge-check] [--no-cache] [--force-tls] [...]
#   e.g. ./deploy.sh --set-domain demo.ironvisionai.com --email k.hill@theironvision.com
# ENV_FILE defaults to deploy/digitalocean/.env.production (git-ignored; lives only on the Droplet).
#  - missing env file → created from deploy/digitalocean/env.production.template, secrets generated, then STOPS so the
#    operator fills the non-secret values (never deploys placeholders);
#  - existing env file → check_env --fix (backup first), gen_env_secrets (fills only EMPTY secrets), check_env must PASS,
#    then scripts/deploy.sh (fail-fast) with the remaining flags.
# The env file is never sourced or evaluated; single values are read with scripts/envget.py.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

F="deploy/digitalocean/.env.production"
if [ $# -gt 0 ] && [ "${1#--}" = "$1" ]; then F="$1"; shift; fi
DOMAIN_NEW=""
EMAIL_NEW=""
PASS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --set-domain) DOMAIN_NEW="${2:?--set-domain needs a hostname}"; shift ;;
    --email) EMAIL_NEW="${2:?--email needs an address}"; shift ;;
    *) PASS+=("$1") ;;
  esac
  shift
done
TEMPLATE="deploy/digitalocean/env.production.template"

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
get() { python3 scripts/envget.py "$F" "$1"; }
command -v python3 >/dev/null || die "python3 is required on the host (apt-get install -y python3)"

if command -v git >/dev/null && git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
   && git ls-files --error-unmatch "$F" >/dev/null 2>&1; then
  die "$F is tracked by git – it would publish your secrets. Untrack it first:
  git rm --cached $F && git commit -m 'stop tracking env file'   (then rotate every secret it contained)"
fi

# Non-secret values the operator must set (OIDC only when enabled, AI key only when an API provider is selected).
needs_input() {
  local k v gaps=()
  local keys=(APP_DOMAIN FRONTEND_URL CORS_ORIGINS)
  case ",$(get AUTH_PROVIDERS)," in *",oidc,"*) keys+=(OIDC_ISSUER OIDC_CLIENT_ID OIDC_CLIENT_SECRET OIDC_REDIRECT_URI) ;; esac
  [ -n "$(get CERT_FULLCHAIN_PATH)" ] || keys+=(LETSENCRYPT_EMAIL)
  case "$(get AI_PROVIDER)" in openrouter|openai_compatible) keys+=(OPENAI_COMPAT_API_KEY AI_MODEL) ;; anthropic) keys+=(ANTHROPIC_API_KEY AI_MODEL) ;; esac
  for k in "${keys[@]}"; do
    v="$(get "$k")"
    case "$v" in ""|*example.gov*|*example.com*|*changeme*|*change-me*) gaps+=("$k") ;; esac
  done
  printf "%s\n" "${gaps[@]}"
}

set_domain() {
  [ -z "$DOMAIN_NEW" ] && return 0
  local a=("$F" "$DOMAIN_NEW")
  [ -n "$EMAIL_NEW" ] && a+=(--email "$EMAIL_NEW")
  python3 scripts/set_domain.py "${a[@]}" || die "could not set the domain"
}

if [ ! -f "$F" ]; then
  [ -f "$TEMPLATE" ] || die "template $TEMPLATE not found – run git pull first"
  install -m 600 "$TEMPLATE" "$F"
  python3 scripts/gen_env_secrets.py "$F"
  set_domain
  if [ -z "$DOMAIN_NEW" ] || [ -n "$(needs_input)" ]; then
    printf '\n#### Created %s (mode 600) with generated secrets. NOT deployed yet.\n' "$F"
    printf '#### Edit it and set these values, then run ./deploy.sh again:\n'
    needs_input | sed 's/^/     - /'
    printf '     (AI is off by default: AI_PROVIDER=none. For OpenRouter set AI_PROVIDER=openrouter, OPENAI_COMPAT_API_KEY, AI_MODEL.)\n'
    exit 2
  fi
  printf '\n#### Created %s for %s – continuing with the deploy\n' "$F" "$DOMAIN_NEW"
  DOMAIN_NEW=""
fi

chmod 600 "$F"
set_domain
python3 scripts/check_env.py --fix "$F" | grep -E "check_env --fix|FIXED|MANUAL" || true
python3 scripts/gen_env_secrets.py "$F" | sed -n '2p'
missing="$(needs_input)"
if [ -n "$missing" ]; then
  printf '\nERROR: %s still has empty or placeholder values – set them and re-run ./deploy.sh:\n' "$F" >&2
  printf '%s\n' "$missing" | sed 's/^/     - /' >&2
  exit 2
fi
python3 scripts/check_env.py "$F" || die "fix the ERROR lines above in $F, then re-run ./deploy.sh"
exec scripts/deploy.sh "$F" "${PASS[@]}"
