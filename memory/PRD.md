# IronVision AI – PRD (living)

## Original problem statement (latest phase)
- **Item A:** Remove the login-page link "Read the IronVision AI whitepaper (PDF / DOCX)". The public pages stay.
- **Item B:** One shared "eMASS report import" that covers five report types:
  - System Details / registration
  - Control Information
  - Test Results
  - POA&M
  - Hardware/Software List
- How the import works:
  - The report type is detected from sheet names and headers.
  - The user sees the confidence and can override the type.
  - The user is asked what to do with the file, with or without a system selected, and is warned when the file names a different system.
  - All changes go through one grouped review screen, and nothing is saved until the user clicks Apply.
- Rules that must hold:
  - Permissions are checked per section.
  - Every applied change is audited with the file's SHA-256.
  - Test Results stay proposals until the SCA approves them.
  - HW/SW macros are never run.
  - Every import is labelled "compatibility pending verification against a real eMASS export".
  - Sample files are SYNTHETIC only.

## Architecture
- FastAPI + React/TS + PostgreSQL + worker, with object storage.
- Shared import:
  - Service: `backend/app/services/emass_reports.py`
  - Routes: `/api/v1/emass-imports…`
  - Migration: `0031`
  - UI: `EmassImportPage.tsx`, `ImportPrompt.tsx`, `ImportReview.tsx`
- Apply reuses the existing services:
  - Control Information: `emass_fields.save_plan`
  - POA&M: `workflow.create_poam`
  - Test Results: `tr.service.import_workbook`
  - HW/SW: `inventory.hwsw.upload`

## Implemented
- 2026-10: eMASS Implementation Plan / Risk Assessment fields (0029); Test Results export modes verified; login whitepaper link removed.
- 2026-10: Control Information import (0030), commit 96dbdee.
- 2026-10: Shared 5-type eMASS report import (0031), commits d151be6 + follow-up:
  - Prompts for both entry points (from a system, or from the global import).
  - Mismatch warning, including when the eMASS IDs differ.
  - Register a new system by pre-filling the registration form (no auto-create).
  - Grouped review and audited apply.
  - Upload needs a write permission.
  - Cancel and register are audited.

- 2026-10-27: Test Plan discoverability + validation, ISCM/SLCM strategy (0032), guided Select flow (0033). Commits d1e33cf, 0a052f9.
- 2026-10-27: UAT remediation, nothing deployed:
  - P1:
    - Server-side bulk review jobs, plus root cause of "still listed" (9fd8be4, 0a62ee0).
    - SCA separation of duties (SoD) lifecycle.
  - P2: Requirement-count rule, single privacy state, one policy-link source (95a9d2e).
  - P3 / P4 / P6 (53e6960):
    - Grounded policy fallback.
    - Draft states.
    - SSP/SAR/RAR as DOCX and PDF.
    - POA&M eMASS risk fields (0034).
  - P5: STIG source-vs-app viewer and TR XLSX warnings (e9832a4).
  - Iteration-21 fixes (latest commit).

## Backlog
- P7: Resume the remaining SLCM/ISCM and guided Select polish.
- P1: Confirm which commit the Droplet runs (`git log -1`), then redeploy current HEAD.
- P1: Pre-existing failure: `test_root_deploy::test_existing_env_with_unquoted_scopes_is_fixed_then_deployed` fails at HEAD before these changes.
- P1: Verify each type against real eMASS exports (SME), then adjust the header aliases.
- P1: Look into the flaky test `test_tr.py::test_prepopulated_mode_leaves_a_to_l_untouched` (fails sometimes under xdist).
- P2: Apply Categorization and Roles proposals through the Categorize and Key roles steps.

## 2026-10-27 – UAT remediation (security + items 3–8 + P7), not deployed
- Security: tenant scoping on /audit-events, /jobs, /jobs/{id}, admin access-history, demo evidence/attestation endpoints; full OpenAPI cross-tenant sweep (298/301 ops, 1480 requests, 5 personas, 0 leaks, 0 tenant-A writes). Assessment: docs/SECURITY_INCIDENT_ASSESSMENT_audit_events.md.
- SCA reject/approve assessments with cited evidence; bulk review jobs on a dedicated worker lane; policy AI refinement 4 concurrent + timing_s.
- POA&M audit before/after; SSP/SAR/RAR generate panels (Implement/Assess/Authorize/package); SYNTHETIC demo statements (sandbox only); /api/v1/health build SHA/time + Admin.
- P7: selection_review approval freezes approved control list + drift; SLCM due in-app notifications.
- Serial suite: 872 tests, 755 passed, 0 failed, 117 skipped (live-only).
- Remaining: browser verification of document panels and 942-item UI workflow (awaiting root go-ahead); raw storage-key probe; time a real 284-control analysis; trace idle-in-transaction app connection.

## 2026-10 eMASS pass-B fixes (commit eea0382)
- SLCM import builds ISCM strategy DRAFT (defaults, family + shared-value profiles, per-control exceptions only); takes effect on ISSM approval; optional per-control mode; revert restores/removes draft.
- Categorization import creates AO categorization proposal (draft / pending_reapproval); never writes C/I/A.
- One type dispatcher on per-system, global+target and Import Center uploads; detection returns sheets + record_count.
- /pii count fixed (53 FIPS); migration report xlsx export links.
- Pending: root tester pass C.

