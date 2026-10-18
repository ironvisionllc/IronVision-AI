# AegisRMF by IronVision – PRD

Tagline: "Intelligent Risk. Continuous Assurance." An RMF automation / compliance workbench for federal ISSO, ISSM, SCA and AO users. All data is synthetic.

## Original problem statement (Phase 0 summary)
Build only the Phase 0 Foundation POC, and keep it portable with no Emergent lock-in: PostgreSQL 16 + Alembic, FastAPI with /api/v1, a separate worker (Postgres-backed queue), a React + TypeScript frontend, a StorageService (s3/local), an AIService (anthropic / openai_compatible / emergent dev-only, model Claude Sonnet 5.5, logged to ai_interactions), and an AuthProvider abstraction (dev_password only, labeled as simulated) with RBAC as a separate layer. Deliver Dockerfiles, docker-compose, .env.example files, verify_portability.sh, README and PORTABILITY.md.
Phase 0 scope:
- Schema skeleton.
- Pinned, hash-verified NIST 800-53 Rev5 OSCAL catalog, the four baselines and the DISA CCI list.
- 8 demo roles, with an AO-only test endpoint (ISSO gets 403).
- App shell with sidebar, system selector, synthetic banner and dev-auth label.
- Read-only controls browser with a content-versions panel.
- AI health endpoint and /api/v1/health.
- pytest suite and docs.

## User choices
- Emergent Universal Key in the preview through the dev-only adapter. The anthropic and openai_compatible adapters can be selected with env vars.
- One demo password for all 8 accounts: AegisDemo!2026.
- Pinned to the latest oscal-content tag, v1.5.0. The CCI list is pinned the same way.
- Visual style: clean federal look, dense tables, IBM Plex Sans, status pills.

## Personas
System Owner, ISSO, ISSM, SCA, AO, DevSecOps, Leadership Viewer, Platform Admin. The Platform Admin role has no AO/SCA decision rights.

## Implemented (2026-10-10, Phase 0)
- Postgres 16 runs in the pod under supervisor, with its data in /app/data/postgres. Migration 0001 creates 19 tables plus an append-only trigger on audit_events.
- Content loaded:
  - 1,196 controls (324 base, 872 enhancements, 182 withdrawn).
  - 3,715 800-53A objectives.
  - Baselines: Low 149, Moderate 287, High 370, Privacy 96.
  - 5,137 CCIs and 3,838 CCI→Rev5 mappings, all resolved to controls.
- Auth and RBAC:
  - dev_password login with JWT and lockout after repeated failures.
  - Permission matrix with a `require_permission` check on endpoints.
  - Audit trail with a hash chain covering login success/failure, authorization denials, and AI/job events.
- AIService with versioned prompts and Pydantic validation. The AI health call succeeds (emergent adapter, claude-sonnet-5-5).
- StorageService with local and s3 drivers. Worker with heartbeat and the content-load job.
- React TS UI:
  - Login with dev user picker.
  - App shell with banner, sidebar, system selector, user and roles.
  - Controls catalog with search, family/baseline filters, detail drawer and content-versions tab.
  - Admin page: health, RBAC demo, AI test, jobs, audit table with chain check, RBAC matrix.
  - Honest "Coming in Phase N" placeholders for unbuilt pages.
- Dockerfiles, compose, .env.examples, verify_portability.sh, README, PORTABILITY.md.
- 33 pytest tests pass.

## Implemented (2026-10-10, Phase 1 – Core Records & Ingestion)
- Migration 0002: systems/assets/system-scoped roles, overlays, common-control providers, control_assignments (4 separate statuses), implementations (versioned), evidence_sources (encrypted creds), ingest_runs, evidence + evidence_controls, findings (canonical, versioned dedup_rules) + finding_observations, finding_control_maps (provenance/confidence/review), org_mapping_rules, freshness_policies, priority_weights, comments, risk_snapshots.
- Pipeline: STIG .ckl/.cklb, ACAS .nessus/CSV via worker job; SHA-256 duplicate detection; CCI→800-53 via pinned DISA list; ACAS via synthetic org rule (RA-5, SI-2); unmapped require ISSO map/disposition with justification.
- Worker: ingest, integrity verify, scheduled freshness + snapshots. Postgres data in /app/data/postgres with auto-bootstrap from server.py.
- UI: Systems list/register/detail (assets, roles), Evidence Sources cards + upload, Ingest run detail, Evidence Ledger, ISSO Workbench queue + control panel, Leadership dashboard, Admin Reset Demo. Phase labels updated (P2 POA&M; P3 Inheritance/Policy Auditor/Reviews/Workflow).
- Seed: 4 synthetic systems (LTP moderate+overlay=291, MPP high, FMDH moderate, TRS low), 18 sample files ingested through pipeline.
- Tests: 45 pytest passing.

## Implemented (2026-10-11, Phase 2 – End-to-End Workflow + Part A fixes)
- Part A: source cards reconcile (Total/Open/Mapped/Unmapped, auto-attribution of unsourced uploads); per-asset freshness coverage (current/partially_stale/expired + "N of M assets" reason); uploads = hash_recorded + unsigned + current; grouped control mappings.
- Migration 0003: poams (+findings, milestones, history), poam_match_rules, decision_rules, approval_requests/decisions, implementation AI/review fields, finding remediation fields, notification kind.
- POA&M module (list w/ server search/sort/filter/pagination + summary, detail, create-from-finding with match/link, milestones, closure/risk/extension requests), remediation detection → closure_eligible (never auto-close).
- Reviews engine (decision rules, tabs, decision actions, effects, self-approval blocked), notifications bell, finding detail page, deep links.
- AI implementation statement (grounded, validated citations, sections, draft versions, review request, diff, needs_reconsideration).
- Leadership full (cards, waiting on you, op-priority score, trend incl. POA&M/risk acceptances).
- Seed: P-0015/19/22/26/27/30/31 on LTP. Tests: 54 passing.

