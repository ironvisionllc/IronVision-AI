# 2 · Connectedness audit ("should flow" links)

How this was checked: code inspection of the services named below, the Phase-1 task runs (`data/baseline_metrics.json`), and pass A–C tester results.

| Should flow | Today | Exact gap |
|---|---|---|
| eMASS TR import → Assess workspace | **Partial** | eMASS Test Results go through the existing TR pipeline (`services/emass_reports.py` → `services/tr/*`). They are stored as historical results and never change SCA approval, which is correct. But they show on `/test-results` and the control history, not in an SCA assessment queue, because there isn't one (complexity #5). No "assess these controls next" after import. |
| SLCM → strategy + schedules | **Works (strategy) / Partial (schedules)** | Since pass C, SLCM builds a draft strategy with defaults, profiles and exceptions (`services/emass_migration.py: slcm_plan`). Schedules (`iscm.py` due/overdue, `/rmf/monitor`) use only the **approved** strategy. Until the ISSM approves, Monitor shows "Never monitored" and no notice links it to the pending draft. |
| Policy upload → mapping suggestions | **Works** | Policy Auditor v2 → `/mapping-review` (Policy mappings tab). Gap: the control's Workbench page does not show "3 pending policy suggestions"; you must know to open Mapping Review. |
| Approved mapping → control coverage (never the assessment) | **Works** | `policy_coverage.approve` updates policy coverage only; assessment untouched (pass rounds 3–5). Gap: the coverage label shares a colour and position with implementation status (complexity #12). |
| ACAS → findings + assets + POA&M | **Partial** | `ingest/pipeline.py` creates and updates findings and matches assets to inventory; ambiguous hosts go to review. POA&M is **not** created: only `poams_closure_eligible` is reported, and creation is manual "Add to POA&M" on each finding. There is no "N new findings without POA&M → create" step. |
| Categorization change → baseline review notice | **Works (FIPS, pass C) / Works (CNSSI proposal)** | `rmf_accuracy.baseline_review` gives a notice in Select plus a review flag. Gap: it is not on a system dashboard (none exists) and not in the ISSM/ISSO "My Work". |
| Completed assessment → package readiness | **Partial** | `services/documents.py` lists "N of M controls have no SCA assessment record" as missing information **when a document is generated**. There is no persistent readiness meter. The package page shows no live blocker list. |
| Evidence → discoverable wherever relevant | **Partial** | Evidence appears on the control (Workbench), the Ledger and ingest runs. Not visible in the finding, POA&M detail (only via links) or the assessment step. Freshness only shows in the Ledger and Monitor. |
| Implementation Plan import → Implement + next-action guidance | **Partial** | The import applies to the Workbench (pass B/C round trip). The completed screen shows counts and blocked rows but **no next action** (metrics: next_action_shown = false). Nothing says "6 controls blocked – missing SLCM fields → open the strategy" or "38 controls still have no statement". |

## Duplicated data copies / duplicate entry points

| Data | Copies / entry points | Proposal |
|---|---|---|
| Information types and PII | Registration form **and** Categorize (`SystemsPage.tsx`, `CategorizeForm.tsx`). Same record, entered twice. | Registration asks name, acronym, type and owner only. Categorize owns info types and PII. |
| Inheritance / designation | `/inheritance` **and** Workbench advanced "designation" | Single editor on the control; `/inheritance` becomes a bulk view of the same field. |
| Assets | `/inventory` **and** System detail "Asset inventory" (same table, two UIs) | One Inventory under Prepare. |
| Categorization summary | Categorize **and** Select step 1 | Select shows a read-only chip linking to Categorize. |
| SSP/SAR/RAR generation | Implement, Assess, Authorize, Authorization package | One "Package & documents" page under Authorize. |
| Imports | Import Center, eMASS import, Test Results "Import from eMASS", eMASS Sync | One Import Center flow (old buttons already open it, pass B). |
| Help | `/help`, `/docs-center` | One Help, with role matrix as a section. |

No **data** is stored twice for the items above. Each UI writes the same record. The issue is duplicate *entry points*, which make users unsure which is authoritative. The exceptions are mission types and assets: they are visible in two UIs but stored once.