## 2026-10 pass-C items (commit b7559ce)
- .txt/.md classified as policy only with policy-like content (score >= 3); otherwise 'Not recognised' + 'Import as policy anyway' override.
- Select shows 'Categorization changed – review baseline' notice/review flag after AO approval; baseline never auto-changed (FIPS); CNSSI keeps its proposal flow.
- Full serial suite (8 sequential shards, -n 0): 876 passed, 117 skipped, 0 failed. Tenant suites: sweep 4/4, full 1/1.

## 2026-10-28 – UX redesign R1–R7 (UI/workflow only, nothing deployed)
- R1 navigation: My Work · Systems · Import Center · Help · Admin + 7 RMF steps (header opens step, chevron expands); old routes kept (route-walk test `frontend/src/routeWalk.test.ts`); system dashboard, My Work per role, recently viewed.
- R2 Workbench: list + 2 primary filters (rest under "More filters", saved per system), 6 control tabs, glossary status chips; removed `wb-export-emass-plan` + parameter-comparison buttons (now `param-compare-export` in Select step 4, `pkg-export-emass-plan` in Authorize › Package & documents; migration report exports unchanged).
- R3/R4/R6 connectedness: "Completed – next: …" after every import/analysis, SCA workspace, ISSM-approval notice for SLCM strategy, mapping suggestions on the control, Create-POA&M step on scan runs, next-step hints (finding, POA&M, package), one-off evidence upload without a source.
- R6 Guided Mode (per user, off by default, first-login prompt); R7 ⌘K search, Help topics + status glossary.
- Night-mode contrast (token level) – `scripts/check_contrast.py`: 2941 → 0 violations. Wrap/squeeze (shared CSS + ActionBar "More ▾") – `scripts/check_wrap.py`: 4128 → 0. Overflow 147/147.
- Task metrics (12 walks, after usability rounds): clicks 56→45, page changes 21→17, fields 19→14, next action 6/12→12/12, completed 12/12 (`docs/ux/METRICS_AFTER.md`).
- Backend serial suite (8 shards + acceptance, -n 0): 889 passed, 116 skipped, 0 failed after fixing stale LTP/MPP ids in live tests.
- Usability-test round (ISSO, 7/8 pass → fixes): Attach / Link existing evidence on control Evidence tab, finding and POA&M (`POST /systems/{id}/controls/{cid}/evidence-links`, ingest.upload, audited, tenant-tested); Monitor metrics as scoped counts ("Controls with current evidence: X of Y" + "Evidence items within their freshness window: N of M") – root cause: two percentages with different denominators; Workbench jump-to-control, edit-ready Implementation tab, sticky Save, My Work/next-action links carry `?tab=`; "Policy coverage: N of M requirements met" with tooltip; SCA auto-advance toast with Undo + setting; SLCM "no monitoring frequency" fix actions; tab titles "<page> · <system> · IronVision AI"; Categorize shows registration answers as Answered · Edit; Guided Mode + SCA auto-advance stored server-side (`/me/preferences`, User.onboarding.prefs) with localStorage fallback.
- Usability round 2 (2026-10-28): Workbench at 390 px – compact two-line rows (ID + status dot / truncated title with tooltip; root cause: flex row button without min-w-0) and a tab select on phones; "Attach evidence" opens an in-app dialog (target control, drop zone + Choose file, progress) → closes with "Completed – next"; SCA moved banner + 12 s toast (pauses on hover); "Save statement" vs "Save status". Wrap checker gained row-wrap + tab-scroll checks, waits for lists, measures content-visibility rows, ignores sr-only text (`scripts/check_wrap_selftest.py` proves the pre-fix markup is caught); the new checks also fixed SCA queue, catalog family rows and Reviews tabs.

## 2026-10-28 – No-silent-misses, Manage imported data, serial suite, demo video, whitepaper v1.1
- Policy Auditor: whole-document default (<60k chars), xx-1 AI check on; compact output built but OFF (POLICY_AI_COMPACT_MIN_REQS=0); truncated/timed-out batches → needs manual review (unit-tested). No further paid AI runs without approval.
- Manage imported data (migration 0039): all import types, grouped by section, restore/clear/delete item/row/section/all (system shell kept), 30-day undo, decision re-review flags, evidence link vs file, TR/inventory export exclusions, tenant isolation.
- Full serial suite green: 1124 passed / 0 failed / 50 skipped (118 files).
- Demo video re-recorded (300 s, 1920x1080/30fps H.264, burned-in captions, no AI calls); old version archived under static/demo/archive/2026-10-24.
- Whitepaper v1.1 (50 pp PDF + DOCX): 25 fresh SYNTHETIC screenshots, Import Center/Manage/no-silent-misses content; old version archived.
- Backlog: optional re-record hiding persona email in header; Excel/eMASS human verification of exports.
