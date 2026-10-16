# IronVision AI

> **Deploying to DigitalOcean?** Start with **[docs/DIGITALOCEAN_DEPLOYMENT.md](docs/DIGITALOCEAN_DEPLOYMENT.md)** (documentation only – not yet executed on DigitalOcean). In the app, all handover docs are under **Handover Docs** (`/docs-center`).

**Intelligent Risk. Continuous Assurance.** — an RMF automation / compliance workbench for federal ISSO, ISSM, SCA and AO users.

> **SYNTHETIC DEMONSTRATION DATA – NOT FOR CUI/CLASSIFIED/OPERATIONAL DATA.**
> Authentication in this build is **DEVELOPMENT AUTHENTICATION – SIMULATED, NOT CAC/PIV**.

Current status: **Phase 5 complete + IronVision Design System** (light/dark themes). Internal codename: **aegisrmf** – Python package names, DB name (`aegisrmf`), env var names, compose service names, storage keys and demo emails (`@aegisrmf.demo`) intentionally keep the codename to avoid breakage. All user-visible branding is **IronVision AI**.

---

## Architecture

```
┌────────────┐  REST /api/v1  ┌──────────────────┐   SQL    ┌──────────────┐
│  frontend  │ ─────────────▶ │  backend (API)   │ ───────▶ │ PostgreSQL 16│
│ React + TS │                │  FastAPI         │          │  + Alembic   │
│ nginx (prod)│               │                  │          └──────▲───────┘
└────────────┘                │  AuthProvider ───┼─ dev_password    │ jobs table
                              │  RBAC layer      │  (oidc/cac later)│ (FOR UPDATE
                              │  AIService ──────┼─ anthropic |     │  SKIP LOCKED)
                              │                  │  openai_compat | │
                              │                  │  emergent(dev)   │
                              │  StorageService ─┼─ local | s3 ─────┼──▶ SeaweedFS / S3 / Spaces
                              └──────────────────┘                  │
                              ┌──────────────────┐                  │
                              │ worker           │ ─────────────────┘
                              │ python -m worker.main (heartbeat + job handlers)
                              └──────────────────┘
```

| Concern | Implementation | Where |
|---|---|---|
| API | FastAPI, versioned `/api/v1/...`, OpenAPI at `/api/openapi.json`, Swagger at `/api/docs` | `backend/app/main.py`, `backend/app/api/v1/` |
| DB | PostgreSQL 16, SQLAlchemy 2.x, Alembic (plain DDL + one plpgsql trigger) | `backend/app/models.py`, `backend/alembic/` |
| Worker | Postgres-backed queue (`jobs`), `FOR UPDATE SKIP LOCKED`, heartbeats in `worker_heartbeats` | `backend/worker/` |
| Auth | `AuthProvider` interface → `dev_password` (bcrypt) → app JWT (HS256). Identities in `auth_identities(provider, subject)` | `backend/app/security/providers/` |
| RBAC | Role assignments (org/system scope) in DB; permission matrix in code; `require_permission("perm")` dependency | `backend/app/security/rbac.py`, `deps.py` |
| Audit | Append-only `audit_events` (DB trigger blocks UPDATE/DELETE), SHA-256 hash chain (`prev_hash`→`hash`) | `backend/app/services/audit.py` |
| AI | `AIService` + versioned prompts + Pydantic output validation; every call logged to `ai_interactions` | `backend/app/services/ai/` |
| Storage | `StorageService` with `local` and `s3` drivers (`STORAGE_DRIVER`) | `backend/app/services/storage/` |
| Reference content | Pinned + vendored OSCAL / CCI files with SHA-256 verification | `backend/content/`, `backend/app/services/content/` |
| Logging | Structured JSON logs with `X-Correlation-ID` propagation | `backend/app/logging_setup.py` |

### Repository layout

```
backend/
  app/            api/v1, security (providers, rbac), services (ai, storage, content, audit, jobs), models, schemas, seed
  alembic/        migrations (0001 = Phase 0 schema)
  worker/         worker entrypoint + job handlers
  content/        manifest.json + vendored NIST OSCAL v1.5.0 files + DISA U_CCI_List
  tests/          pytest suite (auth, RBAC, catalog counts, storage, audit chain)
  Dockerfile, Dockerfile.worker, requirements.prod.txt, .env.example
frontend/
  src/            React + TypeScript (pages, components, context, lib)
  deploy/         nginx.conf + clean index.html used by the Docker build
  Dockerfile, .env.example
docker-compose.yml, .env.example
scripts/verify_portability.sh   end-to-end compose verification (run on a Docker host)
scripts/pod_bootstrap.sh        Emergent preview pod only
docs/PORTABILITY.md
```

## Reference content (pinned)

| Content | Pin | SHA-256 |
|---|---|---|
| NIST SP 800-53 Rev 5 catalog (OSCAL, 5.2.0) | `usnistgov/oscal-content` tag **v1.5.0**, commit `78650f02ad9321bb7b817846f8fbd4f2bcd620de` | `01f37cf90ea99d92242c936cbfbdebcc338eef1f71454e2acac36cc56e9bc062` |
| LOW baseline profile | same | `8fd206017c8d718b44bdef612c2ff321a9fd84d97a515c8ec33c4619accbef6e` |
| MODERATE baseline profile | same | `9030dbf1f13169947eb97eb101b4bd2f00d3c151b100455a923ac75803f00ea1` |
| HIGH baseline profile | same | `60576970caef91b2cba56d46e5948b72e3b879434fc2a4840bc4179e5e75cfd7` |
| PRIVACY baseline profile | same | `7e650c4397ad633eadeaf510baa523372849b1fa3e18207b6c6b70ed456224f9` |
| DISA CCI List (version 2025-01-23) | `https://dl.dod.cyber.mil/wp-content/uploads/stigs/zip/U_CCI_List.zip` (zip `077cbb6d…2700`) | XML `a9e3850f7f30665170c377839abea2fd94863019e434cb27b3f6b2d5e277f403` |

