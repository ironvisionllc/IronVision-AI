# shellcheck shell=bash
# Safe env-file access for scripts. Env files are DATA: never `source`/`. ` them (an unquoted value with spaces such as
# OIDC_SCOPES=openid email profile would run `email` as a command). Usage after `. scripts/lib/envfile.sh`:
#   APP_DOMAIN="$(env_get deploy/digitalocean/.env.production APP_DOMAIN)"
ENVFILE_GET_PY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/envget.py"

env_get() {
  python3 "$ENVFILE_GET_PY" "$1" "$2"
}

# env_export FILE KEY... – export the named keys (and only those) into the current process environment.
env_export() {
  local file="$1" key
  shift
  for key in "$@"; do
    export "$key=$(env_get "$file" "$key")"
  done
}
