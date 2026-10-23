# SME test findings – Section 7 (smaller improvements)

Preview: https://aegis-rmf-demo.preview.emergentagent.com. Browser check account: `sme-s3-9bb8b8@example.com` / `Sme-S3-2026!x`.
Screenshots: `docs/screenshots/sme-section7/`. The Droplet was not touched.

| # | Root cause | Change | Files | Click path |
|---|---|---|---|---|
| 26 Page-size selector | The catalog was fixed at 50 rows per page; the API capped `limit` at 500, so "All" was impossible. The Workbench list rendered every row; traceability was capped at 1,500 rows. | A shared `PageSizeSelect` (50 / 100 / 250 / All), **remembered per user** (localStorage key includes the user ID and the table), with a `Pager`.<br>**Catalog:** stays server-side; `/controls` `limit` raised to `le=2000`, so All = one request. Stale responses are now ignored, which fixes a race when switching sizes quickly.<br>**Workbench list and traceability:** client-side paging over the already-loaded list.<br>Rows use `content-visibility:auto`, so "All" stays fast. **Measured: catalog All = 1,014 rows (1,196 with withdrawn) rendered in about 2.5 s end-to-end over the preview network.** | components/common/PageSize.tsx, controls/ControlsTable.tsx, pages/WorkbenchPage.tsx, pages/RmfStepPages.tsx, api/v1/controls.py | Catalog → bottom bar "Rows"; Workbench → All controls → Rows; Tools → Traceability → Rows |
| 27 "Download sample STIG files" | It was in the sandbox Get-started bar. | Done in Section 3/4: it is intentional, so it was kept. It sits under **Evidence Sources → Upload a file** and is labelled **"Sample/test data (SYNTHETIC)"**. | shell/Sandbox.tsx, EvidencePages.tsx | Evidence Sources → Upload a file |

## Tests
- Browser:
  - Catalog All → 1,014 rows in 2.5 s; after reload the selector still says All.
  - 100 → exactly 100 rows.
  - Traceability 50 → 50 rows, "1–50 of 339".
  - Workbench 100 → 100 items, "1–100 of 339".
  - Sample link present under Upload a file.
- Backend catalog/control tests: 10 passed.
