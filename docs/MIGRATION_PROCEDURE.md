# Schema migration procedure

Every schema change is an Alembic revision in `backend/alembic/versions/` (current head **0009**).

## Authoring
1. Change `backend/app/models.py`.
2. `cd backend && alembic revision --autogenerate -m "<phase/purpose>"`. Rename the file to `NNNN_<slug>.py` and set `revision = "NNNN"`, `down_revision = "<previous>"`.
3. Review the generated operations. Autogenerate misses data migrations, server defaults, enum changes and partial indexes. Write `downgrade()`.
4. `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` on a scratch DB, then `make test`.

## Release
1. Back up: `scripts/backup.sh backups/pre-<rev>` (the manifest records the current revision).
2. Deploy: the one-shot `migrate` service runs `alembic upgrade head` before backend and worker start. Both depend on `service_completed_successfully`.
3. Verify: `/api/v1/ready` shows the new revision.
4. Roll back: `alembic downgrade <prev>` if the revision is reversible. Otherwise run `scripts/restore.sh backups/pre-<rev>` into a fresh database and repoint `DATABASE_URL`.

## Rules
- Never edit an applied revision. Add a new one.
- Large index builds on big tables: use `op.create_index(..., postgresql_concurrently=True)` inside `with op.get_context().autocommit_block()`.
- Do not mix reference-data seeding with DDL. Seeding is idempotent in `app.seed`.

## History
| Rev | Purpose |
|---|---|
| 0001 | Phase 0 initial schema |
| 0002 | Phase 1 core records + ingestion |
| 0003 | Phase 2 POA&M, reviews, AI drafts |
| 0004 | widen decision authority |
| 0005 | CAT rules |
| 0006 | Phase 3 RMF workflow modules |
| 0007 | Phase 4 advanced automation |
| 0008 | Phase 5 hardening (sessions, login attempts, retention, scan status, identity links) |
| 0009 | Phase 5 performance indexes (from perf smoke hot paths) |