Loaded counts: **1,196** controls (324 base + 872 enhancements; 182 withdrawn), **3,715** SP 800-53A objectives,
baselines Low **149** / Moderate **287** / High **370** / Privacy **96**, **5,137** CCIs, **3,838** CCI→Rev5 mappings (all resolved to catalog controls, `review_status=source_asserted`).

The loader (`content.load_reference` job) verifies each vendored file's SHA-256 against `content/manifest.json` before loading, archives the raw file to object storage, and records URL/tag/commit/hash/effective date in `catalog_versions`. Set `CONTENT_FETCH_REMOTE=true` to re-download from the pinned URLs instead (hash must still match). Re-running is idempotent.

## Local development (without Docker)

Prereqs: Python 3.11, Node 20 + Yarn 1.x, PostgreSQL 16.

```bash
# database
createuser aegis -P && createdb -O aegis aegisrmf && createdb -O aegis aegisrmf_test

# backend
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.prod.txt
cp env.template .env            # edit DATABASE_URL, JWT_SECRET, AI settings
alembic upgrade head
python -m app.seed              # demo org + 8 users + enqueues content load
uvicorn app.main:app --port 8001 --reload
python -m worker.main           # in a second terminal (performs the content load)

# tests (wipes TEST_DATABASE_URL)
python -m pytest -c pytest.aegis.ini -q

# frontend
cd ../frontend
cp env.template .env            # REACT_APP_BACKEND_URL=http://localhost:8001
yarn install && yarn start
```

## Quick deploy (DigitalOcean Droplet)
```bash
cd /opt/ironvision/IronVision-AI
mv deploy.sh deploy.sh.old 2>/dev/null || true    # an old untracked deploy.sh would block the pull
git pull
./deploy.sh --apply-demo-settings                 # dry run: shows the before/after diff of the demo keys, writes nothing
./deploy.sh --apply-demo-settings --yes           # writes them in place (backup, mode 600, secrets untouched), then deploys
# later deploys: ./deploy.sh   (TLS certificate is obtained/renewed automatically)
```
`--apply-demo-settings` sets only the non-secret demo.ironvisionai.com keys (`APP_DOMAIN`, `FRONTEND_URL`, `CORS_ORIGINS`,
`LETSENCRYPT_EMAIL`, `OIDC_*` URLs, `AUTH_DOMAIN`, `OIDC_CLIENT_ID=ironvision-app`, `ALLOW_DEMO_LOGIN=true`,
`KEYCLOAK_ALLOW_REGISTRATION=true`, `DEPLOYMENT_KIND=demo`, `ALLOW_SIGNUP=false`, `SEED_DEMO_DATA=false`, `APP_ENV=production`,
`OPENROUTER_SITE_URL`). `OIDC_CLIENT_ID` is changed only after the live Keycloak realm confirms client `ironvision-app` exists;
otherwise it is kept and the fix (`./deploy.sh --apply-realm`) plus the realm's client list are printed. Standalone:
`python3 scripts/apply_demo_settings.py deploy/digitalocean/.env.production [--dry-run|--yes]`. New installs: the demo template
`deploy/digitalocean/env.production.template` already carries these values (customer production: `env.customer-production.template`).
Before the first run: DNS A record `demo.ironvisionai.com` → Droplet IPv4 (AAAA if IPv6), optional CAA `0 issue "letsencrypt.org"`, DO firewall 80/443 open. If OIDC values are still placeholders, the first run creates the env file and lists what to fill. Details: `docs/DIGITALOCEAN_DEPLOYMENT.md` §0 (Quick deploy) and §4 (TLS). The env file lives only on the Droplet; it is git-ignored and never committed.

## Docker Compose

```bash
cp env.template .env      # set real secrets; AI_PROVIDER=openrouter + OPENAI_COMPAT_API_KEY + AI_MODEL to enable AI
docker compose up -d --build
# requirements: backend/requirements.prod.txt is enforced by python3 scripts/check_requirements.py
# DigitalOcean / production: scripts/deploy.sh deploy/digitalocean/.env.production  (fail-fast, see docs/DIGITALOCEAN_DEPLOYMENT.md §0)
# Keycloak sign-in: ./deploy.sh --set-auth-domain auth.demo.ironvisionai.com  → docs/KEYCLOAK.md (migration is a separate dry-run-first step)
# services: postgres, seaweedfs (profile seaweedfs, S3 on the internal network) + objectstore-init (bucket bootstrap, our backend image), migrate (alembic upgrade head + seed, one-shot), backend :8001, worker, frontend :3000
./scripts/verify_portability.sh   # builds, boots, waits for health, checks login/RBAC/catalog/tests, prints PASS/FAIL
```

## Environment variables