## Implemented (2026-10-11, Phase 2 follow-ups)
- authz.denied audit on review decisions; poam.closure_eligible system audit event; cat_rules (migration 0005) with persisted CAT; author names/roles in APIs; interaction_id linkage for AI versions; verify_portability.sh E2E API flow; docs/EXTERNAL_VALIDATION.md. Tests: 56 passing.

## Implemented (2026-10-11, Phase 3 – RMF Workflow Modules)
- Migration 0006. Inheritance & Attestations: providers CRUD, shared responsibility split, owner-only simulated-signature attestations, renew/history, reminders, expiry cascade (worker + demo tool).
- SCA assessments (independence enforced) are the only path that sets assessment_status. Authorization package → ISSM endorse → AO-only ATO/ATO w/ conditions/IATT/DATO; denials are audited.
- Policy Auditor: PDF/DOCX/TXT go to the ledger; worker policy.analyze compares policy value, ODP and observed value; findings stay proposed until a human confirms, dismisses (justification required), requests review or links them; CSV export. 14 synthetic policies; samples are in samples/policies.
- Notifications prefs + idempotent deadline job (email adapter disabled). Header global search filtered by RBAC. Live RMF Workflow (7 stages + 4 ongoing). Audit log filters/pagination/CSV/JSON export/chain check.
- Admin: invite (dev temp pw), access history, truthful security panel, banner, AI settings stored in the DB and enforced, versioned decision-rule editing. Dev login picker shows seeded accounts only.
- Tests: 65 project + 17 agent tests passing (iteration_4).

## Implemented (2026-10-11, Phase 4 – Advanced Automation)
- Part A: POA&M prefill source label, system-scoped/grouped search, decider object, shared statement definition (queue == RMF Implement), LTP seed 61/44/186 + 38 attestations.
- Versioned STIG content (synthetic Demo OS STIG V1R1 installed / V1R2 available), diff + impact preview, controlled apply (content.apply), no history rewrite, mapping history as_of, CCI staged apply, catalog preview-only.
- KEV as versioned content (pinned CISA snapshot), daily re-evaluation; EPSS not loaded (labelled).
- Mapping review + AI suggest-mapping (proposal only).
- Configurable operational prioritization score with breakdown that sums.
- OSCAL 1.2.2 POA&M/SSP/AP/AR exports validated against official NIST schemas; stored as hashed evidence.
- eMASS engine: mock/read/write/oscal_export_only adapters, approval-gated outbound queue, retry/backoff, conflict resolution, failure simulation, truthful setup panel.
- DB-backed scheduler (8 jobs) with locking, idempotency, stale-job recovery; Admin UI.
- Tests: 72 passing.

## Not executed
- Docker build and compose up (no Docker daemon in the pod).
- Real MinIO (only moto-mocked S3 was tested).
- The direct anthropic and openai_compatible adapters.

## Backlog
- Post-Phase 5: real eMASS REST import/write, NIST catalog re-baseline apply, EPSS feed, email adapter, component definitions, migrate frontend off CRA (clears remaining build-time yarn-audit highs), shared rate-limit/OIDC-state store for multi-replica.

- P0 (Phase 1): system registration and categorization, populating the system selector, system-scoped role assignments.
- P1: evidence sources and ledger (Phase 2), inheritance (Phase 2), POA&M and policy auditor (Phase 3), reviews and RMF workflow (Phase 4), portfolio (Phase 5).
- P2: OIDC / CAC-PIV AuthProvider, refresh tokens and session revocation, admin user management UI.

## Phase 5 – Production Hardening, Portability & Handover (completed 2026-10)
- Part A: Content Updates history and apply message are readable (diff counts + impact); no raw JSON.
- Auth: AUTH_PROVIDERS (dev_password | oidc | mtls_header). OIDC Code+PKCE (mocked-IdP test). mTLS trusted-proxy stub. Dev picker hidden when disabled. Server sessions (idle 30m / abs 12h, refresh rotation, logout revoke). Lockout 5/15m. Rate limits. Security headers, CORS allowlist.
- Uploads: allowlist + magic bytes + size + defusedxml + zip checks + optional ClamAV. Tenant isolation test. Retention (audit never purged).
- Secrets env_key | vault (mocked test). Backup/restore scripts (RESTORE_VERIFY: PASS). /health /ready /metrics.
- Migrations 0008 (hardening), 0009 (perf indexes). Perf smoke: 5k findings 17.7s → 13.5s.
- Scans: pip-audit clean, bandit 0 high/medium, yarn 0 critical (12 high in react-scripts build tooling only). Trivy not run.
- Acceptance AT-1..AT-12 (make acceptance) 12/12. Full suite 85/85. Testing agent iteration_6: 100%.
- Ops: docker-compose.prod.yml (TLS edge, OIDC, no seed), profiles keycloak/clamav/monitoring, CI workflow, Makefile, docs set + openapi.json.
- NOT executed in pod: Docker build/up, real IdP, live ClamAV/Vault, GitHub CI.

## Visual redesign + rename (2026-10)
- Product renamed **IronVision AI** in all user-visible places: UI, title, favicon, API docs title, OSCAL remarks/descriptions, auth error text, README/docs. Internal codename `aegisrmf` is kept for identifiers.
- IronVision Design System:
  - Tokens are in one file (`src/styles/tokens.css`, generated by `scripts/gen_tokens.py`) and every Tailwind family is remapped onto them.
  - Light/dark toggle, saved locally and following `prefers-color-scheme` on first load.
  - Plus Jakarta Sans + Inter, with vendored offline copies.
  - Restyled cards, interactive cards, buttons, inputs, tables, sidebar/header, modals (Esc + focus), StatusPill categories with icons, and CAT badges (`Sev`).
  - Leadership chart colours come from tokens.
