#!/usr/bin/env bash
# TLS for the edge nginx, run by scripts/deploy.sh. Never sources the env file.
#   scripts/ensure_tls.sh ensure ENV_FILE -- <docker compose command...>   obtain/install a certificate if needed (edge not serving yet)
#   scripts/ensure_tls.sh verify ENV_FILE                                   check the live certificate + https /api/v1/ready
# Certificate sources: CERT_FULLCHAIN_PATH + CERT_KEY_PATH (user-supplied, copied in) or Let's Encrypt (certbot --standalone on
# port 80 for the first issuance; renewals use the webroot through the running edge – ironvision-certbot-renew.timer).
# LETSENCRYPT_STAGING=true uses the Let's Encrypt staging CA (untrusted, no rate limits). FORCE_TLS=1 skips the DNS preflight.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
MODE="${1:?usage: ensure_tls.sh ensure|verify ENV_FILE [-- compose...]}"
ENV_FILE="${2:?env file}"
shift 2
[ "${1:-}" = "--" ] && shift
DC=("$@")

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
get() { python3 scripts/envget.py "$ENV_FILE" "$1"; }
DOMAIN="$(get APP_DOMAIN)"
DATA_ROOT="$(get DATA_ROOT)"
EMAIL="$(get LETSENCRYPT_EMAIL)"
STAGING="$(get LETSENCRYPT_STAGING)"
USER_CERT="$(get CERT_FULLCHAIN_PATH)"
USER_KEY="$(get CERT_KEY_PATH)"
LIVE="$DATA_ROOT/letsencrypt/live/$DOMAIN"
if [ -z "$DOMAIN" ] || [ -z "$DATA_ROOT" ]; then die "APP_DOMAIN and DATA_ROOT must be set in $ENV_FILE"; fi

cert_ok() {   # valid for DOMAIN, > 30 days left, and from the CA we want
  local f="$LIVE/fullchain.pem" issuer
  [ -s "$f" ] || { echo "no certificate at $f"; return 1; }
  openssl x509 -in "$f" -noout -checkend 2592000 >/dev/null || { echo "certificate expires within 30 days"; return 1; }
  openssl x509 -in "$f" -noout -checkhost "$DOMAIN" | grep -q "does match" || { echo "certificate is not valid for $DOMAIN"; return 1; }
  issuer="$(openssl x509 -in "$f" -noout -issuer)"
  if [ -z "$USER_CERT" ] && [ "$STAGING" != "true" ] && grep -qi "staging" <<<"$issuer"; then
    echo "certificate is from the Let's Encrypt STAGING CA"; return 1
  fi
  return 0
}

public_ip() {
  curl -fsS -4 --max-time 3 http://169.254.169.254/metadata/v1/interfaces/public/0/ipv4/address 2>/dev/null \
    || curl -fsS -4 --max-time 8 https://ifconfig.me 2>/dev/null || true
}

dns_preflight() {
  local resolved ip
  resolved="$(getent ahostsv4 "$DOMAIN" 2>/dev/null | awk 'NR==1 {print $1}')"
  ip="$(public_ip)"
  if [ -z "$resolved" ]; then
    die "$DOMAIN does not resolve. Create DNS A record $DOMAIN → ${ip:-<the Droplet public IPv4>} (and AAAA if you use IPv6), wait for it to propagate, then re-run. (--force-tls skips this check)"
  fi
  if [ -n "$ip" ] && [ "$resolved" != "$ip" ]; then
    die "$DOMAIN resolves to $resolved but this Droplet is $ip. Create DNS A record $DOMAIN → $ip, then re-run. (--force-tls skips this check)"
  fi
  [ -n "$ip" ] || printf 'WARN: could not determine the public IP – DNS check limited to "%s resolves"\n' "$DOMAIN" >&2
  echo "DNS: $DOMAIN → $resolved (matches this Droplet)"
}

port80_free() {
  local busy
  busy="$(ss -ltnpH 'sport = :80' 2>/dev/null || true)"
  [ -z "$busy" ] && return 0
  grep -q docker-proxy <<<"$busy" && return 0      # our own edge – stopped below
  die "port 80 is used by another program – stop it (e.g. systemctl disable --now nginx apache2), then re-run:
$busy"
}

