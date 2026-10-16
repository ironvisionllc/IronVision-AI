#!/usr/bin/env bash
# EMERGENT PREVIEW POD ONLY: (re)provision a REAL Keycloak 26.8.1 (official tarball + Temurin JDK 21, Postgres DB keycloak_test)
# for the live tests, write /opt/kc/kcenv.sh, start Keycloak on :8090 and apply the realm with the configurator.
# Idempotent; not used by Docker/Compose or the Droplet.
set -euo pipefail
KC=/opt/kc
mkdir -p "$KC" && cd "$KC"
arch=$(uname -m); [ "$arch" = aarch64 ] && jarch=aarch64 || jarch=x64
if [ ! -x "$KC/jdk/bin/java" ]; then
  curl -fsSL -o jdk.tgz "https://api.adoptium.net/v3/binary/latest/21/ga/linux/$jarch/jdk/hotspot/normal/eclipse"
  mkdir -p jdk && tar -xzf jdk.tgz -C jdk --strip-components=1 && rm -f jdk.tgz
fi
if [ ! -x "$KC/keycloak/bin/kc.sh" ]; then
  curl -fsSL -o kc.tgz https://github.com/keycloak/keycloak/releases/download/26.8.1/keycloak-26.8.1.tar.gz
  mkdir -p keycloak && tar -xzf kc.tgz -C keycloak --strip-components=1 && rm -f kc.tgz
fi
FRESH=0
if [ ! -f "$KC/kcenv.sh" ]; then
  FRESH=1
  r() { python3 -c 'import secrets;print(secrets.token_urlsafe(30))'; }
  cat > "$KC/kcenv.sh" <<EOF
export JAVA_HOME=$KC/jdk
export KEYCLOAK_URL=http://localhost:8090
export KEYCLOAK_REALM=ironvision-demo
export KC_DB_PASSWORD=$(r)
export KC_BOOTSTRAP_ADMIN_USERNAME=bootstrap-admin
export KC_BOOTSTRAP_ADMIN_PASSWORD=$(r)
export KEYCLOAK_ADMIN_USERNAME=ironvision-admin
export KEYCLOAK_ADMIN_PASSWORD=$(r)
export KEYCLOAK_CONFIGURATOR_CLIENT_ID=ironvision-configurator
export KEYCLOAK_CONFIGURATOR_CLIENT_SECRET=$(r)
export OIDC_ISSUER=http://localhost:8090/realms/ironvision-demo
export OIDC_CLIENT_ID=ironvision-app
export OIDC_CLIENT_SECRET=$(r)
export OIDC_REDIRECT_URI=http://testserver/api/v1/auth/oidc/callback
export OIDC_POST_LOGOUT_REDIRECT_URI=http://spa.test/login
export KEYCLOAK_DEMO_USERNAME=demo-launcher-$(python3 -c 'import secrets;print(secrets.token_hex(6))')
export KEYCLOAK_DEMO_PASSWORD=$(r)
export KEYCLOAK_DEMO_LAUNCHER_CLIENT_ID=ironvision-demo-launcher
export KEYCLOAK_DEMO_LAUNCHER_CLIENT_SECRET=$(r)
export KEYCLOAK_BACKEND_CLIENT_ID=ironvision-backend
export KEYCLOAK_BACKEND_CLIENT_SECRET=$(r)
export KEYCLOAK_ALLOW_REGISTRATION=true
export DEPLOYMENT_KIND=demo
export SIGNUP_RATE_LIMIT=1000/3600
EOF
  chmod 600 "$KC/kcenv.sh"
fi
# shellcheck disable=SC1091
. "$KC/kcenv.sh"
if [ "$FRESH" = 1 ]; then   # new secrets → the old disposable Keycloak DB (bootstrap admin) is unusable
  pkill -f "kc.sh start-dev" || true; pkill -f "org.keycloak" || true; sleep 3
  su postgres -c "psql -h /tmp -c 'drop database if exists keycloak_test with (force)'"
fi
su postgres -c "psql -h /tmp -tAc \"select 1 from pg_roles where rolname='keycloak_test'\"" | grep -q 1 \
  || su postgres -c "psql -h /tmp -c \"create role keycloak_test login password '$KC_DB_PASSWORD'\""
su postgres -c "psql -h /tmp -c \"alter role keycloak_test password '$KC_DB_PASSWORD'\"" >/dev/null
su postgres -c "psql -h /tmp -tAc \"select 1 from pg_database where datname='keycloak_test'\"" | grep -q 1 \
  || su postgres -c "psql -h /tmp -c 'create database keycloak_test owner keycloak_test'"
if ! curl -sf -o /dev/null http://localhost:9090/health/ready 2>/dev/null; then
  (cd "$KC/keycloak" && KC_BOOTSTRAP_ADMIN_USERNAME=$KC_BOOTSTRAP_ADMIN_USERNAME KC_BOOTSTRAP_ADMIN_PASSWORD=$KC_BOOTSTRAP_ADMIN_PASSWORD \
    setsid nohup bin/kc.sh start-dev --http-port 8090 --http-management-port 9090 --health-enabled=true --db postgres \
    --db-url jdbc:postgresql://127.0.0.1:5432/keycloak_test --db-username keycloak_test --db-password "$KC_DB_PASSWORD" \
    > "$KC/kc.log" 2>&1 < /dev/null &)
  for _ in $(seq 1 120); do curl -sf -o /dev/null http://localhost:9090/health/ready && break; sleep 2; done
fi
curl -sf -o /dev/null http://localhost:9090/health/ready || { tail -20 "$KC/kc.log"; exit 1; }
cd /app/backend && python -m app.tools.keycloak_config apply --yes | tail -2
echo "pod Keycloak ready: . $KC/kcenv.sh"