- Logo system: `src/assets/brand/logo.svg` + `logo-mono.svg` (swappable recreation), favicons 16/32/180 + svg via `scripts/build_brand_assets.sh`.
- Part A: SPA security headers on the dev server (craco) and in prod nginx. `/metrics` returns 404 on the SPA (dev, nginx, edge).
- Tests: backend 85/85, acceptance 12/12, yarn build OK. Screenshots: docs/screenshots/*-{light,dark}.png.
- Backlog: swap in the official logo vector when supplied, plus a per-page dark-mode polish pass for less-used admin sub-panels.

## 2026-10-12 – Official logo, DigitalOcean handover, Docs Center
- The logo now comes from the customer's Logo-01.webp via `scripts/build_brand_assets.py`. The header mark and login lockup are served at 1x/2x through srcset, with dark-mode variants. Favicons are regenerated. Screenshots were retaken for login, leadership, controls-workbench-cm6, poam and evidence-ledger in both themes.
- The demo data reset removed the 5k perf findings. test_credentials.md notes that system IDs change on reset.
- docs/DIGITALOCEAN_DEPLOYMENT.md covers all 13 sections. Status: documentation only, not yet executed on DigitalOcean. deploy/digitalocean/ holds the compose overlays (prod and staging), nginx edge templates, env templates, systemd units (app, backup timer, certbot renew), backup-offsite.sh and docker-daemon.json for log rotation.
- scripts/check_env.py now checks env files, and the production guard refuses dev_password or the demo seed. `python -m app.cli create-admin` creates the first admin. STAGING_DEMO_PASSWORD applies to staging. The AI_PROVIDER=emergent setting is refused in staging and production.
- scripts/verify_no_preview_deps.sh passes for the non-Docker parts; the image checks run on the Droplet with --docker.
- The in-app Docs Center (/docs-center, /docs-center/:slug) serves an allowlist of docs, with .md download and a zip of all docs.
- Verification: backend 91 passed, acceptance 12/12, frontend yarn build passed.
- Backlog: run the Droplet validation checklist (§13), set up CI image builds and a registry, and work through the remaining frontend yarn-audit items.

## 2026-10-13 – ISSO usability round (Waves 1–7) + Wave 8 sandboxes
- W1: one metrics service (`app/services/metrics.py`) now feeds Controls, Workflow, POA&M, eMASS, Sources and Leadership.
  - Each screen labels both "controls with current supporting evidence N of M" and "collected evidence items within freshness window %".
  - Monitor stage is rule-based: KEV / CAT I / overdue / stale evidence → needs attention.
  - eMASS state is derived from queue and sync history; seed writes real sync history.
  - Pending = not sent + out of sync + queued + failed/retrying.
  - Source cards show Results vs Findings (failed).
- W2: queue lanes (needs action / due soon / backlog by family), mixing control, POA&M, attestation, policy, review and milestone items, with a Mine/All toggle. POA&M list sorts by risk by default.
- W3: control "Policy & parameters" section. ODP-filled control statements. Config evidence is linked to its control, and a config mismatch now marks monitoring as failing. Policy quotes are verbatim with offsets and location. Policy review status is derived from dates.
- W4: passing results excluded and scored 0. Unmapped findings grouped by rule with a host list. Map manually (multiple controls) / out of scope / informational. AI suggest is shown only when AI is configured.
- W5: AI status reports a reason. Template draft engine (`impl-template-1.0.0`). Author shows "System (seed)". Stale-evidence banner only on non-empty statements.
- W6: CRM responsibility matrix (migration 0010, synthetic matrix by family, CSV import). Missing splits are flagged.
- W7:
  - loading states;
  - "Linked: P-xxxx" on findings already on a POA&M;
  - `fmtControl` AC-2(3) ID format;
  - human-readable history;
  - attestation evidence naming plus a 365-day window;
  - Superseded evidence state;
  - no future content dates;
  - non-overlapping decision rules with a validator;
  - audit log shows human actions by default;
  - eMASS retry idles when the queue is empty;
  - nav entries hidden by permission;
  - XCCDF/ARF and SARIF parsers with samples;
  - responsive sidebar.
- W8 (migration 0011):
  - single demo account demo@ironvision.ai (`DEMO_PASSWORD`);
  - self sign-up (`ALLOW_SIGNUP`, honeypot, per-IP limit, password rules);
  - private sandbox tenants provisioned by the seed pipeline as job `sandbox.provision`;
  - persona identities with "Acting as" switcher, SoD per persona, and `operated_by` on every audit event;
  - reset sandbox, inactivity purge job, nightly demo reset;
  - onboarding checklist.
  - The 8 role users exist only as test fixtures.
- Verification: backend 132 passed; acceptance 12/12; yarn build OK.
- Backlog:
  - Out-of-scope dispositions are applied directly; they do not yet go through a decision-rule approver.
  - Day-23/29 expiry warnings are in-app notifications only, no email.
  - Onboarding steps other than "switch to ISSM" are marked done when their link is clicked, not when the action is completed.

## 2026-10-13 – Follow-up round
- Shared `client_ip()` for the sign-up, login and upload limiters and audit: X-Forwarded-For is trusted only when the peer is in `TRUSTED_PROXIES` (CIDRs or hostnames). The preview trusts the private ingress ranges.
  - `SIGNUP_RATE_LIMIT` (default 5/3600) is counted from recorded sign-up audit events per real client IP.
  - The old preview counter is cleared.
- Out of scope / N/A now creates a `finding_out_of_scope` review (default rule: ISSM decides) and only applies on approval. The pending state shows in Mapping Review and Reviews.
- Control-ID formatter is used everywhere, including backend notifications and exports. Added the guard `yarn check:control-ids` (`frontend/scripts/check-control-ids.js`).
- Loading placeholders replace 0 counts on several tiles and panels.
- Onboarding ticks come from real audit events after the sandbox is ready.
- A fresh login always acts as ISSO and shows an "Acting as ISSO" toast.
- Source card labels changed to "Mapped findings", ingest table to "Mapped results".
- eMASS last sync = max of succeeded sync-history rows.
- Verification: backend 136 passed, acceptance 12/12, build OK.

### Sign-up rejection fix (Oct 2026)
- Root cause: honeypot field named `website` was autofilled by the customer's browser (audit reason=honeypot ×2). Replaced with off-screen `iv_hp_fax_only` (autocomplete off, password-manager ignore attrs, tabindex -1, aria-hidden) + signed form token with SIGNUP_MIN_SECONDS (default 2).
- Specific messages for password/duplicate/rate limit (minutes remaining); bot rejections generic but audited with reason + XFF chain; only successful sign-ups count toward the limit.
- Preview TRUSTED_PROXIES now includes Cloudflare ranges + the edge LB 35.186.245.91, so the real client IP is used (was shared edge IP for all users). Edge IP removed from SIGNUP_RATE_LIMIT_EXEMPT_CIDRS.

### Clean sign-up workspaces (Oct 2026)
- Only demo@ironvision.ai is seeded (4 systems). New sign-ups provision CLEAN (`seed_tenant_config`: decision/CAT/match/dedup/weight rules, reference content, personas).
- "Clear my workspace" (non-demo) vs "Reset demo data" (demo; nightly). Confirm modal. Audit `sandbox.workspace_cleared`.
- 18 existing sign-up tenants converted (audit `sandbox.converted_to_clean`, accounts kept, incl. k.hill).
- Clean onboarding: Register system → Add source/upload (+ samples.zip download, allowlisted, no auto-load) → Create POA&M → ISSM approve closure → View Leadership; ticks from audit events only (manual link-click ticks removed).
- Empty states: NeedSystem CTA, Systems "Register your first system", Evidence Sources "Add a source or upload a scan", Leadership "No systems yet", Workflow ongoing stages "not configured" when no records.
- Fixed tenant leak: audit log items + category counts now tenant-scoped.

### Domain switch + automatic TLS (Oct 2026)
- `./deploy.sh --set-domain <d> --email <e>` runs scripts/set_domain.py: backup, mode 600, rewrites APP_DOMAIN, FRONTEND_URL, CORS_ORIGINS, OPENROUTER_SITE_URL, OIDC_REDIRECT_URI and LETSENCRYPT_EMAIL, plus every non-secret occurrence of the old or placeholder domain, then prints a diff.
- scripts/ensure_tls.sh `ensure` runs before the app starts. If the cert is missing, for another domain, expiring within 30 days or from the staging CA, it runs a DNS A-record vs Droplet IPv4 check (--force-tls skips it), stops edge, checks port 80, runs certbot certonly --standalone (honouring LETSENCRYPT_STAGING), and re-checks. It can also install a user-supplied CERT_FULLCHAIN_PATH/CERT_KEY_PATH. `verify` checks the SAN, the Let's Encrypt issuer and https /api/v1/ready.
- deploy.sh installs and enables the systemd units (paths rendered for the checkout; renew timer and backup timer) when run as root or with --install-systemd; --no-systemd skips this.
- check_env rejects placeholder domains in staging/prod and warns when LETSENCRYPT_EMAIL is empty. The templates have a TLS block. Docs §3/§4 and README were updated. tests/test_tls_domain.py uses fake docker/openssl/getent/curl.

### One-command Droplet deploy (Oct 2026)
- New tracked, executable `./deploy.sh` at the repo root. With no env file, it creates one from the template (mode 600), generates secrets, lists the values the operator must fill, and stops (exit 2). With an existing env file, it runs check_env --fix (backup), then gen_env_secrets, then the placeholder guard, then check_env must PASS, then `exec scripts/deploy.sh`. It refuses git-tracked env files and never sources the env file.
- scripts/deploy.sh gained `--no-cache` and now ends with `Ready: https://<APP_DOMAIN>`. Quick deploy steps are in README and DO guide §0. tests/test_root_deploy.py runs dry runs against a fake docker.

### Env files are data, never sourced (Oct 2026)
- Customer bug: a wrapper sourced the env file, so the unquoted OIDC_SCOPES value ran `email` as a command. The repo itself sourced an env file in one place, deploy/digitalocean/backup-offsite.sh; it now reads keys through scripts/lib/envfile.sh (env_get / env_export → scripts/envget.py). deploy.sh uses env_get too.
- backend/app/envfile.py is the one parser, following Compose/dotenv rules. Lint flags unquoted whitespace or shell metacharacters, unbalanced quotes, `export `, CRLF, trailing spaces, duplicate and invalid keys, and `$` inside double quotes. It reports line numbers with a suggested fix and is an error in staging/production. `check_env.py --fix` writes a backup (mode 600) and preserves comments. OIDC scopes now accept space- or comma-separated values and strip quotes.
- Templates now quote OIDC_SCOPES, DEMO_USER_PASSWORD and OPENROUTER_APP_NAME. Tests cover template lint, parse equivalence across our parser, python-dotenv, envget, env_get and docker compose, and a guard against sourcing (scripts plus code blocks in docs). DO guide §0.2 added.

### requirements.prod drift guard + OpenRouter (Oct 2026)
- A production outage was caused by python-multipart missing from requirements.prod.txt. requirements.prod.txt now holds the same pins as requirements.txt (77 packages). 88 packages are left out, each listed with a reason in requirements.prod-exclude.txt: dev tools, the preview AI adapter and its transitive dependencies, and unused template leftovers.
- scripts/check_requirements.py checks pins, exclusions, import coverage and implicit runtime dependencies; it runs in pytest and CI. app.tools.selfcheck imports every app and worker module; deploy.sh runs it in both images after build, and so do verify_portability and CI. A clean venv with only requirements.prod.txt passed: pip check, selfcheck, uvicorn /health and /ready returned 200, and the worker started.
- AI_PROVIDER=openrouter uses httpx Chat Completions. The model slug is passed through verbatim. Per-use-case env models are supported, and an admin model override takes precedence over them. Structured output tries json_schema, then json_object, then a plain prompt; every reply is validated with Pydantic with one repair retry. 429/502/503 are retried using Retry-After; 402, 401, 404 and timeouts give clear messages. ANTHROPIC_API_KEY is never read in this mode. Templates, check_env and docs were updated.

### Env templates shipped to GitHub (Oct 2026)
- .gitignore: `.env`, `.env.*` and `*.env` ignored every template. Added negations for `*.example` and `env.template`. Real env files, keys, pem and credentials stay ignored. Removed duplicate and legacy cache entries.
- Non-dot copies sit next to each template, identical in content: env.template, backend/env.template, backend/worker/env.template, frontend/env.template, deploy/digitalocean/env.production.template and env.staging.template. Docs, README, CI, verify_portability and the deploy.sh hint now copy from the *.template files.
- tests/test_env_templates.py checks that each pair exists and is identical, holds placeholders only, covers every variable the code reads, and that git check-ignore results are right.

### Fail-fast DigitalOcean deploy (Oct 2026)
- Customer failure: they ran plain `docker compose up` (project aegisrmf) without --env-file or overlays. As a result seaweedfs never started, the S3 keys were blank and objectstore-init exited 1. Their own wrapper then printed "Deployment complete"; that wrapper is not in this repo.
- `scripts/deploy.sh [ENV_FILE] [--staging] [--skip-edge-check] [--no-pull]` is the only supported deploy command. It uses an explicit `-p ironvision`, `--env-file` and overlays, takes COMPOSE_PROFILES from the env file, refuses while aegisrmf containers run, and fixes DATA_ROOT ownership whether run as root or as ironvision (postgres 70, objects 10001, backups = operator). Order: check_env → config → pull → build → postgres → seaweedfs → objectstore-init → migrate → app → /api/v1/ready → summary. It stops at the first failure and is shellcheck clean.
- `deploy/compose/storage-s3.yml` / `storage-seaweedfs.yml` turn missing S3 or admin keys into a readable error at config time. The base and DO files require STORAGE_DRIVER. objectstore-init is a no-op for the local driver; for s3 it names missing variables, retries the endpoint, explains a missing seaweedfs profile, and explains auth failures. check_env enforces that the seaweedfs profile matches the storage mode. `scripts/gen_env_secrets.py` fills only empty secrets (mode 600).
- Verified in the pod: real compose config simulations, objectstore-init against live SeaweedFS (READY, blank keys, wrong secret, missing seaweedfs, delayed endpoint), and deploy.sh dry runs through a fake docker shim covering 8 scenarios. Backend tests: 169 passed, 1 skipped.

### MinIO removal → SeaweedFS (Oct 2026)
- MinIO community images are no longer pullable. All compose files now use SeaweedFS `chrislusf/seaweedfs:4.48` (pinned; verified on Docker Hub: 2026-09-28, amd64/arm64/arm). It runs under profile `seaweedfs`, single container, internal network only (no S3 host port; master UI 127.0.0.1:9333 on DO). S3 identities are generated from env by `deploy/seaweedfs/entrypoint.sh`; the app identity can only Read/Write/List/Tagging on S3_BUCKET.
- `objectstore-init` = backend image `python -m app.tools.s3_bootstrap`: bucket, versioning, optional policy, SHA-256 round-trip; idempotent. `python -m app.tools.objsync` handles dir↔S3 and S3↔S3 copies with a SHA-256 manifest; used by backup.sh, restore.sh, backup-offsite.sh (off-site to any S3 via OFFSITE_S3_*) and MinIO migration (s3:OLD). No mc, aws-cli or rclone.
- New env: S3_ADDRESSING_STYLE, S3_ADMIN_ACCESS_KEY_ID/SECRET (MINIO_ROOT_* are deprecated aliases for the admin key only), S3_BUCKET_VERSIONING, S3_BUCKET_POLICY_FILE, SEAWEEDFS_IMAGE, OFFSITE_S3_*. check_env: storage checks, deprecated names, plain-http non-internal endpoints, app≠admin key. Storage profiles: SeaweedFS / DO Spaces / AWS S3 / Garage / local.
- Also fixed: the KEYCLOAK/GRAFANA `:?` interpolation broke `compose config` for DO env files even with those profiles off. Those passwords are now required only when the profile is enabled (check_env).
- Executed in pod: weed 4.48 binary, bootstrap, least privilege, live round-trip, seed ingestion (25 objects), integrity 25/25, backup→restore PASS, migration 31/31; `docker compose config -q` (Compose v5.6.0) passes on all combinations. Images were not pulled or run.

### CORS review (Oct 2026)
- `access-control-allow-origin: *` on preview responses is injected by the Emergent ingress (app sends exact-origin only; unknown origins get no header, preflight 400). Preview CORS_ORIGINS now = the preview origin only (old host + localhost removed). `*` refused at startup and by check_env; allow_credentials=false. Documented in SECURITY.md + PORTABILITY.md (#7).

### Demo login (Oct 2026)
- "Explore the demo – no sign-up" button → POST /api/v1/auth/demo-login (no password from browser), gated by ALLOW_DEMO_LOGIN (404 when off; check_env refuses in production unless ALLOW_DEMO_LOGIN_IN_PRODUCTION), per-IP rate limit DEMO_LOGIN_RATE_LIMIT, audit auth.demo_login; user invites refused in demo tenant; `scripts/check_bundle_secrets.sh` greps src/public/build for demo passwords.

### Access-denied polish (Oct 2026)
- 403 missing-permission detail is structured ({code, permission, roles, message}); `AccessDenied` panel shows "Your acting role (X) can't view …" with one-click persona switch buttons in sandboxes, plain "You don't have access" elsewhere. Action errors read "Your role can't do this (needs …, held by …)".
- useApi refetches after a persona switch (`iv:identity` event).
- RMF Workflow with zero systems shows all 11 stages "Not configured" + "Register your first system" CTA. Onboarding "View Leadership" carries the role-switch hint.


### Security fix round (Oct 2026)
- Direct finding disposition endpoint now routes through decision-rule approval (all disposition types); informational rule-action likewise.
- Route authorization guard: all mutating routes declare permission dependencies; automated enumeration test.
- Workflow bypasses closed: POA&M PATCH status during review / later due date; assessment needs `assessment.perform`; authorization decision needs `authorization.decide`; attestation sign needs `evidence.submit`; eMASS keep_local needs re-approval.
- `SIGNUP_RATE_LIMIT_EXEMPT_CIDRS` (preview: loopback + 2 test-pod /32s). Demo sandbox reset.
- Verification: backend 143 passed, acceptance 12/12, build OK.

### UI fix round (Oct 2026)
- Modal focus-steal regression fixed (focus on mount only; Esc uses latest onClose via ref). Modal moved to `components/common/Modal.tsx`; Jest test `Modal.test.tsx` types per keystroke and asserts focus + full value (fails on the old code).
- Onboarding checklist refetches /sandbox/status after any successful write (debounced global `iv:mutated` event), on window focus and on route change.
- Browser self-run: Add to POA&M, Request closure, Map manually, Register system, Create account all keep full typed text; checklist ticked "Create a POA&M" without reload.


### Keycloak authentication for demo.ironvisionai.com (Oct 2026) – implemented, NOT deployed
- Keycloak 26.8.1 (`deploy/keycloak/Dockerfile`, `start --optimized`, Postgres DB/role `keycloak` created idempotently by `keycloak-db-init`) via overlay `deploy/compose/keycloak.yml` (auto-added by deploy.sh when AUTH_DOMAIN set; loopback 127.0.0.1:8081 for SSH-tunnel admin). Edge `edge-auth.conf.template`: only /realms/<realm>/, /resources/, /js/ public; /admin/ and /realms/master/ denied unless KEYCLOAK_ADMIN_ALLOWED_CIDRS. ensure_tls.sh handles APP_DOMAIN + AUTH_DOMAIN (separate certs, DNS preflight, discovery + /admin 403 verification).
- `python -m app.tools.keycloak_config plan|apply`: master hardening (configurator service account, named admin + CONFIGURE_TOTP, OTP required in master browser flow, bootstrap admin disabled) + realm ironvision-demo (confidential client ironvision-app, PKCE S256, standard flow only, password policy, brute force, no registration/reset/verify, 5-min tokens, SSO = app session timeouts, KEYCLOAK_REQUIRE_MFA).
- Backend OIDC hardening: DB-backed single-use state (`oidc_pending`), one-time 60 s login code exchanged by POST (`oidc_login_codes`; no tokens in URLs), discovery TTL + JWKS kid-miss refresh, RP-initiated logout (id_token_hint), explicit identity mapping only (no email linking outside dev; unmapped → 403 + audit), admin read-only mapping view. Migration 0012 (additive).
- CLI: `keycloak-migrate` (dry run default, plan hash, --apply/--yes/--plan-hash, --create-identities/--link/--reactivate, backup required, individual generated passwords → 600 CSV once), `keycloak-user list|set-password|rotate|disable|enable|reset-mfa`, `identity-map`, `identity-list`; wrapper `scripts/keycloak.sh`.
- deploy: `./deploy.sh --set-auth-domain auth.demo.ironvisionai.com`, `--apply-realm`; order backup → postgres → keycloak-db-init → keycloak → realm plan/apply → TLS → app. systemd units read `/srv/ironvision/compose.env` (same overlays as deploy). Backups include keycloak.dump.
- Demo-login 404 unless dev_password provider enabled; hidden in Keycloak mode (Explore-demo options pending approval).
- Templates: Keycloak block in production/staging pairs; `env.customer-production.template` (+.example) for future app.ironvisionai.com (realm ironvision-prod, MFA required, no demo) – not deployed.
- Tests: 11 LIVE tests vs real Keycloak 26.8.1 in pod + 13 infra/unit tests (real nginx in front of live Keycloak for /admin 403). Backlog: approve Explore-demo mechanism; run on Droplet; switch AUTH_PROVIDERS=oidc after migration.
- Follow-ups (Oct 2026): per-xdist-worker test DBs (`<db>_gwN`); tests/acceptance only collected when targeted; seed lookups scoped to the demo org (sandbox tenants copy LTP data). Real bugs fixed: SARIF evidence source missing from connector catalog (`/systems/{id}/sources` 500 after a SARIF upload); source cards `unmapped` now includes dispositioned (Mapped + Unmapped = Total). Docs/scripts path-agnostic (customer checkout /opt/ironvision/IronVision-AI). Live test: named master admin requires OTP.
- Explore-the-demo Option B (approved, implemented): client `ironvision-demo-launcher` (direct grant only, client-specific flow denies users without admin-only attribute `demo_launcher=true`), realm browser flow `ironvision-browser` (username → deny launcher users → password → OTP), launcher user = unpublished handle `KEYCLOAK_DEMO_USERNAME` + `@demo-launcher.invalid` e-mail (Keycloak counts deny-access as brute-force failure; handle keeps visitors from targeting it), no default roles; backend ROPC server-side, ID-token validation, explicit mapping to demo@ironvision.ai, KC session ended immediately, provider `oidc-demo`, per-IP + global rate limits, 503 on IdP errors, 404 unless ALLOW_DEMO_LOGIN + oidc + launcher configured. check_env: production demo login only with DEPLOYMENT_KIND=demo. `scripts/keycloak.sh rotate-demo`. Option C (ephemeral per-visitor users) documented only.

## 2026-10-15 – Demo self-registration + doctor; recovery toolkit (NOT run on the customer Droplet)
- Keycloak self-registration, DEMO only (`KEYCLOAK_ALLOW_REGISTRATION`, check_env refuses customer). JIT clean sandbox only for
  Keycloak REGISTER-event users; reserved identifiers / existing-account e-mails refused (403, never auto-linked); purge deletes
  the self-registered Keycloak user; edge rate limit on registration routes; Login: Sign in / Create account / Explore demo.
- `scripts/keycloak.sh doctor` (+ deploy.sh summary): OK/FAIL with exact fix commands, no secrets.
- Migration 0013 `organizations.protected`; purge hard-refused for protected/non-sandbox tenants.
- `./recover.sh` preflight/rehearse/apply --plan-hash/verify/rollback/status/audit/link; MinIO xl-single reader; copy-only
  SeaweedFS recovery; `scripts/e2e_sso.py`; `scripts/recover_audit.sh`; docs/RECOVERY_REPORT.md.
- Verified in pod: backend 256 passed/25 skipped (serial + parallel), live Keycloak 19/1 skipped, recovery E2E 25/25, e2e_sso 15/15,
  testing agent iteration_12 100%.
### Backlog
- P0: operator runs `./recover.sh preflight → rehearse --e2e → apply` on the Droplet; `doctor` must show 0 failing checks.
- P1: real MinIO binary fixture validation of the archive reader; reboot persistence check on the Droplet.
- P2: Option C ephemeral demo users; customer-production registration opt-in design.

## 2026-10-16 – Demo defaults + `./deploy.sh --apply-demo-settings`
- Demo template pair (env.production.template = .env.production.example) ships the demo.ironvisionai.com values (single
  source: scripts/apply_demo_settings.py DEMO); secrets empty; KEYCLOAK_ADMIN_USERNAME=ironvision-admin (non-secret, needed by
  check_env). Customer-production/staging keep placeholders; OIDC_CLIENT_ID=ironvision-app everywhere.
- `scripts/apply_demo_settings.py` / `./deploy.sh --apply-demo-settings [--yes]`: in-place rewrite of only those keys (backup,
  600, never sourced, secrets untouched), dry-run diff by default, OIDC_CLIENT_ID only after live Keycloak confirms the client
  (else exit 3 + client list via `scripts/keycloak.sh … clients` + fix `./deploy.sh --apply-realm`).
- Tests: backend 269 passed / 26 skipped (serial + parallel); shellcheck clean.

## 2026-10-16 – Legacy `aegisrmf` containers + automated recovery (run / cutover / finalize)
- `scripts/legacy_project.sh inspect|backup|stop|preserve-and-stop`: verdict SAFE_TO_STOP / PORT_CONFLICT /
  PRODUCTION_DEPENDS_ON_LEGACY (DATABASE_URL/storage host, shared networks, mounts, ports); verified backups (pg_dump -Fc +
  pg_restore -l, globals, docker inspect, read-only objsync MinIO export, SHA-256 manifests incl. every exported object);
  graceful `docker stop` only, prints `docker start …`; never rm/down/-v.
- `scripts/deploy.sh`: legacy gate – safe → continue with warning; conflict/dependency → exact fix command.
- `recover.sh run` (read-only: inspect, backups, source selection preferring live legacy DB matching stated counts, preflight,
  rehearsal, SSO probe, PLAN-HASH) → `cutover --plan-hash` (apply, switch, deploy, Keycloak link, verify, live SSO, doctor,
  SeaweedFS restart; auto-rollback on failure) → `finalize` (reboot check, graceful legacy stop) ; `resolve-conflict`; `rollback`.
- Fixes found in replica: catalog FK re-keying by natural key; sequence reset after merge; Keycloak person-name sanitising;
  demo-sandbox personas skipped by keycloak-migrate; nested manifest paths.
- Image pinning: SeaweedFS 4.48 + postgres/nginx/certbot/keycloak pinned by digest; check_env tag-only = warn (demo) / error (customer).
- Verified locally: backend 285 passed/27 skipped; orchestration E2E 24/24; recovery E2E 2/2; live Keycloak 19 + 1 skipped; shellcheck clean.
  NOT run on the customer Droplet. Legacy MinIO was a SeaweedFS stand-in.


## 2026-10-16 – Droplet `recover.sh run` legacy-backup fixes (no deploy)
- Root cause reproduced: empty `postgres` maintenance DB → valid archive with 0 TOC entries, rejected as "unreadable". Now same-major
  pg tools (container client or local postgres:<major> image), no TTY, PGDMP header + pg_restore -l + archive-version + sha256;
  0-entry dumps only with catalog proof → `maintenance_db`; globals (--no-role-passwords) mandatory + verified; read-only sessions.
- Dependency verdict evidence-based (mount mode/kind, env KEY host resolution on shared nets, published ports, data volumes); RO repo
  binds no longer a dependency; legacy app containers reported as non-sources.
- MinIO: endpoint from inspect (IP + internal port), *_FILE secrets, helper image fallback, `objsync probe` (short timeouts), mc
  listing fallback; else tarball + "evidence NOT verified".
- Verified locally: backend 301 passed/27 skipped; orchestration E2E 28/28 (incl. 3 Droplet failure cases); shellcheck clean.
  NOT run on the Droplet.

## 2026-10-16 – Recovery image without private packages + network-free MinIO export (no deploy)
- deploy/recovery/Dockerfile installs deploy/recovery/requirements.recovery.txt (50 prod pins, public PyPI, closure-generated),
  runs `selfcheck --recovery`; check_requirements guards closure coverage, pin equality, private packages, Dockerfiles.
- MinIO export without network (docker exec -i mc cat / read-only docker cp + xl reader); host network; extras classified;
  xl.meta 1.0–1.3, newest version by MTime; present_in_production status.
- Verified locally: clean public-PyPI venv selfcheck 114/114; orchestration E2E 29/29 using that venv; backend 321 passed.

## 2026-10-16 – check_requirements host-independence (no deploy)
- Root cause: checker used importlib.metadata of the running (host) interpreter. Now static stdlib-only mode with committed
  locks (prod 78 / recovery 50, generated in clean --no-deps venvs, sha256 freshness); --in-env inside images; deploy.sh and
  recover.sh run static → build → in-image checks. jsonschema 4.26.0 needs no pyrsistent.

## 2026-10-16 – selfcheck independent of environment (#23, no deploy)
- Root cause of Droplet 76/114: app/db.py built the engine at import (needs DATABASE_URL); pod passed because config.py
  loads backend/.env. Engine/sessionmaker now lazy; selfcheck imports in a scrubbed, network-blocked child with a documented
  build profile and classified failures; root .dockerignore excludes **/.env. Recovery 114/114 + prod 107/107 under env -i,
  10 new negative tests, full workflow (scrubbed recover.sh env) PASS, suite 336 passed. Real docker build not run (no daemon).


