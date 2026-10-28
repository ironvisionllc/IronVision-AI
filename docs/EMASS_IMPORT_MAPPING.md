# eMASS System Import & Migration – field mapping

All imports run through the shared eMASS import sessions (`services/emass_reports.py`, `services/emass_import.py`, migration `0031`,
`/api/v1/emass-imports…`), with the new types in `services/emass_migration.py`. Every file is treated as untrusted:

- Only .xlsx/.xlsm/.csv are accepted. Limits are 10 MB, 120 MB uncompressed (ZIP-bomb guard), 40 sheets and 10,000 data rows.
- VBA is never loaded and formulas are never evaluated (cached values only).
- The original file is stored in tenant-scoped object storage at `emass-import/<org>/<system>/<sha256>/<name>`.
- Every applied field records the file, sheet, row, column, session, user, time, file name and SHA-256 in the audit `details.provenance`.
- **Default:** imported values win. Valid changes are preselected "Use imported". Per field, per item, per section or globally you can switch to "Keep existing".
- **Revert:** SLCM, Categorization and PPSM sessions can be reverted, either whole or item by item, and every revert is audited.
- **Idempotent retry:** re-uploading a file with the same SHA-256 after it has been applied reports `duplicate_of`. Its values already match, so nothing new is proposed.
- **Exports:** SLCM and PPSM exports neutralize formula/CSV injection by prefixing `= + - @ TAB CR` with `'`. Re-import strips that prefix again, so a round trip makes no change.

Sample templates (supplied by the customer) are stored in `backend/tests/fixtures/emass/`. The supplied blank TR template and HW/SW template
are byte-identical (SHA-256 `8cb7cb8a…`, `e4f7f1d2…`) to the fixtures already used by the existing importers.

## In scope

### Test Results (`BLANK_TRExport.xlsx`) → Assess
The existing TR parser (`services/tr/xlsx.py`) is unchanged.

- Rows become historical eMASS test results (Compliance Status / Tested By / Date Tested).
- They **never** change the app's SCA approval status. The SCA approves each row (separation of duties).
- Export / round trip uses the existing TR export (`/test-results`).

### SLCM worksheet (`System-Level Continuous Monitoring Plan Worksheet (v1.3).xlsm`) → Select S-5 / Monitor

| Sheet | Discovered columns |
|---|---|
| READ ME FIRST | guidance text + a mirror of the control list (ignored) |
| **Final Results** (preferred) | Sort # · Control Acronym · Control Title · Criticality · Frequency · Method · Reporting · Tracking · SLCM Comments · Order # |
| All Security Controls (fallback) | Security Control # · Security Control Name · Enhancement · Comments · Criticality · Frequency · Method · Reporting · Tracking · SLCM Comments · Order # |

Values seen:

- Criticality: CRWG Red / Yellow / White Criticality Control
- Frequency: Annually, Constantly, Monthly, Quarterly, Weekly
- Method: Automated, Manual
- `---` = empty

| Column | Target | Rule |
|---|---|---|
| Control Acronym / Security Control # | `control_assignments.control_id` (lookup) | Controls not assigned to the system go to the exception queue ("not in system"). Duplicates: first row is used. |
| Criticality | `emass_control_fields.slcm_criticality` | free text ≤ 2000 |
| Frequency | `emass_control_fields.slcm_frequency` | must be an eMASS frequency (Constantly … Every Three Years, Undetermined) |
| Method | `emass_control_fields.slcm_method` | Automated / Semi-Automated / Manual / Undetermined |
| Reporting | `emass_control_fields.slcm_reporting` | ≤ 2000 |
| Tracking | `emass_control_fields.slcm_tracking` | ≤ 2000 |
| SLCM Comments | `emass_control_fields.slcm_comments` | ≤ 4000 |

- **Default: "Save as strategy draft + per-control exceptions".** The worksheet builds the system's Continuous Monitoring Strategy as a DRAFT (`iscm.save`, same as the S-5 editor):
  - system default per field = the most common value (only a value shared by at least 2 controls);
  - family profiles where a family's most common value differs from the default;
  - shared-value control-list profiles (for example one CRWG criticality tier), each covering at least 3 controls, at most 6 of them;
  - per-control overrides **only** where a control still differs from its resolved profile or default (same resolver: override, then first matching profile, then default).
  - The preview shows "N defaults, M family profiles, [T shared-value profiles,] K per-control exceptions". The real v1.3 worksheet (70 controls in a Moderate system) gives 6 defaults, 3 family, 5 shared-value profiles and 12 exceptions, where it used to give 70+ overrides.