| Variable | Used by | Description |
|---|---|---|
| `DATABASE_URL` | backend, worker | `postgresql+psycopg://user:pass@host:5432/db` (required) |
| `TEST_DATABASE_URL` | tests | Disposable database, wiped by pytest |
| `JWT_SECRET`, `JWT_TTL_MINUTES` | backend | App session token signing / lifetime |
| `AUTH_PROVIDER` | backend | `dev_password` (only provider in Phase 0) |
| `SEED_DEMO_DATA`, `DEMO_PASSWORD` | backend, migrate | Idempotent synthetic seed: demo@ironvision.ai + its private sandbox |
| `ALLOW_SIGNUP`, `SANDBOX_INACTIVITY_DAYS` | backend, worker | Public self sign-up (false in production) and sandbox inactivity purge |
| `DEMO_USER_PASSWORD` | tests | Password of the pytest/acceptance fixture role users |
| `CORS_ORIGINS` | backend | Comma-separated browser origins |
| `STORAGE_DRIVER` | backend, worker | `local` or `s3` (required) |
| `STORAGE_LOCAL_ROOT` | local driver | Filesystem root |
| `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_REGION`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | s3 driver | SeaweedFS (bundled, `COMPOSE_PROFILES=seaweedfs`) / AWS S3 / DO Spaces / Garage / Ceph RGW. `S3_ADDRESSING_STYLE` = path (self-hosted) or virtual (Spaces/AWS). MinIO was removed – its community images are no longer published |
| `AI_PROVIDER` | backend | `openrouter` (recommended: one key, any model), `anthropic`, `openai_compatible`, `emergent` (dev only), `none` |
| `AI_MODEL`, `AI_TIMEOUT_SECONDS`, `AI_TEMPERATURE` | backend | Any model slug passed verbatim (OpenRouter: `openai/gpt-4o`, `anthropic/claude-3.5-sonnet`, …), timeout, temperature. Admin page can override the model |
| `AI_MODEL_DRAFTING`, `AI_MODEL_POLICY`, `AI_MODEL_MAPPING`, `AI_MODEL_SUMMARY` | backend | Optional per-use-case models (fall back to `AI_MODEL`) |
| `ANTHROPIC_API_KEY` | anthropic adapter | Direct Anthropic API key |
| `OPENAI_COMPAT_BASE_URL`, `OPENAI_COMPAT_API_KEY` | openrouter / openai_compatible | The only key for OpenRouter (base URL defaults to `https://openrouter.ai/api/v1`); self-hosted / gateway endpoint otherwise |
| `OPENROUTER_SITE_URL`, `OPENROUTER_APP_NAME` | openrouter | Optional `HTTP-Referer` / `X-Title` attribution headers |
| `EMERGENT_LLM_KEY`, `EMERGENT_AI_VENDOR` | emergent adapter | Emergent preview only |
| `CONTENT_DIR`, `CONTENT_FETCH_REMOTE` | worker | Vendored content dir; remote re-fetch toggle |
| `WORKER_ID`, `WORKER_POLL_SECONDS`, `WORKER_HEARTBEAT_STALE_SECONDS` | worker / health | Worker tuning |
| `LOG_LEVEL`, `APP_ENV` | all | Logging / environment label |
| `REACT_APP_BACKEND_URL` | frontend (build time) | API origin; empty = same-origin `/api` |

## Migrations

```bash
cd backend
alembic upgrade head                                  # apply
alembic revision --autogenerate -m "describe change"  # new migration after editing app/models.py
alembic downgrade -1                                  # roll back one
```
`0001_phase0_initial_schema` creates: organizations, users, auth_identities, login_attempts, role_assignments, systems, assets, catalog_versions, controls, control_objectives, baselines, baseline_controls, ccis, cci_control_map, audit_events (+ append-only trigger), ai_interactions, jobs, worker_heartbeats, notifications. Every table has a UUID `id` (`gen_random_uuid()`, core PG13+), `created_at`, `updated_at`; reference/business tables carry `source` + `provenance` JSONB.

## Demo account, sign-up and sandboxes (synthetic)

- **One shared demo account:** `demo@ironvision.ai`. The password comes from `DEMO_PASSWORD`; the preview default is listed only in `memory/test_credentials.md` and is not shown on the login page.
  - **"Explore the demo – no sign-up"** on the login page opens it in one click via `POST /api/v1/auth/demo-login` – the server issues a normal session; no password is sent from or shipped in the browser. Gated by `ALLOW_DEMO_LOGIN` (preview/staging only; production refuses it), rate-limited per client IP (`DEMO_LOGIN_RATE_LIMIT`), audited as `auth.demo_login`. It is a **shared** workspace that resets nightly; user management is disabled there.
- **Self sign-up** ("Create a free sandbox account", only when `ALLOW_SIGNUP=true`). Each new account gets a **private, CLEAN sandbox tenant**, "<org> Sandbox – SYNTHETIC": no systems or records, only reference content, default decision/CAT/match rules and personas. Only `demo@ironvision.ai` is seeded with the 4 synthetic systems. Sample STIG/ACAS/SCAP/SARIF files can be downloaded from the onboarding checklist (`GET /api/v1/sandbox/samples.zip`); nothing is auto-loaded.
- **Persona mode (sandbox tenants only):** in the header, "Acting as" switches between ISSO, ISSM, SCA, AO, System Owner, DevSecOps, Leadership and Admin personas.
  - Personas are separate synthetic identities, so requester ≠ decider and assessor ≠ implementer are still enforced.
  - Every audit event records `operated_by` = the real user.
  - **This is a demo feature and is not acceptable as production separation of duties.**
- **Sandbox lifecycle:**
  - Normal accounts: "Clear my workspace" deletes all their records (account and reference content kept; audited `sandbox.workspace_cleared`).
  - Demo account: "Reset demo data" re-seeds the 4 systems; it also resets nightly.
  - Sandboxes inactive for `SANDBOX_INACTIVITY_DAYS` (30) are purged, with warnings shown in the app.
- The 8 per-role accounts (`*@aegisrmf.demo`) now exist **only as pytest/acceptance fixtures** in the test database.

## Key API endpoints

| Method | Path | Permission |
|---|---|---|
| GET | `/api/v1/health` | public |
| GET | `/api/v1/auth/provider` | public (lists dev accounts only for simulated provider) |
| POST | `/api/v1/auth/login` / GET `/auth/me` / POST `/auth/logout` | — / bearer |
| GET | `/api/v1/controls`, `/controls/families`, `/controls/{id}` | `catalog.read` |
| GET | `/api/v1/content/versions`, `/content/stats` | `catalog.read` |
| GET | `/api/v1/systems` | `system.read` |
| POST | `/api/v1/authorization-decisions/test` | `authorization.decide` (AO only) |
| POST | `/api/v1/ai/health` | `admin.ai.test` |
| POST | `/api/v1/admin/content/load` | `admin.content.load` |
| GET | `/api/v1/jobs` | `admin.health.read` |
| GET | `/api/v1/audit-events`, `/audit-events/verify` | `audit.read` |
| GET | `/api/v1/rbac/matrix` | authenticated |