## 2026-10-17 – Droplet rehearsal failures (commit 9b7b7f7, plan e4c831f4a432b3b4; no deploy)
- Probes now run inside rehearsal-backend (127.0.0.1:8001, `up --wait` + healthcheck, env_file = production env + scratch
  overrides) with netdiag diagnostics. SSO e2e: full redacted transcript, public callback delivered to the rehearsal backend
  (production never contacted), separate login/callback/access/denial/logout/demo/role-switch steps, operator probe account
  (RECOVER_E2E_USER + RECOVER_E2E_PASSWORD_FILE), Keycloak link into the scratch DB only, faked-pass removed.
- compose audit → scripts/compose_audit.py; snippet compile tests on 3.11 + 3.12. Frontend audit → scripts/frontend_url_audit.py
  (FAIL/WARN/INFO). Per-record evidence integrity + `--accept-evidence-exceptions`. TOOL_VERSION in the plan hash + rehearsal_gate.
- Orchestration e2e 33/33, suite 359 passed. Real Docker paths (up --wait/exec/inspect) not executed here.


## 2026-10-17 – Rehearsal SSO on an isolated scratch Keycloak (no deploy)
- **Removed:** the operator probe-account path (`RECOVER_E2E_USER` / `RECOVER_E2E_PASSWORD_FILE`) and all production Keycloak admin use in rehearsal. The production `keycloak-migrate` dry run is gone from rehearsal; cutover still runs its own dry run before any change.
- **Inspection:** the credentials CSV is written only by cutover/rotate (0600). It has no role metadata, and no recovery code reads it.
- **New `app/tools/scratch_sso.py`** (`recovery.py scratch-sso prepare|setup|cleanup-users|cleanup-finish|prod-oidc-check`):
  - own `rec_kc_<ts>` DB and role
  - `keycloak_config apply` against the scratch Keycloak
  - ephemeral `rehearsal-e2e-*` user, scratch org, `leadership_viewer`
  - scratch demo launcher
  - cleanup on every exit path, recorded in the report
  - restored-user fingerprint compared before/after
