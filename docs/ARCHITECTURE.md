# Architecture

```
 Browser ──▶ edge nginx (TLS, prod) ──▶ frontend nginx (static React/TS bundle, /api proxy)
                                   └──▶ backend  FastAPI (uvicorn)  /api/v1/*
                                            │  SQLAlchemy 2 / Alembic
                                            ▼
                     PostgreSQL 16  ◀── worker (separate process: jobs table queue + scheduler)
                                            │
                     Object storage (local FS | S3: SeaweedFS / AWS S3 / DO Spaces) – immutable, SHA-256 addressed evidence
 Optional: OIDC IdP (Keycloak profile) · clamd · Prometheus/Grafana · Vault · AI provider (anthropic | openai_compatible)
```

## Components
| Component | Path | Responsibility |
|---|---|---|
| API | `backend/app/api/v1/*` | REST endpoints, RBAC (`authz.py`), validation |
| Domain services | `backend/app/services/*` | ingestion/normalization, dedup, mapping, control evaluation, POA&M, reviews, inheritance, policy auditor, risk scoring, content updates, KEV, OSCAL, eMASS, retention, secrets, upload security |
| Security | `backend/app/security/*` | auth providers, sessions, OIDC/mTLS, login guard, web middleware |
| Worker | `backend/app/worker/*` | `SELECT … FOR UPDATE SKIP LOCKED` job queue, handlers, DB-stored schedules, heartbeat |
| Content | `backend/content/` | pinned NIST 800-53 r5, CCI, OSCAL schemas, CISA KEV, synthetic STIG releases. SHA-256 verified at load. |
| Frontend | `frontend/src` | React + TypeScript, page per RMF module |

## Data principles
- Evidence is immutable and content-addressed. Observations are append-only. Canonical findings are deduplicated by rule, asset, and source.
- Every state change goes through a service that writes a hash-chained `audit_events` row.
- Content versions are pinned per observation and assessment. An update never rewrites history (see CONTENT_UPDATES.md).
- AI output is always a *draft* with validated citations and needs a human approval.
- Multi-tenant: every record carries `org_id`. Queries are scoped by the caller's org and system role assignments.

## Migrations
`backend/alembic/versions/0001 … 0009`. One revision per schema change. See MIGRATION_PROCEDURE.md.