## Phase 1 – Core Records & Ingestion

- **Systems**: registration wizard (FIPS 199 high-water mark → baseline, overlays, tailoring with justification, common-control providers) generates `control_assignments` with origin + responsibility. Assets CRUD, system-scoped role grant/revoke (audited).
- **Four separate statuses** per assignment: `implementation_status`, `assessment_status` (SCA only, Phase 2+), `monitoring_status` (technical checks), `evidence_freshness_status`. System `authorization_status` is separate. Passing checks never set "compliant".
- **Ingestion** (worker job `ingest.process`): `.nessus`, ACAS CSV, `.ckl`, `.cklb`. Receive → validate → SHA-256 → immutable `StorageService` write → parse → asset match (unmatched assets flagged) → canonical `findings` keyed by versioned `dedup_rules` + one `finding_observations` row per scan → mapping → re-evaluate controls → queue → risk snapshot → audit. Identical bytes = `duplicate` run, nothing double-counted.
- **Mappings**: STIG rule CCIs → 800-53 via the pinned DISA CCI list (`mapping_source=stig_cci`, CCI content version/sha recorded). ACAS → controls only via `org_mapping_rules` (seeded synthetic rule v1: CVE findings → RA-5, SI-2). Anything else stays `unmapped` until an ISSO maps or dispositions it with a justification.
- **Evidence Ledger**: integrity re-verification job (`evidence.verify_integrity`), freshness evaluation (`evidence.evaluate_freshness`, scheduled by the worker), demo-only back-date tool (`demo.tools`, platform admin).
- **Connectors**: `file_import` adapters (STIG, ACAS) plus clearly labelled MOCK/DEMO adapters (AWS GovCloud, Azure Gov, DevSecOps pipeline, attestation, eMASS not configured). Credentials are encrypted server-side with `SECRET_STORE_KEY` (Fernet) and never returned.
- **Workbench** `/systems/:id/controls/:controlId`: explainable priority queue (weights in `priority_weights`), evidence, open findings with provenance, versioned narratives, comments, CCIs. **Leadership** `/portfolio`: live DB metrics + stored `risk_snapshots` (8 weeks of history are flagged `is_synthetic`).
- Samples: `samples/` (regenerate with `python scripts/generate_samples.py`; RFC 5737 IPs, `.demo` hosts). Seed ingests them through the real pipeline. Reset: Admin → Reset Demo Data.

| Method | Path | Permission |
|---|---|---|
| POST/GET/PATCH | `/api/v1/systems`, `/systems/{id}` | `system.register` / `system.read` / `system.write` |
| GET/POST/DELETE | `/api/v1/systems/{id}/roles` | `system.roles.manage` |
| GET/POST | `/api/v1/systems/{id}/sources`, `/sources/{id}/test`, `/sources/{id}/run` | `source.manage` |
| POST | `/api/v1/systems/{id}/uploads` (multipart `file`, `source_id`) | `ingest.upload` |
| GET | `/api/v1/systems/{id}/ingest-runs`, `/ingest-runs/{id}` | `system.read` |
| POST | `/api/v1/findings/{id}/map`, `/findings/{id}/disposition` | `finding.map` |
| GET/POST | `/api/v1/systems/{id}/evidence`, `/evidence/verify` | `system.read` / `evidence.verify` |
| GET/PUT | `/api/v1/systems/{id}/workbench/...` | `system.read` / `implementation.write` |
| GET | `/api/v1/dashboard/leadership` | `portfolio.read` (leadership_viewer, AO, ISSM) |
| POST | `/api/v1/admin/demo/reset`, `/demo/evidence/{id}/collected-at` | `demo.tools` |

Tests: `cd backend && pytest -c pytest.aegis.ini tests` (45 tests incl. `tests/test_phase1.py`).

## Phase 2 – End-to-End Workflow (POA&M · Reviews · AI implementation statements · Leadership)

- **POA&M** (`/poams`, `/poams/:id`): `poams`, `poam_findings` (many findings → one POA&M), `poam_milestones`, `poam_history`. IDs `P-0001…` per tenant. Statuses: new, in_progress, overdue (derived from due date), closure_eligible, closure_review, risk_acceptance_review, closed, risk_accepted. eMASS state is `not_sent` (connector Phase 4).
- **Create from finding**: "Add to POA&M" on workbench / ingest-run / finding pages. The versioned `poam_match_rules` table (v1: same STIG rule / ACAS plugin / CVE **and** overlapping control, across assets) is checked first; a match returns `409` + "Link to existing P-00xx". Overriding requires a justification. Rescans never create POA&Ms.
- **Remediation detection**: a rescan that shows a linked finding as NotAFinding, or no longer reports it for an asset that the rescan covered, marks the finding `remediated_observed` and its POA&M `closure_eligible`, then notifies the owner. Nothing is ever closed automatically.
- **Reviews** (`/reviews`, `/reviews/:id`): `approval_requests`, `approval_decisions`, versioned per-tenant `decision_rules` (seeded: FP → ISSM; closure → ISSM; waiver/extension and risk acceptance → ISSM endorses then AO decides; implementation review → ISSM; assessment → SCA). The backend enforces the rule role and system scope. The requester cannot decide their own request. A rationale of at least 10 characters is required. Each decision records the user, timestamp, decision authority and rule version, and is audited. Effects are transactional and idempotent: a second decision gets `409`.
- **AI implementation statement**: `POST /systems/{id}/workbench/controls/{cid}/ai-draft` uses `AIService` with prompt `control.implementation_statement@1.0.0` and Pydantic-validated output (narrative, citations, verified_facts, interpretation, suggested_actions, missing_information). Grounding is assembled server-side. Citations to evidence that is not in context are stripped. Drafts are saved as versions with `ai_generated` and `prompt_version`; review is requested via an approval request. When linked evidence changes, the version is flagged `needs_reconsideration`. Nothing is auto-approved, and eMASS submit is disabled.
- **Freshness (per-asset coverage rule)**: for each control, the newest evidence per covered asset counts (asset-less sources count per source). All covered assets fresh → `current`; all stale → `expired`; mixed → `partially_stale`, which adds the queue reason "expired evidence on N of M assets". Leadership freshness = % of controls with evidence whose freshness is current/near-expiration. Uploads are `integrity=hash_recorded` (SHA-256 at receipt; `verified` after a re-hash job) and `signature=unsigned`. Both are shown separately, and freshness is `current` inside the window. `unverified` is used only when integrity could not be established.
- **Source cards**: Total / Open / Mapped / Unmapped, computed from canonical findings (Mapped + Unmapped = Total). Uploads without a source are auto-attributed to the system's STIG/ACAS file-import source, which is created if missing.
- **Leadership**: cards, "Waiting on your decision", and the system table sorted by the **operational prioritization score** (weights in `priority_weights` `sys_*`; breakdown shown; *not a formal residual risk determination*). The trend comes from `risk_snapshots`, which are written after every workflow event.
- **Notifications**: header bell for assignment, closure_eligible, pending_review, returned/rejected and approved events, with acknowledge and deep link.
- Deep links: `/poams/:id`, `/reviews/:id`, `/findings/:id`, `/systems/:id/controls/:controlId`.