- **`recovery.yml`:** `rehearsal-keycloak` (26.8.1, no ports, project network only). The rehearsal backend uses scratch OIDC values.
- **e2e:** `--forbid-host`, wrong-password counted only as an expected rejection, session handling, Keycloak-session-ended check.
- **Validated:** real pod run, 20/20 SSO steps, cleanup complete. Orchestration E2E passed; full suite 360 passed, 27 skipped. The Docker compose path was static-checked only.
- **Droplet:** `sudo ./recover.sh run` (no inputs).

## 2026-10-17 – Droplet rehearsal bugs: rehearsal backend uvicorn, scratch JWT_SECRET, cleanup order (no deploy)
- **rehearsal-backend:** now builds and runs the production backend image definition (`backend/Dockerfile` + `requirements.prod.txt`) as `ironvision/rehearsal-backend:local`. It is rebuilt and checked in-image on every run, and the build runs `selfcheck --startup` (imports incl. uvicorn + app.main, uvicorn loads the app, health/live 200).
- **Static check:** `check_entrypoints` flags uvicorn missing from the image that runs it.
- **Scratch env:** a full scratch env for app-code commands (per-run JWT_SECRET in 0600 `app.env`, `IRONVISION_DOTENV=0`). `assert_scratch_targets` refuses production DB/Keycloak targets.
- **Cleanup:** `admin.env` is written before any user is created. Cleanup steps run in a fixed order, are idempotent and recorded (users moot when the Keycloak container + DB are gone). New `recover.sh scratch-cleanup`.
- **Validated:**
  - orchestration E2E 41/41, including 4 failure paths and the interrupted-run cleanup
  - full suite 367 passed / 27 skipped
  - real uvicorn start from a clean prod venv
