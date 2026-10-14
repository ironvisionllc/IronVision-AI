# External validation checkpoint (run outside Emergent)

> DigitalOcean target: follow **[DIGITALOCEAN_DEPLOYMENT.md](DIGITALOCEAN_DEPLOYMENT.md)** and complete its §13 operator checklist. Run `scripts/check_env.py` and `scripts/verify_no_preview_deps.sh --docker` on the Droplet. Not yet executed on DigitalOcean.

This shows that IronVision AI runs on any machine with Docker: clone → `.env` → compose build/up → migrations → seed → login → STIG upload → POA&M → closure approval → leadership metric. No Emergent packages, keys or hosts are needed. **All data is SYNTHETIC.**

## Prerequisites

| Item | Requirement |
|---|---|
| OS | Linux, macOS, or Windows + WSL2 (x86_64 or arm64) |
| Docker | Docker Engine **24+** (or Docker Desktop 4.25+) with **Compose v2** (`docker compose version` ≥ 2.20) |
| RAM / disk | **≥ 6 GB RAM** free for Docker (the frontend build peaks at ~2–3 GB), **≥ 8 GB** disk |
| Free ports | **3000** (frontend/nginx), **8001** (API), **5432** (Postgres) (SeaweedFS S3 stays on the internal compose network – no host port) |
| Host tools | `git`, `bash`, `curl`, `python3` (used only by the verify script for JSON parsing) |
| Network | Needed for the first build only (Docker Hub images, PyPI, npm registry). No calls to emergent.sh / emergentagent.com |

## Commands

```bash
git clone <your-repo-url> aegisrmf && cd aegisrmf
./scripts/verify_portability.sh          # KEEP=0 ./scripts/verify_portability.sh  → tears down + deletes volumes at the end
```

The script does the following:
1. If `.env` is missing, it creates it from `.env.example` and generates the Postgres, S3 (app + admin), JWT and `SECRET_STORE_KEY` secrets.
2. Runs `docker compose config`, then `docker compose build` (backend, worker, frontend) and `docker compose up -d`.
3. Waits for the one-shot `migrate` service (`alembic upgrade head`, revisions 0001 to 0005) and checks that `alembic current` is at `(head)`.
4. Checks health (database, storage/SeaweedFS S3, worker heartbeat; AI is reported but optional).
5. Logs in the demo users, then checks the catalog (1196 controls / moderate 287), RBAC (ISSO → AO endpoint 403, audited) and the audit hash chain.
6. Runs the **E2E workflow via the API**: register a moderate system → upload `samples/e2e/e2e-web-01.ckl` (the worker ingests it) → V-900140 persisted as **CAT I** → create a POA&M from the finding → a duplicate attempt returns **409** → upload `e2e-web-01_remediated.ckl` → POA&M becomes **closure_eligible** (not closed) → ISSO requests closure with evidence → ISSO self-approval returns **403** (audited) → ISSM approves → POA&M **closed** → the leadership open CAT I count drops.
7. Checks the seed (LTP = 291 controls, ≥ 7 POA&Ms, decision rules), the frontend on :3000 and nginx proxying `/api`.
8. Runs the backend pytest suite inside the backend container against a throwaway `aegisrmf_test` database.

## Expected output (abridged)

```
PASS  docker + compose v2 available
PASS  .env created from .env.example with generated secrets
PASS  images built
PASS  migrate service exited 0
PASS  alembic at head: 0005 (head)
PASS  health.database ok
PASS  health.storage ok
PASS  health.worker heartbeat fresh
PASS  catalog loaded: 1196 controls, 872 enh, moderate=287, ccis=5137, ...
PASS  ISSO -> AO endpoint = 403
PASS  registered moderate system <uuid>
PASS  STIG checklist ingested by worker (run <uuid>)
PASS  V-900140 persisted as CAT I
PASS  POA&M created from finding
PASS  duplicate POA&M blocked (409 → link to existing)
PASS  POA&M closure_eligible (not auto-closed)
PASS  requester self-approval = 403 (audited)
PASS  ISSM approved closure
PASS  POA&M closed
PASS  leadership open CAT I dropped 1 → 0
PASS  frontend serves index.html on :3000
PASS  pytest suite
================ SUMMARY ================
...
OVERALL: PASS
```

Then open http://localhost:3000 and log in as `isso@aegisrmf.demo` (dev password in `.env` `DEMO_USER_PASSWORD`; development authentication only, not CAC/PIV). The README "Phase 2 demo script" walks through the same flow in the UI.

## AI (optional)

AI is **off by default** (`AI_PROVIDER=none`). Every non-AI step passes without it, and the script prints `SKIP AI health`. To use your own Anthropic key, set the following in `.env`:

