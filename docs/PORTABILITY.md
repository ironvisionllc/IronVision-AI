# Portability & Emergent dependency register

Goal: `git clone` → set `.env` → `alembic upgrade head` → `docker compose up` on any Docker host, with **no Emergent services in business logic**.

## Emergent dependencies (complete list)

| # | Dependency | Where | Used in business logic? | How to remove / replace |
|---|---|---|---|---|
| 1 | **Emergent universal-key AI adapter** (`emergentintegrations`, `EMERGENT_LLM_KEY`) | `backend/app/services/ai/adapters/emergent_adapter.py` + one `"emergent"` line in `ADAPTERS` (`app/services/ai/service.py`) | No – behind `AIService` | Set `AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` (or `openai_compatible` + base URL). Delete the adapter file and the dict entry. The package is **not** in `requirements.prod.txt`, so Docker images never contain it. |
| 2 | **Preview hosting** – Postgres now auto-starts: data lives in `/app/data/postgres`, and `backend/server.py` (preview entrypoint only) re-runs `scripts/pod_bootstrap.sh` in the background if the supervisor `postgres` program is missing after a pod restart (Kubernetes ingress `*.preview.emergentagent.com`, supervisor programs) | `/etc/supervisor/conf.d/*` (outside repo), `deploy/emergent-pod/aegis-supervisor.conf`, `scripts/pod_bootstrap.sh` | No | Replaced by `docker-compose.yml`. Delete `deploy/emergent-pod/` and `scripts/pod_bootstrap.sh`. |
| 3 | Preview-only frontend tooling: `@emergentbase/overlay`, `@emergentbase/visual-edits` devDependencies, `public/index.html` script tags (`assets.emergent.sh`, analytics), `craco.config.js` hooks, `frontend/plugins/` | `frontend/` | No | The frontend Dockerfile already strips the `@emergentbase/*` devDeps and swaps in `frontend/deploy/index.html` (no Emergent scripts). To clean the repo: `yarn remove @emergentbase/overlay @emergentbase/visual-edits`, replace `public/index.html` with `deploy/index.html`. craco tolerates their absence. |
| 4 | Emergent testing config `backend/pytest.ini` (xdist addopts for Emergent's test agent) | `backend/pytest.ini` | No | Project tests use `pytest -c pytest.aegis.ini`. Delete `pytest.ini` after migration. |
| 5 | Leftover template keys in `backend/.env` (`MONGO_URL`, `DB_NAME`, `TIGRIS_*`) | `backend/.env` (pod only) | **Not read by any code** | Delete. MongoDB is stopped in the pod and unused. |
| 6 | `backend/requirements.txt` is a full `pip freeze` of the pod venv (includes Emergent/LiteLLM wheels) | `backend/` | No | Docker uses curated `requirements.prod.txt`. Delete `requirements.txt` or regenerate from a clean venv. |

No Emergent auth, storage, database, queue, email or deploy services are used. Auth = `dev_password` (local bcrypt), storage = local/S3, DB = PostgreSQL, queue = PostgreSQL `jobs` table.

## Secrets hygiene before pushing to a new remote
`backend/.env` and `frontend/.env` exist in the pod and contain dev secrets (JWT secret, DB password, `SECRET_STORE_KEY`, Emergent key). They are now in `.gitignore` (with `/data/`, `backend/data/`); `git ls-files` shows they were never tracked, so `git rm --cached` was not needed. If an earlier remote ever contained them, purge with `git filter-repo --path backend/.env --invert-paths`.

## What was / was not executed (Phase 0)

| Item | Status |
|---|---|
| `alembic upgrade head` on empty PostgreSQL 16 (pod + fresh test DB) | **Executed – clean** |
| Content load via worker job (pinned, hash-verified) | **Executed** |
| pytest suite (33 tests: auth, RBAC 403/200, audit chain & append-only, catalog/CCI counts, storage local + S3 via moto) | **Executed – 33 passed** |
| AI health through `AIService` (`emergent` adapter, `claude-sonnet-5-5`) | **Executed – success** |
| `anthropic` and `openai_compatible` adapters | Code complete, **not executed** (no direct keys / endpoint in pod) |
| `s3` storage driver against real MinIO | **Not executed** (moto-mocked S3 round-trip passes; MinIO exercised only by `verify_portability.sh`) |
| `docker compose config -q` (Compose v2.29.7 binary, no daemon) | **Executed – valid** |
| hadolint on all three Dockerfiles | **Executed – no findings** (DL3008/DL3018/DL3007 pin warnings ignored) |
| `pip install -r requirements.prod.txt` in a clean venv (no emergentintegrations) + full pytest run from that venv | **Executed – install OK, 33 passed** |
| Production frontend build `yarn build` (REACT_APP_BACKEND_URL empty) | **Executed – OK** (in-pod; Docker-stage variant with `@emergentbase/*` stripped not executed) |
| `docker build` / `docker compose up` / `scripts/verify_portability.sh` | **NOT executed – Docker daemon unavailable in the pod.** Run on a developer machine. |

## Phase 1 verification (pod)

| Item | Status |
|---|---|
| `alembic upgrade 0001 -> 0002` on pod DB and on wiped test DB | **Executed – clean** |
| pytest 45 tests (Phase 0 + registration=287 moderate assignments, CCI-000366→CM-6 provenance, duplicate SHA + rescan dedup, KEV→RA-5 queue, unmapped justification + audit, system-scoped RBAC, role grant/revoke audit, freshness back-date, integrity tamper detection, RFC 5737 IP check) | **Executed – 45 passed** |
| Seed ingests 18 sample files through the real pipeline | **Executed** |
| `docker compose up` / `verify_portability.sh` with Phase 1 | **NOT executed – no Docker daemon in pod** |
| Mock connectors (AWS/Azure/pipeline/attestation) | **MOCK/DEMO only** – no real cloud APIs called |

## Phase 2 verification (pod)

| Item | Status |
|---|---|
| `alembic upgrade 0002 -> 0003` (poams, poam_findings/milestones/history, poam_match_rules, decision_rules, approval_requests/decisions, implementation AI fields) | **Executed – clean** (pod DB + wiped test DB) |
| pytest 54 tests (+ testing-agent suite 16, after `0004` widened `approval_decisions.decision_authority`) | **Executed – 54 passed; agent AI-review test re-run green** |
| Live AI draft via `AIService` (`emergent` adapter, `claude-sonnet-5-5`, prompt `control.implementation_statement@1.0.0`) | **Executed – 200, citations validated (~24 s)** |
| `verify_portability.sh` Phase 1/2 checks (LTP=291, POA&Ms, decision rules) | Added, **not executed** (no Docker daemon) |
| Emergent dependencies | Unchanged from the table above – AI drafts go through `AIService`; switch with `AI_PROVIDER=anthropic` or `openai_compatible` |

## Phase 5 status
| Item | Status |
|---|---|
| Backend tests (`pytest tests`) + acceptance AT-1..AT-12 in pod | **Executed – pass** (see TEST_RESULTS.md) |
| Backup → restore into scratch DB/storage | **Executed – RESTORE_VERIFY: PASS** |
| Security scans (pip-audit, bandit, yarn audit) | **Executed** – docs/security/. Trivy **not run** (no Docker) |
| Perf smoke (5,000 findings) | **Executed** – docs/PERFORMANCE.md |
| `docker compose` build/up, prod overlay, Keycloak/ClamAV/monitoring profiles | **Not executed** (no Docker daemon). YAML parsed only. |
| OIDC against a real IdP, ClamAV against live clamd, Vault live | **Not executed** – mocked tests only |
| GitHub Actions CI | **Not executed** |
| Emergent dependencies | Unchanged from the table above. None added in Phase 5. |