- Resolver semantics are unchanged: only the **approved** strategy feeds controls and exports. Draft defaults and profiles take effect when the ISSM approves the strategy. Exceptions apply immediately. An existing old override on a field that the strategy now covers is cleared, so the strategy value applies after approval.
- Existing strategy handling:
  - Existing non-import profiles are kept, after the imported ones.
  - An approved strategy gets a new draft version, and its approved snapshot stays in effect.
  - If a strategy is pending approval, it cannot be edited. In that case values are applied per control and the preview says so.
- **Option: "Apply as per-control values now"** (`POST …/apply?slcm_mode=per_control`) keeps the earlier behaviour: every imported value becomes an override immediately. After approval, "merge overrides equal to the strategy" removes the redundant ones.
- Original values stay on the import session with sheet/row/column provenance, and in the `emass.slcm_strategy_drafted` and `emass.slcm_imported` audit events.
- Revert restores the strategy exactly as it was before the import, or deletes it if the import created it. This works only while the strategy is still a draft.
- Ignored columns: Sort #, Order #, Control Title, Comments, Enhancement.
- Export: `GET /systems/{id}/emass-exports/slcm` (Final Results layout).

### Hardware/Software List (`HWSWList_Template - eMASS 3.xlsm`) → Inventory
The existing HW/SW importer (`services/inventory/hwsw.py`) is unchanged.

- Macros are never run.
- Changes stay proposals until a second person approves them.
- Export / round trip uses the existing inventory export.

### Categorization template (`Categorization Tempalte.xlsx`) → registration + Categorize proposal

| Sheet | Discovered layout |
|---|---|
| Step 1 - Instructions | guidance (ignored) |
| **Mission Types** | Row 1: Package (B), Security Category C/I/A as formulas (D–F). Row 2: Date. Row 4 header: Mission Type · (sub-type) · Applicability · Confidentiality · Integrity · Availablilty [sic]. Rows 5–122: mission categories (col A) and sub-types (col B). Data validation `Yes, No` on Applicability (C7:C122). |

| Source | Target | Rule |
|---|---|---|
| Rows with Applicability = Yes | `systems.environment_detail.emass_mission_types` (list "Category – Sub-type") | Recorded only. SP 800-60 information types are still chosen in Categorize. |
| C/I/A of applicable rows | a **categorization proposal** (`categorization_records` revision) | Computed by the app as the high-water mark. The template's cached formula values are not trusted. "National Security" header rows are ignored. The import **never** writes `systems.*_impact` or `systems.categorization`. |
| Package (B1) | registration pre-fill `name` | Placeholders ("Insert Package Name") are ignored. |

- Apply always goes through the existing revision flow (`rmf_accuracy.record`):
  - No approved record: a **draft** revision is created.
  - Approved record exists: a revision **pending AO re-approval** is created, and the approved record stays in effect.
- The system's C/I/A change only when the AO approves the revision (`POST /systems/{id}/categorization/records/{rid}/approve`). After that, the usual FIPS 199 / CNSSI 1253 baseline proposal follows in Select.
- Each mission type is kept as a row in the revision, so the approval check finds information types. Existing SP 800-60 types are kept.
- Revert withdraws an unapproved revision: it is marked superseded and kept for history, and earlier open revisions are reopened.
- With "Register new system", the form is pre-filled and nothing is created until the user submits.

### PPSM Boundaries (`PPSMBoundariesInformationExport_Template - eMASS 2.xlsx`) → system boundary (new `ppsm_entries` table, migration `0036`)

| Sheet | Discovered layout |
|---|---|
| **PPSM** | Rows 1–6 banner and header block: CUI label, Date Exported, Exported By, Information System Owner, System Name, DITPR ID, POC Name / Phone / E-Mail, Date Reviewed, Reviewed By. Labels are in merged A:B, values in merged C:D. Row 7 header: # · Port (Required) · Protocol (Required) · Data Service (Required) · Boundary (Required) · FQDN · Purpose. Data from row 9. |
| Glossary | the 16 allowed boundary values ("1. Ext to DoD GW (In)" … "16. Single AO E2E Tunnel") |
| Instructions | limits: Port / Protocol 20, Data Service / FQDN 100, Purpose 1000; multi-values separated by `;`; "#" = eMASS Asset ID (read-only) |

| Column | Target | Rule |
|---|---|---|
| # (Asset ID) | `ppsm_entries.asset_id` | Record key when present, otherwise port/protocol/data service. |
| Port | `ppsm_entries.port` | required, ≤ 20, 0–65535 or a range `a-b`, or Any |
| Protocol | `ppsm_entries.protocol` | required, ≤ 20, upper-cased |
| Data Service | `ppsm_entries.data_service` | required, ≤ 100 |
| Boundary | `ppsm_entries.boundaries` (list) | required. `;`-separated; each part must match the Glossary by number or text. |
| FQDN | `ppsm_entries.fqdn` | ≤ 100 |
| Purpose | `ppsm_entries.purpose` | ≤ 1000 |