```
AI_PROVIDER=anthropic
AI_MODEL=<an Anthropic model id available to your key, e.g. claude-sonnet-4-5>
ANTHROPIC_API_KEY=sk-ant-...
```

Then run `docker compose up -d backend worker`. The script's AI step calls `/api/v1/ai/health` through `AIService`. In the UI, go to Controls → CM-6 → **Generate draft**. Any OpenAI-compatible endpoint also works: `AI_PROVIDER=openai_compatible`, `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY`, `AI_MODEL`. The `emergent` adapter is preview-only and not used here.

## Self-contained frontend build

`frontend/Dockerfile` removes the preview-only `@emergentbase/*` devDependencies from `package.json` before `yarn install`. `craco.config.js` turns those dev-server plugins off when they are absent, and `deploy/index.html` replaces the preview `public/index.html`. The production bundle is static and served by `nginx-unprivileged`, which proxies `/api` to the backend.

## Troubleshooting

- A port is in use: stop the conflicting service, or change the host port mappings in `docker-compose.yml`.
- The frontend build is OOM-killed: give Docker ≥ 6 GB RAM.
- `migrate` did not complete: `docker compose logs migrate`.
- The worker heartbeat is stale: `docker compose logs worker`.

## Phase 3 checks (added to `scripts/verify_portability.sh`)
- Alembic head `0006_phase3_rmf_workflow_modules` is applied by the `migrate` service.
- PASS lines expected: inheritance cards reconcile + attestations seeded · policy library seeded (14) · policy upload analyzed by worker · AC-2(3) 35 vs 90 day discrepancy proposed · non-AO authorization decision denied · authorization denial audited · RMF workflow stages derived · global search.
- Policy analysis runs in the separate `worker` container (job `policy.analyze`). With no AI provider configured, the deterministic extractor still produces the parameter comparison. AI proposals only appear when a provider is configured and the `policy_audit` use case is enabled in Admin.
- New Python dependencies: `pypdf`, `python-docx`, `reportlab` (sample generation) and `lxml`. They are installed from `backend/requirements.txt` by the backend Dockerfile.

## Phase 4 checks (added to `scripts/verify_portability.sh`)
- Alembic head `0007` (`0007_phase4_advanced_automation`).
- Expected PASS lines: STIG V1R1 installed / V1R2 available · STIG diff 6/3/11/2 · impact preview shows P-0027 CAT II -> CAT I · OSCAL poam / ssp / assessment-results schema-valid (NIST v1.2.2 schema) · eMASS mode reported (MOCK) · scheduled jobs visible with next run.
- Pinned files baked into the backend and worker images (`backend/content/`): `stig/demo-linux-server/V1R*.json` (synthetic), `oscal-schemas/v1.2.2/*.json` (official NIST), and `kev/known_exploited_vulnerabilities.json` (official CISA). All are SHA-256-verified at load, and a hash mismatch refuses to load.
- New Python dependencies: `jsonschema` and `regex` (OSCAL validation). They are already in `requirements.prod.txt`.
- Worker env: `SCHEDULER_TICK_SECONDS` (default 30). Schedules are stored in the DB and editable in Admin.
- No Emergent-specific dependency was added. The `mapping.suggest` AI use case uses the configured provider (`AI_PROVIDER`). Without one, the endpoint returns 503 and everything else works.

## Phase 5 checks (added to `scripts/verify_portability.sh`)
- Alembic head `0009` (`0008_phase5_hardening`, `0009_phase5_perf_indexes`).
- Expected PASS lines: security headers (CSP, nosniff, DENY, no-referrer, Permissions-Policy) · `/ready` · `/metrics` · auth provider info · disallowed upload rejected · acceptance AT-1..AT-12 inside the backend container.
- Production overlay: `docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q` (needs `OIDC_*`, `FRONTEND_URL`, `CORS_ORIGINS`, `SECRET_STORE_KEY`). TLS certificate placeholder: `deploy/tls/tls.crt|tls.key`.
- Optional profiles: `--profile keycloak` (realm `deploy/keycloak/aegisrmf-realm.json`), `--profile clamav`, `--profile monitoring` (Prometheus + Grafana dashboard). **None of these were run in the build pod (no Docker).**
- Backup/restore: `scripts/backup.sh` → `scripts/restore.sh <dir>` into an empty DB. Expect `RESTORE_VERIFY: PASS`. Needs `pg_dump`/`pg_restore` 16 on the host running the scripts (or `PG_BIN`).
- CI: `.github/workflows/ci.yml` (backend tests + acceptance on postgres:16, pip-audit, bandit, tsc, build, yarn audit critical, compose build, Trivy). It has **not** been executed. Run it by pushing to GitHub.
- New Python dependencies: `defusedxml`, `hvac`, `prometheus_client` (in `requirements.prod.txt`).
- Emergent dependencies: unchanged (see PORTABILITY.md). No new ones added.
