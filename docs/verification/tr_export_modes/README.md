# eMASS Test Results export modes – verification (October 2026)

**Result: both modes PASS.** The evidence comes from running the real workflows and diffing every cell of the output against the input. Code intent was not used as evidence.

**Inputs:**
- The real fixture `backend/tests/fixtures/emass/BLANK_TRExport.xlsx`.
- A synthetic sandbox system: Moderate baseline, STIG checklist ingested, sandbox signup org.
- SCA-approved rows created via `POST /api/v1/tr/workbooks/{id}/decide`.

This is **not** a claim of official eMASS compatibility. Opening the files in Microsoft Excel and importing them into a real eMASS instance remain human steps.

## Where each mode is selected and implemented
| What | File:line |
|---|---|
| Column roles are detected by header text. Result roles pick the "Enter Test Results Here" group (M–P) over the read-only "Latest" group (Q–T). | `backend/app/services/tr/xlsx.py:95` (`detect`), `:118` |
| Blank template: rows are generated from the system (only when the template has no rows) | `backend/app/services/tr/service.py:157` (`populate_from_system`), called at `:186` when `populate=true` (`api/v1/tr.py:172` → `worker/handlers.py:161`) |
| Mode selection: `blank` if every row was generated, otherwise `prepopulated` | `service.py:441` (`export_mode`), used at `:350` |
| Mode 2 only: identifiers A/F/G/H are written on generated rows | `service.py:353-357` |
| Both modes: M–P are written only for `approved` rows with `tester_confirmed` | `service.py:359-367` |
| Byte-copy writer: only the listed cells change | `xlsx.py:205` (`write`), called at `service.py:369` |
| Built-in proof, permitted ranges, outside-permitted check | `xlsx.py:236` (`verify`), `service.py:446` (`permission_report`) |
| **New:** validation report sections `mode_explanation`, `modified_columns`, `row_counts`, `rows_not_populated` (with reasons), `unmatched_controls`, `controls_not_in_system`, `system_controls_without_template_row` | `service.py:396` (`rows_report`) |
| Tester/date rules: both required, date not in the future, tester length limit | `backend/app/api/v1/tr.py:195-207` |

## Results – from the independent diff (`backend/tests/xlsx_diff.py`)
The diff compares:
- every cell's value, data type, style and number format (formulas included);
- merged cells, data validations, conditional formatting, column widths, row heights and freeze panes;
- sheet-level and workbook-level defined names, and the sheet list and order;
- every other part of the zip package, byte for byte.

| | Mode 1 – populated template | Mode 2 – blank template | Mode 2 output re-uploaded (Mode 1) |
|---|---|---|---|
| Mode reported | prepopulated | blank | prepopulated |
| Template rows | 7 | 1,698 generated (rows 7–1704) | 1,698 (read from the identifiers) |
| Rows written (M–P) | 2 | 4 | 1 |
| Columns changed (diff) | **M, N, O, P** (2 cells each, rows 7–8) | **A, F, G, H** (1,698 cells each, rows 7–1704); **M, N, O, P** (4 cells each, rows 7–10) | **M, N, O, P** (row 17 only) |
| Header rows 1–6 | unchanged | unchanged | unchanged |
| Other sheets (Example, Assignment Values, Instructions) | unchanged | unchanged | unchanged |
| Structure (merges, validations, CF, widths, names, sheet order) | unchanged | unchanged | unchanged |
| Zip parts changed | only `xl/worksheets/sheet1.xml` (Template) | same | same |
| Formulas / formatting in A–L and after P | `E7` `=A7&" narrative"`, `U8` `=LEN(P8)`, bold `B7`, fill `V8`, width of U: all preserved | n/a | n/a |
| Unmatched | ZZ-1 (not in catalog); AC-10 (in catalog, not in the system's control set) | none | none |
| Not populated (with reasons) | row 9: old approval without tester confirmation; rows 10–11: no SCA-approved result; row 12: control not in system; row 13: unmatched | 1,694 rows: no SCA-approved result; row 11: unconfirmed approval excluded | 1,697 |

**Mode 2 reference data check.** On every generated row:
- Column A equals the control acronym.
- `F` = `<control>.<n>` (AP number **derived** and flagged `derived_ap`, because a blank template has no AP numbers).
- The `G` CCI maps to that control in the DISA CCI list.
- `H` matches `Cci.definition` from the loaded reference data exactly.
- Row count = the sum of CCIs across all assigned controls (1,698).

**M–P rules checked:**
- Only SCA-approved rows were written.
- The tester and date are the values the SCA entered per row, not the approver and not today.
- A future date was rejected with 422.
- Approvals without tester confirmation were excluded in both modes.

## Files here
- `mode1_input_populated_template.xlsx`, `mode1_output_populated_template_export.xlsx`, `mode1_diff_report.json`
- `mode2_input_BLANK_TRExport.xlsx`, `mode2_output_blank_template_export.xlsx`, `mode2_diff_report.json`
- `mode2_roundtrip_output.xlsx`, `mode2_roundtrip_diff_report.json`

Each `*_diff_report.json` contains:
- the mode and its explanation;
- modified columns, both from the export's validation report and from the diff (they agree);
- row counts and the unmatched/not-populated rows with their reasons;
- structure, zip-part and other-sheet changes, plus a sample of the changed cells.

To regenerate: `cd backend && TR_VERIFY_OUT=../docs/verification/tr_export_modes python -m pytest -n 0 tests/test_tr_export_modes.py`

## Guard tests
`backend/tests/test_tr_export_modes.py` runs in the normal suite and is marked `guard`. It fails if any future change writes outside the permitted columns or rows, touches a header or another sheet, or changes structure.
- `test_guard_mode2_blank_only_A_F_G_H_and_M_to_P`
- `test_guard_mode2_identifiers_match_reference_data`
- `test_guard_mode1_populated_only_M_to_P`
- `test_guard_mode1_matching_and_unpopulated_report`
- `test_guard_mode2_output_roundtrip_as_populated_template`
- `test_guard_diff_catches_writes_outside_permitted_columns` (self-test: writes to L7, Q7, M6 and to the Example sheet are all caught)

**Matching note.** Rows are matched on the template's own identifiers: AP Acronym + CCI, with Control Acronym used when the AP Acronym is empty. Uncertain matches are never written; they are listed for review.
