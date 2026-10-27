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
