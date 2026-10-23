# TR + AI evidence analysis + HW/SW inventory: report

Recovery stayed paused and the Droplet was not touched. The stack is unchanged (FastAPI / React-TS / PostgreSQL / Docker / Keycloak).

## What was built (Implemented / Mockup / Future)

| Capability | Status |
|---|---|
| TR import of the real `BLANK_TRExport.xlsx`: header-role detection, AP/CCI matching, manual resolution, reusable template | Implemented |
| TR generation from assessments, STIG/ACAS, policy coverage, evidence (freshness), POA&Ms; missing/conflict/stale flags | Implemented |
| SCA-only approval and edit (backend, including bulk), locked explanation for other roles | Implemented |
| Bounded TR export (`Template!M:P` + identifiers of user-added rows) with XML/cell diff validation report | Implemented |
| AI evidence analysis per TR row (on demand + bulk worker job), validated references/quotes, deterministic fallback, "Use this text" | Implemented |
| HW/SW List `.xlsm` import (header detection, vocabularies from `(U) Lists` tables), never overwrites | Implemented |
| Scan host facts (CKL, CKLB, Nessus XML/CSV, XCCDF) → deterministic asset correlation; identifier history; multiple IPs | Implemented |
| Consistency checks: missing from inventory, no scan, conflicting hostname/FQDN/MAC/OS/IP, software version vs CPE, duplicates, likely duplicates, shared IP, stale scans, eMASS rule 6 | Implemented |
| Proposal → approval → audit for every inventory change; ignore with a reason; create asset from a scan | Implemented |
| AI ranking of ambiguous correlations and explanation/ranking of discrepancies (validated, suggestion only) | Implemented |
| HW/SW export into the same template (VBA + 3 signature parts byte-identical) with validation report | Implemented |
| "Potentially related" open findings across assets (proposal only), benchmark/CPE/OS "applies to" | Implemented (asset detail API; not shown in the UI table) |
| Software↔asset assignment in the UI, merging duplicate assets, OS-level vulnerability applicability | Future |

## Automated tests (all run in this pod)
- Backend full suite (`pytest tests`): **540 passed, 43 skipped, 0 failed**.
  - New: `test_tr.py` 25, `test_tr_analysis.py` 6, `test_inventory.py` 11.
  - `test_route_authz.py` now also covers the TR and inventory routes.
  - `test_legacy_project.py` needs SeaweedFS running (`scripts/pod_seaweedfs.sh`); after the pod restart it had to be restarted.
- Frontend: `tsc --noEmit` clean; `yarn test` **6 passed / 6**.
- AI tests use a **mocked AI provider**. They cover:
  - fabricated reference rejected; fabricated quote rejected;
  - AI output with `compliance_status`/`tested_by`/`date_tested` rejected by the schema (deterministic stands);
  - `use-analysis` with those fields → 422; an ISSO editing the status → 403;
  - deterministic fallback labelled correctly;
  - Open STIG vs Compliant assessment → conflict (kept even if the AI omits it); stale evidence flagged;
  - analysis alone leaves the export byte-identical; applied text is exported only after SCA re-approval;
  - tenant isolation.
- Inventory tests (real `.xlsm` template + synthetic CKLs) cover:
  - deterministic hostname match; shared IP → review; IP conflict → review;
  - each consistency kind;
  - no overwrite without accept + approve (audited before/after);
  - create-asset needs approval;
  - AI rank drops a fabricated candidate and unsupported identifiers, and creates no Finding/Asset;
  - confirming a correlation leaves finding IDs/asset/dedup/evidence unchanged;
  - export keeps VBA and package parts identical and writes only permitted cells;
  - MOCKED labelling; tenant isolation.
- Independent testing agent (iteration 14): 100% backend, 100% frontend in scope. One React `<option>` warning in the TR selector was fixed.

## Manual demonstration (jordan.qa7731, QA Payroll System, synthetic data)
Screenshots are in `docs/screenshots/tr/` (1–8) and `docs/screenshots/inventory/` (01–04).
- **TR:** the real blank template was imported. Mapping detected `Template!M–P`. 1,679 rows were added from the system's controls. The SCA approved rows ("Brooks, Dana"). Export v1 validation passed, with changed cells only in permitted columns.
- **AI analysis (real call):** provider emergent, model `claude-sonnet-5-5`, prompt `tr.evidence_analysis@1.1.0`, 0 references dropped. "Use this text" set the row to *edited* with the "AI suggestion applied, edited" badge, which needs SCA re-approval.
- **Inventory import:** a synthetic HW/SW workbook built from the real `.xlsm` template (6 HW, 3 SW) gave 9 created and 2 scan hosts linked deterministically.
- **Synthetic CKLs:** `nat-gw` on shared IP 192.0.2.50 went to review. The real AI ranking said neither candidate is convincing; the ISSO confirmed app-01 with a justification. A FQDN/MAC conflict went accept → approve → applied. The AI explanation of the likely duplicate concluded the two are probably distinct.
- **Inventory export v1:** 135 cells, validation passed. `vbaProject.bin` and all signature parts are identical to the template.

## HUMAN_REQUIRED (not verifiable here)
1. Open both exported workbooks in Microsoft Excel (macros disabled): no repair prompt; dropdowns still work.
2. Import the TR export (Assessment → Test Result Import) and the HW/SW export (Hardware/Software → Import) into eMASS.
3. Spot-check three rows of each in eMASS.

## Mocked
- Evidence connector `MockAdapter` data is labelled **MOCKED source**.
- STIG/ACAS demo files are **SYNTHETIC**.
- The AI provider is **mocked in pytest** only; preview used real calls.

## Changes
- **Migrations:** `0019_tr_workbooks`, `0020_tr_analyses`, `0021_inventory`. All are additive with a downgrade; `0021` adds 6 nullable columns to `assets` plus 6 tables.
- **Backend:**
  - new: `services/tr/{xlsx,service,analysis}.py`, `services/inventory/{correlate,consistency,hwsw,ai}.py`, `api/v1/{tr,inventory}.py`;
  - prompts `tr.evidence_analysis@1.1.0`, `inventory.correlation_rank@1.0.0`, `inventory.discrepancy_explain@1.0.0`;
  - `parsers.asset_facts`; `pipeline._match_asset` now delegates to the correlation engine;
  - worker jobs `tr.detect/generate/analyze`, `inventory.import/check/ai`;
  - `security/deps` tenant check via the owning system for TR/inventory objects;
  - Mapping Review `asset_correlations_pending`.
- **Frontend:** `TestResultsPage.tsx`, `InventoryPage.tsx`, routes `/test-results` and `/inventory`, nav entries, Mapping Review banner.
- **Dependencies:** `openpyxl==3.1.5`, `et_xmlfile==2.0.0`. Added to `requirements.txt` and `requirements.prod.txt`, with the prod lock regenerated in a clean venv. Also added to `deploy/recovery/requirements.recovery.txt` and its lock: **strictly needed**, because the recovery target imports the backend app and the host check failed without it. `scripts/check_requirements.py` passes.
- **Env variables:** none new. **Deployment steps:** `alembic upgrade head` (0019–0021); rebuild the backend and worker images.
- **Not part of this work:** older uncommitted edits to `deploy/digitalocean/.env*.example` were left uncommitted.
- **Test fixtures only:** `backend/tests/fixtures/emass/` (copies of the two templates). There is no demo seed data from the templates.
