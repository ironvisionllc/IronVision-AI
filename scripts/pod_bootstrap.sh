#!/usr/bin/env bash
# EMERGENT PREVIEW POD ONLY: re-provision PostgreSQL 16 + supervisor programs after a pod restart
# (apt packages and /etc/supervisor live outside the persistent /app volume). Not used by Docker/Compose.
set -euo pipefail
if [ ! -x /usr/lib/postgresql/16/bin/postgres ]; then
  apt-get update -qq && apt-get install -y -qq curl ca-certificates gnupg
  install -d /usr/share/postgresql-common/pgdg
  curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc
  echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" > /etc/apt/sources.list.d/pgdg.list
  apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get install -y -qq postgresql-16
fi
chown -R postgres:postgres /app/data/postgres && chmod 700 /app/data/postgres
cp /app/deploy/emergent-pod/aegis-supervisor.conf /etc/supervisor/conf.d/aegis.conf
supervisorctl status >/dev/null 2>&1 || [ $? -ne 4 ] || { supervisord -c /etc/supervisor/supervisord.conf; sleep 8; }  # 4 = no socket (supervisord down)
supervisorctl reread && supervisorctl update
supervisorctl stop mongodb || true
sleep 3
(cd /app/backend && /root/.venv/bin/alembic upgrade head)
supervisorctl restart backend worker
supervisorctl status