install_user_cert() {
  if [ ! -s "$USER_CERT" ] || [ ! -s "$USER_KEY" ]; then die "CERT_FULLCHAIN_PATH / CERT_KEY_PATH must point to existing PEM files"; fi
  openssl x509 -in "$USER_CERT" -noout -checkhost "$DOMAIN" | grep -q "does match" || die "$USER_CERT is not valid for $DOMAIN"
  [ "$(openssl x509 -in "$USER_CERT" -noout -pubkey | openssl sha256)" = "$(openssl pkey -in "$USER_KEY" -pubout | openssl sha256)" ] \
    || die "CERT_KEY_PATH does not match CERT_FULLCHAIN_PATH"
  install -d -m 755 "$DATA_ROOT/letsencrypt/live"
  install -d -m 700 "$LIVE"
  install -m 644 "$USER_CERT" "$LIVE/fullchain.pem"
  install -m 600 "$USER_KEY" "$LIVE/privkey.pem"
  echo "installed user-supplied certificate for $DOMAIN into $LIVE"
}

ensure() {
  local why args
  if [ -n "$USER_CERT" ]; then
    cert_ok >/dev/null 2>&1 && cmp -s "$USER_CERT" "$LIVE/fullchain.pem" && { echo "user-supplied certificate already installed"; return 0; }
    install_user_cert
    return 0
  fi
  if why="$(cert_ok)"; then
    echo "certificate for $DOMAIN is valid until $(openssl x509 -in "$LIVE/fullchain.pem" -noout -enddate | cut -d= -f2) – nothing to do"
    return 0
  fi
  echo "certificate needed: $why"
  [ -n "$EMAIL" ] || die "LETSENCRYPT_EMAIL is required for Let's Encrypt – run: ./deploy.sh --set-domain $DOMAIN --email you@your-org"
  [ "${#DC[@]}" -gt 0 ] || die "internal: compose command missing"
  [ "${FORCE_TLS:-0}" = "1" ] || dns_preflight
  "${DC[@]}" stop edge >/dev/null 2>&1 || true
  port80_free
  args=(certonly --standalone --non-interactive --agree-tos -m "$EMAIL" --no-eff-email -d "$DOMAIN" --keep-until-expiring)
  [ "$STAGING" = "true" ] && args+=(--staging)
  grep -q "STAGING" <<<"$why" && args+=(--force-renewal)
  install -d -m 755 "$DATA_ROOT/letsencrypt" "$DATA_ROOT/certbot/www"
  "${DC[@]}" --profile certbot run --rm --no-deps -p 80:80 certbot "${args[@]}"
  chown -R root:root "$DATA_ROOT/letsencrypt" 2>/dev/null || true   # edge nginx master (root) reads it via the :ro mount
  why="$(cert_ok)" || die "certbot finished but the certificate is still not usable: $why"
  echo "certificate for $DOMAIN obtained$([ "$STAGING" = "true" ] && echo ' (STAGING – browsers will not trust it)')"
}

verify() {
  local info curl_k=()
  info="$(openssl s_client -connect "$DOMAIN:443" -servername "$DOMAIN" </dev/null 2>/dev/null \
          | openssl x509 -noout -subject -issuer -ext subjectAltName 2>/dev/null || true)"
  grep -q "DNS:$DOMAIN" <<<"$info" || die "https://$DOMAIN does not present a certificate for $DOMAIN:
$info"
  if [ -z "$USER_CERT" ]; then
    grep -qiE "Let's Encrypt|\(STAGING\)" <<<"$info" || die "certificate on $DOMAIN:443 is not issued by Let's Encrypt:
$info"
  fi
  [ "$STAGING" = "true" ] && curl_k=(-k)
  curl -fsS "${curl_k[@]}" --max-time 15 --retry 10 --retry-delay 3 --retry-all-errors "https://$DOMAIN/api/v1/ready" >/dev/null \
    || die "https://$DOMAIN/api/v1/ready did not answer – check the DO firewall (80/443) and: docker compose logs edge"
  echo "TLS OK: $(grep -m1 -i issuer <<<"$info") · https://$DOMAIN/api/v1/ready answered"
}

case "$MODE" in
  ensure) ensure ;;
  verify) verify ;;
  *) die "unknown mode $MODE" ;;
esac