### Phase 2 demo script (password for all: see `memory/test_credentials.md`)
E2E sample files: `samples/e2e/` (regenerate: `python scripts/generate_e2e_samples.py`).

1. Sign in as `demo@ironvision.ai` (or create an account), switch **Acting as → ISSM** → Systems → Register system → name "E2E Demo", moderate → Register (287 controls).
2. **Acting as → ISSO** → select "E2E Demo" in sidebar → Evidence Sources → Upload `e2e-web-01.ckl`, then `e2e_scan.nessus`. The STIG/ACAS source cards appear automatically. Open the ingest run (the host is flagged as an unmatched asset because it is not in inventory yet).
3. Controls → queue: CM-6 / RA-5 / SC-13 now have failing checks. Open **SC-13** → Open findings → V-900140 → **Add to POA&M** → set due date → Create POA&M (P-0032).
4. Ingest run page → V-900140 → **Add to POA&M** again → the modal offers **Link to existing P-0032** (no duplicate).
5. Upload `e2e-web-01_remediated.ckl` → POA&M page shows **closure eligible** (banner; not closed) and the bell shows a notification.
6. POA&M → **Request closure** → tick the remediated checklist as closure evidence → submit (R-000x routed to ISSM). As ISSO, open the review: "You requested this; you cannot decide it."
7. Switch user → **ISSM** → Reviews → ISSM tab → open request → rationale → **Record approval (simulated signature – not CAC/PIV)**. The POA&M is Closed (actual completion = today), the finding's remediation is closed, and the control is re-evaluated.
8. **Acting as → Leadership** → Portfolio: CAT I and overdue counts reflect the closure; the trend gains a new live snapshot. Audit trail: Admin → Audit (platform admin).
9. KEV path: as ISSO on "E2E Demo", RA-5 → Log4Shell finding → Add to POA&M → Request risk acceptance → ISSM **Endorse** → **Acting as → AO** decides (an ISSO calling the AO step directly gets 403). Uploading `e2e_scan_remediated.nessus` makes it closure eligible → closure → ISSM approves.
10. AI: as ISSO on LTP → Controls → **CM-6** → Implementation statement → **Generate draft** (label "AI DRAFT – not reviewed", citations link to the ledger) → edit → **Save draft version** → **Request review** → ISSM approves in Reviews → it becomes the "Current approved" statement.

Tests: `pytest -c pytest.aegis.ini tests` → 54 tests (incl. `tests/test_phase2.py`: reconciliation, partial freshness, POA&M dedupe-link, closure flow + self-approval 403, ISSO cannot act as AO, false positive, AI citation stripping, cross-screen consistency).

### Phase 2 follow-ups
- **CAT derivation** (`cat_rules` table, versioned, per tenant): STIG CAT comes from the checklist's own severity (DISA: high/medium/low → CAT I/II/III). ACAS uses an **ORG RULE**: critical/high → CAT I, medium → CAT II, low → CAT III, info → none. CAT is stored on each finding at ingest; every CAT I count and display reads that stored value.
- Denied review decisions (self-approval, wrong role) write `authz.denied` audit events. When a POA&M becomes `closure_eligible`, a `poam.closure_eligible` event is written with actor `system` and the triggering ingest run and observation IDs.
- Author or decider display name and roles are returned on implementation versions, POA&M history, review decisions and the audit log.
- Saving an AI draft requires the `interaction_id` returned by `/ai-draft`; the saved version links to `ai_interactions`.
- External checkpoint: see `docs/EXTERNAL_VALIDATION.md`. `scripts/verify_portability.sh` now runs the full E2E flow through the API.

## Phase 3 – RMF Workflow Modules
Migration `0006_phase3_rmf_workflow_modules`. Seed `app/seed_phase3.py` is idempotent and synthetic. Sample policies are in `samples/policies/` (regenerate with `python scripts/generate_policy_samples.py`).

