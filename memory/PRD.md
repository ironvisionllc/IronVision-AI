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