- **Not run:** Docker build/up (no daemon in the pod).

## 2026-10-17 – Prod pin failure at Droplet 79e99af (httptools/uvloop via uvicorn[standard])
- **Pins:** httptools==0.9.0 and uvloop==0.23.0 in requirements.prod.txt.
- **Locks:** regenerated from fresh 3.11 venvs via regen_cmd and now record extras metadata (markers, on_image).
- **Checker:** check_extras (host static), plus extras checks in write-lock and --in-env.
- **Root cause of the blind spot:** --no-deps never installs extras, and pip check can't see requested extras.
- **Validated:** image-faithful venvs (with deps) PASS --in-env for prod and recovery; suite 368 passed; orchestration 41/41.

### 2026-10-18: Droplet scratch SSO demo-login 403 fixed
- **Root cause:** the scratch DB had no `demo@ironvision.ai`. keycloak-migrate --link then planned no demo row, linked 0 rows with rc 0, and the e2e demo login got 403. Issuer, subject, provider and DB were identical on both sides.
- **Fix:** scratch setup seeds the demo sandbox identity (seed_demo_account + provision) in the scratch DB, links through the unchanged migrate path (guarded to scratch DB, Keycloak and issuer), then verifies the exact mapping demo-login looks up and fails setup with a diagnostic if it is absent.
- **Validated:** Droplet 403 reproduced on the pre-fix path; fixed path PASS; orchestration 44/44; suite 370 passed. `/auth/demo-login` and keycloak_migrate unchanged.
- **Follow-up (same day):** demo-account creation is now the explicit cutover step `demo_account` (app.seed.ensure_demo_launcher_sandbox, in the plan hash, run by rehearse and apply alike; restored users/orgs fingerprinted). `keycloak-migrate --link` exits 4 when the demo launcher would map 0 accounts. Cutover runs `recovery demo-check` (Explore Demo 200), and a 403 triggers automatic rollback. Orchestration 46/46.


### 2026-10-18: Droplet rehearsal-20261018t201958 (demo account silently skipped) fixed
- **Root cause:** the recovery container env (`x-recovery-env` only) had no DEPLOYMENT_KIND etc., so demo_account decided "not a demo deployment" without running. The decision now comes from the production env file (recover.sh prod_flags → RECOVER_PRODENV_*), through the same app.seed.demo_launcher_decision. An inconsistent config or missing flags is an error. The inputs are in the plan hash; TOOL_VERSION 2026.10.18-rehearsal-v4-demo-account-env.
- **Also fixed:** cutover verify/rollback needed JWT_SECRET in the container (now process-local in the tool). Added a persistence check after the step, an order guard before the link, and the ISSM-token e2e. Local py() runs exactly like the container (env -i + x-recovery-env).
- **Validated:** orchestration 47/47; suite 378 passed.