- POC Name / Phone / E-Mail and Information System Owner are **never imported** (person data).
- Export: `GET /systems/{id}/emass-exports/ppsm`, filled into the original template so its data validation and glossary are kept.

### System Details
Unchanged existing importer (name, acronym, eMASS ID, description, organization, system type, mission owner).

- Authorization fields, NSS, categorization and roles are blocked; they appear as proposals only.

## AI assist
- **Default and toggle:** on by default. The organization-level toggle (`PUT /emass-import-settings/ai`, permission `emass.admin`) is audited as `admin.emass_ai_updated`.
- **When it is used:** only when no deterministic header row is found for SLCM or PPSM.
- **What is sent:** header text plus at most 3 sample values per column. E-mails, phone numbers, IP addresses and host names are redacted first; columns that look like person data (name, POC, owner, contact, tested by…) are never sent. The request goes to the configured OpenRouter provider.
- **What it does with the answer:** high- and medium-confidence mappings are used, but the values are **never preselected**, so the user must decide. Low-confidence suggestions are only listed.
- **What it never does:** create assessments, statuses or evidence, or approve anything.
- **With AI off or unavailable:** the deterministic import works unchanged.

## Registration migration wizard
`/systems/new` starts with three choices:

1. **Start from scratch.**
2. **Import an existing eMASS system** – opens the Import Center; System Details and Categorization pre-fill the registration form.
3. **Copy setup from an existing IronVision AI system** – a same-org system the user can read.
   - The registration form is pre-filled from `GET /systems/{id}/setup-template`.
   - After registration, `POST /systems/{new}/copy-setup` copies overlays, tailoring decisions, ODP values (approvals cleared), the ISCM strategy and profiles (as a new draft), and policy links.
   - It never copies assessments, evidence, POA&Ms, test results, approvals or inventory.
   - Audited as `system.setup_copied`.

The completion report is at `/systems/{id}/migration-report` (API `GET /systems/{id}/migration-report`). It shows coverage per file type, the sessions, exception counts and links into each RMF step.

## Manage imported data
Import Center → an applied import → **Manage imported data** (`/import-center/manage/{import_id}`). It is built on the import's own provenance (`apply_results[].undo`); nothing new is stored per field.

- **View:** every imported field (Control Information) or record (PPSM, SLCM, strategy, categorization), grouped by destination. Each one shows the value before the import, the imported value and the current value, plus a "changed after the import" flag.
  - API: `GET /api/v1/emass-imports/{id}/manage`.
  - Per-system list: `GET /api/v1/systems/{id}/imported-data`.
- **Actions:** restore previous value, clear field, or delete imported data (only for data the import created). Actions can apply to selected items, a whole group, or the whole import with exclusions.
  - API: `POST /api/v1/emass-imports/{id}/manage {action, ids | all + exclude, force}`.
  - Each item gets its own result, so one failure does not stop the others.
  - A field edited after the import is skipped with `needs_confirm`. It is only overwritten with `force=true`, after the user clicks "Overwrite anyway".
- **Safeguards:**
  - Writes go through the normal save paths (validation, status mapping, audit).
  - Implementation statements get a new draft version. If an approved statement is affected, it is flagged for re-review.
  - Nothing is ever approved by this page, and evidence files are never touched.
  - The compliance evaluation is recomputed, so dashboards, exports, eMASS and OSCAL reflect the change.
- **Undo:** each operation can be undone for 30 days (`POST /api/v1/emass-imports/{id}/manage/{op_id}/undo`). Field values are put back and deleted PPSM rows are re-created. Record-level restores are undone by re-applying the file.
- **Audit:** events `import_data.restore`, `import_data.clear`, `import_data.delete` and `import_data.undo` record the import id, SHA-256, entries and failures. The audit history is never deleted.
- **RBAC and tenancy:** actions follow the import's section permissions; the SCA, for example, gets a read-only view. Another tenant's import returns 404.


## Deferred
- **Control Information** and **POA&M** imports are deferred for the migration.
- Their existing parsers, endpoints and tests are unchanged and keep working.
- They are excluded from the Import Center migration list, the migration wizard, the round trips and the completion-report coverage, where they are listed as "deferred".

## Known limits
- The SLCM strategy-level defaults (S-5) are not derived from the worksheet; it is applied per control only.
- eMASS mission types are not mapped to SP 800-60 information types automatically.
- PPSM rows are not linked to HW/SW assets.
- Compatibility with live eMASS exports beyond the supplied templates is pending verification.