- **Inheritance & Attestations** (`/inheritance`). The cards count Fully inherited, Shared and System-owned. These categories are mutually exclusive and add up to the assigned total. Manual attestation is a separate, overlapping category. The page lists providers (package, basis, coverage, validation and expiration dates, evidence references) and has CRUD for them. For shared controls it shows provider and system responsibility side by side. The system's own part (monitoring, freshness, open findings) is computed only from this system's own records. A provider passing never satisfies it.
- **Attestations** have an owner, statement, required evidence, due date, a simulated signature (not CAC/PIV) and an expiry. Evidence uploads go to the ledger with SHA-256. Only the owner can attest. Renewing creates a new version, and earlier signed records are kept unchanged. "Send reminder" sends a notification.
- **Attestation expiry** happens through the worker job `attestations.evaluate` or on demand. Expiry marks the evidence expired, re-evaluates the control (queue reason, freshness), records a risk snapshot (leadership), notifies the owner and writes an audit event. Admin-only demo tool: `POST /demo/attestations/{id}/expire` (audited).
- **Reviews** have all request types, including `authorization_package_review` and assessment. Decision rules can be edited in Admin; each edit creates a new rule version. Each in-flight request keeps the rule version it started with.
- **SCA assessments** (Workbench → SCA assessment) record objectives (800-53A), methods (examine/interview/test), result and findings. This is the only path that sets `assessment_status`. **Independence check**: an SCA who authored the control's implementation statement, or who holds an ISSO/System Owner role on that system, gets `403` + `authz.denied`.
- **Authorization** (`/systems/:id/authorization`): the package contains the SSP summary, assessment results, open POA&Ms and risk acceptances. Submit → ISSM endorses → AO records ATO / ATO with conditions / IATT / DATO, with expiration, conditions and rationale. Only the AO can decide. Anyone else gets `403`, audited as `authz.denied`. The decision updates the system's authorization status and expiration.
- **Policy Auditor** (`/policy-auditor`). Accepts PDF/DOCX/TXT, stored through the ledger with SHA-256. Text is extracted with pypdf/python-docx. The worker job `policy.analyze` runs deterministic parameter extraction plus `AIService` (prompt `policy.audit@1.0.0`, Pydantic-validated) when the `policy_audit` AI use case is enabled. Values are checked against the catalog, and invalid control IDs are dropped.
  - The page shows the policy value, the approved ODP and the observed value with its source.
  - Finding types: policy_vs_config_difference, odp_not_met, missing_policy_requirement, possible_outdated_reference (Rev 4 references), ai_suggested_needs_validation.
  - Every finding starts as `proposed`. You can Confirm it (this creates a canonical finding mapped to the control; then Add to POA&M), Dismiss it (a justification is required and kept), Request review, or Link it to a control.
  - The parameter comparison exports as CSV. There is no universal ODP threshold: ODPs are organization-defined per system.
- **Notifications**: in-app alerts with per-user preferences (`/settings/notifications`). Email is an adapter interface, **disabled** in this build. The worker job `notifications.deadlines` (POA&M due ≤7d, attestation due ≤14d, ATO expiration ≤90d) is idempotent per (user, kind, entity, day).
- **Global search** (header) uses server-side ILIKE over systems, controls, findings, POA&Ms, reviews, policies and evidence. Results are filtered by the caller's system-scoped RBAC.
- **Audit log** (`/audit-log`): server-side filters (actor, action prefix, entity, outcome, date range), pagination, CSV/JSON export and a hash-chain verification banner.
- **Admin**:
  - Users can be invited with a DEV temporary password (shown once). Each user has an access history. System roles are assigned and revoked on each System page.
  - A truthful security panel shows the real session timeout from env, dev-only sign-in, the banner, tenant separation and secret handling.
  - AI administration settings are stored in the DB and enforced by `AIService`: a disabled use case returns `403`. Human approval is always required (locked).

### RMF workflow derivation rules (`/rmf-workflow`)
| Stage | Completed when | In progress / needs attention |
|---|---|---|
| Prepare | ISSO, System Owner and AO system roles are assigned | some roles assigned / none |
| Categorize | FIPS 199 C/I/A all set | – / missing |
| Select | ≥1 control assigned | – / none |
| Implement | every assigned control has an implementation statement | ≥1 / none |
| Assess | every control has an SCA assessment result | ≥1 / none |
| Authorize | status "Authorized…" and expiration in the future | – / otherwise |
| Monitor | enabled sources all healthy and evidence fresh ≥80% | sources exist / *not configured* when no source |
Ongoing cards: POA&M (overdue = 0), Attestations (overdue = 0), Reviews (pending = 0), Policy audit (proposed = 0).

### Phase 3 demo script
1. **ISSO** → Inheritance (LTP): cards reconcile. CP-4 is overdue and AT-2 is due in about 12 days. CM-6/AC-2/SC-28 show provider vs system responsibility.
2. **System Owner** → AT-2 → Upload evidence → Attest (the simulated signature is recorded). Platform admin → "Demo: expire" → the control shows expired evidence and the owner gets a notification.
3. **ISSO** → Policy Auditor → upload `samples/policies/access_control_policy.pdf` → open it. The page shows AC-2(3) as policy 35 days vs observed 90 days (Mismatch), the Rev 4 reference and the missing remote-access section. **Confirm** the AC-2(3) proposal, which creates a finding → Add to POA&M. Dismissing a proposal requires a justification.
4. **SCA** → Workbench → AC-2 → SCA assessment → record the result. This is denied if the SCA wrote the statement.
5. **System Owner/ISSO** → System → Authorization package → Submit. **ISSM** endorses in Reviews. **AO** → Authorization page → ATO with conditions. An ISSM calling the decision endpoint gets 403 (audited).
6. RMF Workflow shows the live stages. The header search finds "ac-2" or POA&M IDs. Audit log → filter `authz` → export CSV.

Tests: `pytest -c pytest.aegis.ini tests` → 65 tests (`tests/test_phase3.py`: expiry cascade, SCA independence, AO-only decision + denials audited, 35-vs-90 confirm, dismissal justification, search RBAC, workflow derivation, notification idempotency, AI use-case enforcement, audit filters/export).

## Phase 4 – Advanced Automation
Migration `0007_phase4_advanced_automation`. The seed (`app/seed_phase4.py`) is idempotent, and **Reset Demo** brings back the same state.

