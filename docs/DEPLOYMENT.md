# Deployment

## 1. Development / evaluation (single host)
```bash
git clone <repo> aegisrmf && cd aegisrmf
cp .env.example .env              # set POSTGRES_PASSWORD, MINIO_ROOT_PASSWORD, JWT_SECRET, SECRET_STORE_KEY
docker compose up -d --build      # migrate (alembic upgrade head + seed) runs once, then backend :8001, worker, frontend :3000
./scripts/verify_portability.sh   # end-to-end PASS/FAIL report
```
Synthetic demo accounts (dev_password) are seeded. See `memory/test_credentials.md`.

Optional profiles:
| Profile | Services | Use |
|---|---|---|
| `keycloak` | Keycloak 26 + `deploy/keycloak/aegisrmf-realm.json` on :8081 | Local OIDC. Set `AUTH_PROVIDERS=dev_password,oidc`, `OIDC_ISSUER=http://localhost:8081/realms/aegisrmf`, `OIDC_CLIENT_ID=aegisrmf`, `OIDC_REDIRECT_URI=http://localhost:3000/api/v1/auth/oidc/callback`. Realm users must match IronVision AI user emails. |
| `clamav` | clamd | `UPLOAD_SCANNER=clamav` |
| `monitoring` | Prometheus :9090, Grafana :3001 (dashboard "IronVision AI – Operations") | Scrapes `/api/v1/metrics` |

`docker compose --profile keycloak --profile monitoring up -d`

## 2. Production overlay
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build    # or: make up-prod
```
The overlay sets `AUTH_PROVIDERS=oidc` (dev password off, login picker hidden) and `SEED_DEMO_DATA=false`. Only the `edge` nginx publishes ports (443/80). It requires `deploy/tls/tls.crt` and `deploy/tls/tls.key`, which are placeholders you provide. The overlay **fails fast** if `CORS_ORIGINS`, `FRONTEND_URL`, `OIDC_*` or `SECRET_STORE_KEY` are unset.

Checklist:
- [ ] Strong unique `JWT_SECRET` (≥ 32 bytes), `SECRET_STORE_KEY` (Fernet), and DB/S3 credentials. Prefer `SECRET_STORE_BACKEND=vault`.
- [ ] Managed PostgreSQL 16 with encryption at rest and PITR. S3 with SSE-KMS and versioning.
- [ ] Users provisioned in IronVision AI (Admin → Users) before their first OIDC login.
- [ ] `TRUST_PROXY_HEADERS=true` only behind your proxy. `MTLS_TRUSTED_PROXIES` set if CAC/PIV headers are used.
- [ ] Block `/api/v1/metrics` at the edge (already denied in `edge.conf`) and scrape it on the internal network.
- [ ] Scheduled backups (`scripts/backup.sh`) and a quarterly restore test (`scripts/restore.sh`).
- [ ] Multiple backend replicas: move rate limiting and OIDC `state` storage to a shared store (both are in-process today).

## 3. Without Docker
Requires Python 3.11, Node 20, and PostgreSQL 16. Steps: `backend/.env` from `backend/.env.example`, then `alembic upgrade head`, then `uvicorn app.main:app --host 0.0.0.0 --port 8001`, plus `python -m app.worker` and `yarn build` served by any static server that proxies `/api`.

## 4. Backup / restore
`scripts/backup.sh [OUT_DIR]` writes `db.dump` (pg_dump custom format), the object store archive, and `manifest.json` (SHA-256 of every artifact, alembic revision, audit-chain head hash).
`scripts/restore.sh BACKUP_DIR` restores into the configured `DATABASE_URL`/storage (always use an empty target), then verifies hashes, row counts, alembic revision, and the audit hash chain. It prints `RESTORE_VERIFY: PASS|FAIL`.
Executed in the build pod: backup, then restore into a scratch DB and storage path, gave **RESTORE_VERIFY: PASS** at revision 0008. Migration 0009 adds only indexes.

## 5. Health
`/api/v1/health` (components: db, storage, worker heartbeat, AI), `/api/v1/ready` (DB reachable + alembic revision; 503 otherwise), `/api/v1/metrics` (Prometheus).
