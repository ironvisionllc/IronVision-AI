# SME test findings – Section 5 (inheritance)

Preview: https://aegis-rmf-demo.preview.emergentagent.com. Browser check account: `sme-s3-9bb8b8@example.com` / `Sme-S3-2026!x` (clean sign-up, system S3P).
Screenshots: `docs/screenshots/sme-section5/`. The Droplet was not touched.

| # | Root cause | Change | Files | Click path |
|---|---|---|---|---|
| 24a Bulk Inherited / Shared | Only a one-control-at-a-time "Assign" modal. | **Bulk-set inheritance**: filter, select all shown or tick, choose Inherited / Shared / System and the provider (required for inherited/shared), plus optional responsibility text for all selected. One action, one audit entry (`inheritance.bulk_updated`). Inherited controls are set to implementation "inherited"; switching back resets them to planned. Next step → document shared controls. | services/crm.py (`bulk_set`), api/v1/phase3.py `POST /systems/{id}/inheritance/bulk`, components/inheritance/CrmImport.tsx (`BulkInheritance`) | Implement → Inheritance → Bulk-set inheritance… |
| 24b CRM import | The CSV-only import required exact column names, had no preview or row-level feedback, and **did not update this system's controls** (it only filled empty text). | A wizard: upload **CSV or XLSX** → **column mapping** (auto-suggested from common header names such as "Control", "Type", "CSP Responsibility", "Customer Responsibility"; editable) → **preview**:<br>• per-row change for this system (e.g. "system → shared", "unchanged", "not in this system");<br>• **row-level errors**: bad responsibility, duplicate, shared without both texts.<br>→ **Apply**: valid rows only; updates the provider matrix and this system's assignments; audited as `provider.crm_applied` with file, mapping and controls.<br>A **SAMPLE** template (synthetic, labelled "SAMPLE" in every row) can be downloaded. The old endpoint is kept. | services/crm.py, phase3.py (`/providers/{id}/crm/preview`, `/crm/apply`, `/crm/sample.csv`), CrmImport.tsx (`CrmImportModal`). XLSX is read with the Python standard library (zip + XML), so no new dependency enters the prod or paused recovery lockfiles | Inheritance → provider row → Import CRM (CSV / Excel) |
| 24c Provider record + expiry warnings | The provider had no authorization type; the expiration date was shown without warnings; inherited rows did not show their provider. | New `authorization_type` (migration 0016) alongside name, package/system and authorization expiration. `expiry_status`: current / expiring (≤90 days) / expired / unknown. A red or amber **banner** names the dependent controls and links to "Update the provider record". The provider table shows the status. Inherited/shared rows show "from Provider (authorization expired)". The bulk picker flags expired providers. | models.py, alembic 0016, crm.py (`expiry_status`), phase3.py (`inheritance` view), Phase3Pages.tsx | Inheritance (banner / table) |
| 24d Plain explanation | Only a technical note. | An explainer panel: **Inherited** = fully satisfied by another authorized package/provider; **Shared** = both parties have responsibilities (the provider part plus a system part that this system must implement and evidence); **System-owned**. | Phase3Pages.tsx | Inheritance (top) |

## Tests
- `backend/tests/test_sme_section5.py` (5):
  - Provider authorization type and expiring/expired status.
  - Bulk inheritance needs a provider and reports unassigned IDs.
  - CRM preview auto-mapping, row errors and change labels, missing-column check.
  - XLSX apply updates controls and is audited.
  - The sample is labelled SAMPLE.
- Browser:
  - Expiry banner: "expires in 20 day(s)".
  - Bulk set 19 PE controls → inherited.
  - CRM CSV preview "Changes: 2 … Row errors: 1" (row 4 `au-6 maybe` → plain error).
  - Apply → "CRM applied …: 2 control(s) updated, 1 row(s) with errors skipped" + Next step.
- Full suite after Section 5: 447 passed; the 5 failures were from a `pip freeze` that pulled unrelated packages – reverted, and the XLSX reader rewritten without a new dependency. Requirements, env-lint and root-deploy tests then passed: 43/43.