### Part A fixes
- A POA&M prefilled from a finding takes its source label from the finding's actual source (`workflow.source_label`), e.g. "Policy audit".
- Global search sends the selected system. Control hits resolve to that system; otherwise there is one hit per visible system, labelled `· ACR` and grouped.
- Decision lists include a `decider` object (name, roles).
- **Statement rule.** One definition (`evaluation.statement_map`, `STATEMENT_RULE`) is shared by the ISSO queue and the RMF *Implement* stage. A control has a statement when it has an approved version, or its current non-blank version is in review. Blank or unsubmitted drafts count as missing. Inherited controls are exempt.
- LTP inheritance seed: Cloud FedRAMP High package 41 inherited / 38 shared, Enterprise identity 12 / 6, Enterprise SecOps 8 / 0. That gives **61 / 44 / 186 of 291**, plus **38 manual attestations** (all synthetic; metrics stay computed).

### Versioned content and update impact
- **STIG content.** `scripts/generate_stig_content.py` writes the synthetic **Demo OS STIG** V1R1 (July, installed) and V1R2 (October, available) into `content/stig/` in the `aegisrmf-stig-json/1` format. Both are SHA-256-pinned in `manifest.json`. V1R2 adds 6 rules, removes 3, changes 11 requirements and changes 2 severities. V-900118, the rule behind **P-0027**, goes from CAT II to CAT I.
- **Content Updates panel** (Evidence Ledger) lists installed vs available versions for DISA STIGs, the NIST catalog, baselines, the CCI list, overlays, KEV, threat intel, SCAP and EPSS. Types with nothing loaded say so.
- **Preview** shows a rule-by-rule diff and the impact before anything changes: assets that need a new checklist, affected controls, findings and POA&Ms.
- **Apply** needs `content.apply` (ISSM or platform admin) and a justification. It:
  - activates the new version and supersedes the old one;
  - updates the current CAT and content version on findings;
  - versions mappings (`valid_to`, `superseded_by_version_id`) where CCIs changed;
  - flags assets for re-check, adds the ISSO queue reason `catalog_change`, and creates a POA&M impact review item (accept the new CAT or keep it, with a rationale).
- **History is never rewritten.** `finding_observations.content_version_id` and assessment content versions are never changed.
- **Mapping history.** `GET /findings/{id}/mappings?as_of={content_version_id}` returns mappings as they stood under that version.
- **NIST catalog / CCI.** `scripts/stage_content_release.py cci_list|oscal_catalog FILE --version --source-url` stages a release. Then use Admin → Register staged content, then Preview, then Apply. CCI apply loads a new version, and existing mappings keep the old one. **Catalog apply is preview-only in this build**, because it needs every system re-baselined.
- **KEV** is a versioned content type. The real CISA KEV snapshot 2026.10.08 is vendored and hashed, and enrichment reads the active version. `scripts/stage_content_release.py kev` fetches a newer snapshot as "available". Applying it re-evaluates findings, and the job `kev.reevaluate` runs daily. **EPSS is not loaded**; the factor is labelled "not loaded" and contributes 0.

### Mapping review
`/mapping-review` lists suggested and low-confidence mappings; approving or rejecting each one needs a justification. **AI: suggest mapping** (`mapping.suggest@1.0.0` via AIService) creates `review_status=suggested` rows only. Control IDs not in the catalog are dropped.

### Operational prioritization score
Score = Σ weight × factor, with each factor between 0 and 1. Factors: severity, KEV, EPSS (not loaded), asset criticality, mission criticality, exposure (network zone), remediation age, authorization status and evidence confidence.
- Weights are stored in `priority_weights` with `rf_*` codes and edited in Admin (`risk.admin`).
- Scores are recomputed on every system evaluation and when weights change.
- The breakdown on the finding page adds up exactly to the total.
- It is labelled *"Operational prioritization score – not a formal residual risk determination."*

### OSCAL exports
POA&M, SSP, Assessment Plan and Assessment Results are produced as JSON, **OSCAL 1.2.2**, matching the pinned oscal-content catalog's `oscal-version`.
- **Validation.** Each export is checked against the **official NIST schemas** (`content/oscal-schemas/v1.2.2`, downloaded from the usnistgov/OSCAL v1.2.2 release and hashed in the manifest). It uses jsonschema Draft-07, with a `regex` engine for the `\p{..}` patterns.
- **Labelling.** A failed export is stored as `_INVALID` and is never labelled valid OSCAL.
- **Storage.** Every export is saved as hashed evidence with an `oscal.exported` audit event. Preview and download are on the Authorization page.
- **Not supported:** component definitions, catalog/profile export, and XML/YAML. Limitations are listed in the UI.
- **Policy comparison** export stays CSV, because there is no schema-valid OSCAL equivalent for it.

### eMASS sync engine (`app/services/emass.py`, page `/emass`)
- **Modes:**
  - `mock`: a synthetic remote store, labelled MOCK.
  - `read` / `write`: REST stubs that stay disabled until the base URL, app registration, API key (SecretStore, never returned), client certificate file and user UID are all set. Real import and write raise "not implemented in this build".
  - `oscal_export_only`: the UI says "No live synchronization occurred".
- **Admin setup panel** shows each prerequisite truthfully, plus capabilities, a connectivity test, last sync and errors.
- **Compare and import.** Compare checks local vs remote (in sync / different / local only / remote only). Import fills empty local fields only.
- **Outbound queue.** Each change records entity, operation, before/after, requester, approval, submission time, response, attempts, retry history and final status.
  - Submitting needs an `emass_submission` approval (decision rule: ISSM).
  - Recoverable failures go to `pending_retry` with exponential backoff, retried by the job `emass.retry`, up to 5 attempts.
  - If the remote version moved past our base version, the change goes to `conflict`, and a person must choose keep local (rebase) or accept remote.
- **Auto-queue.** Approved POA&M closures and authorization decisions auto-queue *proposed* changes; nothing is auto-submitted.
- **Mock failure simulation** (Admin): fail the next N calls with 500, a timeout or a 409.
- **POA&M page.** The "Pending eMASS sync" card and the eMASS column use the real queue state. Workbench "Submit for eMASS sync" queues a control change.

### Continuous monitoring scheduler
The `scheduled_jobs` table (Admin → Continuous monitoring jobs) shows the interval, enabled flag, last run, status, next run and run count, with **Run now**.
- **Jobs:** freshness 15 min, attestations 60, integrity re-hash daily, risk snapshot + score recompute daily, deadline notifications 60, mock connector collection 30 (each source runs on its own frequency, so its *next run* is real), KEV re-evaluation daily, eMASS retry 5.
- **No double runs.** The worker ticks every `SCHEDULER_TICK_SECONDS`, locks due rows with `FOR UPDATE SKIP LOCKED`, and won't enqueue a job type that is already queued or running.
- **Recovery.** Stale running jobs (more than 30 min) are requeued, and results are written back to the schedule row.

### Phase 4 demo script
1. **ISSO** → Evidence Ledger → Content updates → DISA STIGs → *Preview diff & impact*. Check the 6 / 3 / 11 / 2 tabs, the 14 LTP assets, controls, and **P-0027 severity CAT II → CAT I**.
2. **ISSM** applies it with a justification. Then: P-0027 shows the impact banner; findings show V1R2; the finding page's *Mappings by content version* can show "As of V1R1"; observations are unchanged.
3. Finding page → score breakdown (it adds up). **Admin** → weights → change `rf_kev` → scores recompute.
4. System → Authorization package → OSCAL → generate POA&M / SSP / AR / AP. Each shows "Valid OSCAL (schema-validated)" with the schema hash. Download.
5. **Admin** → eMASS: MOCK mode, "Fail next 2 (500)". **ISSO** → eMASS → Compare → queue P-0019 → request approval. **ISSM** approves in Reviews. Submit → `pending_retry`; the POA&M is not synced and the local record is unchanged. Turn simulation Off → Retry → `succeeded`.
6. Admin → switch to `oscal_export_only` → the banner says "No live synchronization occurred". Switch back to mock.
7. Admin → Continuous monitoring jobs → Run now; last and next run update.

Tests: `pytest -c pytest.aegis.ini tests` → 72 tests. `tests/test_phase4.py` covers: Part A, the STIG diff/impact/apply with history preserved, KEV enrichment from the pinned file, OSCAL POA&M/SSP/AR/AP schema validation (test 9), eMASS failure/retry/conflict/export-only (test 10), scheduler idempotency, and the risk-score explanation adding up.

## Phase 5 – Production hardening & handover
- **Auth**: `AUTH_PROVIDERS=dev_password,oidc,mtls_header`. OIDC (Code + PKCE) and a trusted-proxy mTLS header stub for CAC/PIV. Removing `dev_password` hides the picker and disables `/auth/login`. Server-side sessions (idle 30 min / absolute 12 h, refresh rotation, logout revocation), lockout, rate limits, security headers.
- **Uploads**: extension + magic-byte allowlist, size cap, defusedxml, zip-bomb/traversal checks, optional ClamAV (`UPLOAD_SCANNER=clamav`).
- **Tenant isolation** enforced and tested. **Retention** policies with dry-run (audit events are never purged).
- **Secrets**: `SECRET_STORE_BACKEND=env_key|vault`.
- **Ops**: `/api/v1/health`, `/api/v1/ready`, `/api/v1/metrics` (Prometheus). `--profile monitoring` (Grafana dashboard), `--profile keycloak`, `--profile clamav`. `docker-compose.prod.yml` (TLS edge, OIDC, no demo seed).
- **Backup/restore**: `scripts/backup.sh`, `scripts/restore.sh` (verified restore in pod).
- **Quality**: `make acceptance` (AT-1..AT-12 → `docs/TEST_RESULTS.md`), `make scan` (`docs/security/`), `make perf` (`docs/PERFORMANCE.md`), `.github/workflows/ci.yml`.
- **Docs**: `docs/ARCHITECTURE.md`, `DEPLOYMENT.md`, `API.md` + `openapi.json`, `SECURITY.md`, `PORTABILITY.md`, `CONTENT_UPDATES.md`, `MIGRATION_PROCEDURE.md`, `EXTERNAL_VALIDATION.md`, `TEST_RESULTS.md`, `PERFORMANCE.md`.
- Not claimed: FedRAMP, ATO, IL4–IL6, CUI, FIPS 140-3 validation, CAC/PIV conformance. Docker, real-IdP OIDC, ClamAV, Vault and CI were **not executed** in the build environment.

## IronVision Design System (visual redesign)
- Tokens: `frontend/src/styles/tokens.css`, generated by `scripts/gen_tokens.py`. Every Tailwind colour family maps to a CSS variable, so no page has its own colours. Light/dark toggle in the header (`theme-toggle-btn`). The choice is saved in `localStorage` (`ironvision.theme`) and the first load follows `prefers-color-scheme`.
- Components: `.panel`, `.card-interactive`, `.btn-primary|secondary|outline|ghost|destructive`, `.input`, `.th/.td`, `.t-display … .t-label` (index.css). `StatusPill`/`S` maps statuses onto Draft · Under Review · Approved · Failed · Critical · Warning · Informational. `Sev` styles CAT I/II/III.
- Fonts: Plus Jakarta Sans (headings/UI) and Inter (body) from Google Fonts. Air-gapped builds use the vendored copies (`scripts/vendor_fonts.sh` → `frontend/public/fonts/fonts.css`) or the system fallback stack.
- Logo: the official IronVision artwork (`frontend/src/assets/brand/original/Logo-01.webp`, supplied by the customer). `scripts/build_brand_assets.py` builds every variant from it: mark, dark mark, white mono mark, vertical lockup and dark lockup (each 1x/2x), plus favicons (svg, 16, 32, 180, 512). There is a single swap point, `frontend/src/assets/brand/index.ts`.
- Details: `docs/DESIGN_SYSTEM.md`. Screenshots: `docs/screenshots/`.
