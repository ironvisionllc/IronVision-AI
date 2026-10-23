# Official CNSSI 1253 overlays + independent-test fixes

Preview: https://aegis-rmf-demo.preview.emergentagent.com. Browser check account: `jordan.qa7731@example.com` (existing clean account, no new sign-up). Screenshots: `docs/screenshots/sme-overlays/`. The Droplet was not touched.

## A1. Markings per PDF (cover page + every page's header/footer checked)
| File | Pages | Marking found | Decision |
|---|---|---|---|
| CNSSI-1253F_Attachment_6_Privacy_Overlay_20241031.pdf | 98 | No classification banner, no CUI/FOUO, **no distribution statement** | Derived data shipped (public reference JSON); PDF **not** committed |
| Classified_Systems_Overlay_FINAL_Dated.pdf | 43 | No banner, no CUI/FOUO, no distribution statement | Derived data shipped; PDF not committed |
| CNSSI_1253F_Attachment_2_Space_Overlay_Aug_2025.pdf | 82 | No banner, no CUI/FOUO, no distribution statement. Paragraphs carry "(U)" portion marks. The text *mentions* CUI only as a protected information category. | Derived data shipped; PDF not committed |
| Intelligence_Overlays_.pdf | 71 | **UNCLASSIFIED//FOUO** on every page | **Restricted.** PDF and derived data are gitignored; not in the public demo; importable by a platform admin |
| CDS_Overlay_Admin_Update_20240109.pdf | 149 | **UNCLASSIFIED//FOUO** on every page (142 marks) | **Restricted**, as above |

None of the five carries an explicit "Approved for public release" statement, so **no PDF is committed**. `.gitignore` covers `reference/cnssi1253/*.pdf` and `reference/cnssi1253/derived/`.

## A2. Parsing
- **Parser:** `scripts/cnssi1253/parse_overlays.py` (pdftotext -layout + pdfplumber).
  - Single-column summary tables (Classified, Space, CDS) are parsed from layout text, with tokens anchored to the header column.
  - Multi-column tables (Privacy, Intelligence) are parsed from PDF word x-coordinates, because layout-text offsets drift.
  - Detail blocks (`ID, NAME` → Justification / Guidance / Parameter Value / Reference) are captured with their page, and labels are scoped to variants ("for INT-B and INT-C", "ACCT, Low, and Moderate Parameter Value").
- **Output:**
  - `backend/app/services/content/cnssi1253_overlays.json`: public data, schema 1, with source file, SHA-256, document date, page count, marking and PDF page per row.
  - `reference/cnssi1253/derived/cnssi1253_restricted_overlays.json`: FOUO data, gitignored.
- **IDs:** normalised to the Rev 5 catalog (`AC-2(12)` → `ac-2.12`). **Not-in-Rev-5 or withdrawn IDs: 0 in all five documents.**
- **Page references** are PDF page numbers (the viewer's page index), not the printed page numbers.

### Per-overlay counts and parse confidence
| Overlay / variant | Summary rows | Add | Remove | Other | Parameter values | Confidence / verification |
|---|---|---|---|---|---|---|
| Privacy (Att. 6, 2024-10-31) – ACCT | 315 | 92 | 1 | 93 baseline | 37 in total | High. 14 hand samples (pp. 15–16) plus 1 absent check. Layering check ACCT ⊆ Low ⊆ Mod ⊆ High holds for all rows. |
| – Low | | 121 | 1 | 93 baseline | | |
| – Moderate | | 169 | 1 | 93 baseline, 5 guidance | | |
| – High | | 174 | 1 | 93 baseline, 5 guidance | | |
| – Privacy Enhancing | | – | – | 42 optional (not auto-applied) | | |
| Classified (App. E Att. 5, 2022-09-30) | 108 | 108 | 0 | – | 24 | High. 108 = my family-by-family count of Table 1 (pp. 5–9). 13 hand samples. |
| Space (Att. 2, Aug 2025) | 345 | 83 | 262 | – | 0 | High. 12 hand samples. The document's own total ("306 H/H/H controls not identified in Table 2") equals Appendix A Table 3 (306), with zero overlap with Table 2. |
| Intelligence INT-A / B / C (FOUO, 2023-11-27) | 186 | 166 / 175 / 185 | 1 / 1 / 1 | – | 44 | High. 10 hand samples plus 1 absent check (stored in the gitignored verification file). |
| CDS Access / Transfer-Multilevel (FOUO, 2023-02-01, admin update 2024-01-09) | 724 | 107 / 135 | 14 / 14 | 211 baseline (S/P), 318 / 324 guidance, 32 / 39 implementation considerations | 302 | High. 12 hand samples plus 2 absent checks ("*" = Transfer only, "**" = Access only). |

### Ambiguous / not parsed confidently (no guessing)
1. **Privacy AC-3(9):** the summary row parses cleanly (Low +R, Mod/High +VR), but the detail section has no `AC-3(9), …` heading I could find. The row has no guidance text instead of borrowed text.
2. **Space removals ("--")** are defined against the **CNSSI 1253 H/H/H** baseline. This app's baselines are NIST SP 800-53B, so a removal of a control the system doesn't have is a no-op, and nothing is invented.
3. **CDS** is baseline-dependent (H-H-M + CNSS privacy baseline). `S` / `P` / `A` markers are stored as "baseline (with guidance)". Implementation-consideration-only cells (e.g. AC-3(10) `GV`) are stored as "consideration" and never change the control list.
4. **Privacy "CNSS Privacy Baseline"** rows (93) are listed as baseline controls with no per-variant flags, exactly as the table shows.
5. **Long parameter values** are stored in full in the overlay data. The Workbench parameter value (OdpValue) keeps the first 255 characters, with the citation.
6. **NC3 overlay:** no document was provided, so it stays "structure only".

## A3. Select step
- **Data:** migration `0017` adds overlay `group_key`/`variant`/`details` and tailoring-decision `overlay_key`/`prior_origin`/`prior_origin_detail`. One active overlay row exists per variant (e.g. `cnssi-privacy-moderate`), with the document provenance.
- **Applicability per overlay**, with help text from each document:
  - Privacy: two-question PII approach → ACCT / Low / Moderate / High.
  - Classified: yes/no.
  - Space: yes/no.
  - Intelligence (INT-A/B/C) and CDS (Access / Transfer): appear once imported. Until then they show "marked UNCLASSIFIED//FOUO … a platform administrator can import the derived data file".
- **Apply:**
  - Adds the "+" controls and removes the "--" controls (each removal is recorded with its prior origin).
  - Sets the overlay parameter values (`OdpValue`, parameter `overlay:<key>`, source "…(CNSSI 1253 App. E Att. 5, p. 12)").
  - Variants of one overlay are mutually exclusive: switching Low → Moderate removes Low first.
- **Remove** reverses exactly its own changes:
  - deletes only the controls it added (a control also added by another applied overlay is handed over, not deleted);
  - restores the controls it removed, with their original origin;
  - deletes its parameter values.
- **Per-control view** ("Show what … changes in this system"): "Added by Classified System Overlay (CNSSI 1253 App. E Att. 5, p. 12) · +VR", followed by justification, guidance and parameter value with pages. The same note appears in the Workbench control detail.
- **Counts** come from the one counts service: "287 baseline + 65 added by overlays − 0 removed by overlays − 1 tailored out + 0 tailored in = 351 assigned". Overlay removals are no longer mixed into manual tailoring.
- **Admin import:**
  - **Import official data (JSON)** (`POST /overlays/import-reference`, `admin.content.load` = platform admin only) loads the restricted file or a newer version.
  - The existing per-overlay CSV import is kept for newer versions.
  - Every import is audited.

## B. Independent-test fixes
1. **Page-size selector (50/100/250/All, remembered per user)** is now always visible on the Workbench, and added to:
   - Mapping Review queue;
   - POA&M (server `page_size`, cap raised to 1000);
   - Audit log (cap 1000);
   - Evidence ledger;
   - Ingest runs;
   - each overlay's control list.

   Traceability already had it. All are shared via `usePaged()` in `components/common/PageSize.tsx`.
2. **Approved status suggestions:**
   - They move to a separate **"Awaiting assessor (SCA)"** tab with an explainer.
   - The message reads "Implementation set to Implemented. Assessment status needs SCA confirmation".
   - The Next step link is "SCA: confirm the assessment result in 'Awaiting assessor (SCA)'" (`/mapping-review?tab=sca`).
   - **Audit:** previously only status items wrote a per-item event; policy and STIG mapping items relied on their helpers plus one summary row. Now every decided item writes its own `mapping_review.item_approved|rejected|edited` event, and tests assert one event per item.
3. **Export parameter comparison:**
   - New system-wide `GET /systems/{id}/parameters.csv`: policy values next to the ODP and observed value, plus ODP and overlay parameter rows.
   - Buttons on the Workbench header and the Select step. The policy detail button now uses the same download.
   - Download is a Blob + anchor with the filename from Content-Disposition, plus a success toast (`lib/download.ts`).

## Files
- **New:**
  - `scripts/cnssi1253/parse_overlays.py`
  - `backend/app/services/overlays.py`
  - `backend/app/services/content/cnssi1253_overlays.json`
  - `backend/alembic/versions/0017_official_overlays.py`
  - `backend/tests/test_official_overlays.py`
  - `frontend/src/lib/download.ts`
- **Changed (backend):**
  - `models.py`
  - `services/rmf_steps.py`
  - `services/counts.py`
  - `api/v1/rmf_steps.py`
  - `api/v1/phase3.py`
  - `api/v1/phase4.py`
  - `api/v1/workbench.py`
  - `api/v1/poams.py`
- **Changed (frontend):**
  - `components/common/PageSize.tsx`
  - `components/evidence/ReviewQueue.tsx`
  - `pages/RmfStepPages.tsx`
  - `pages/WorkbenchPage.tsx`
  - `pages/EvidencePages.tsx`
  - `pages/PoamPages.tsx`
  - `pages/Phase3Extras.tsx`
  - `pages/Phase3Pages.tsx`
- **Changed (other):** `.gitignore`
- **Tests:** `tests/test_sme_section2.py` and `tests/test_sme_section3.py`, updated.

## Tests
- `test_official_overlays.py` (11 tests):
  - reference file is public-only, versioned, SHA-256 matches the PDF, no ambiguous or flagged IDs;
  - hand-verified samples for each public overlay, with PDF pages checked against `pdftotext` page text;
  - FOUO samples (skipped when the gitignored data is absent);
  - totals: Classified 108; Space 345 = 83 + 262, with Table 3 = 306 and no overlap; Privacy layering;
  - Select-step tests covering:
    - applicability groups and the restricted note;
    - Classified apply → additions, parameter values, label "p. 12", the 15-minute parameter, the CSV export row and the Workbench note; then remove → identical control set;
    - Space removals recorded and restored exactly;
    - Privacy variant exclusivity, with shared additions kept and the final state identical;
    - admin-only import;
    - restricted load inside a rolled-back transaction (FOUO rows never committed to the shared DB).
- **Section 2:** a 2-item bulk approval writes 2 per-item audit events and the items show "awaiting SCA"; a mixed bulk approval writes one audit event per item.
- **Full backend suite: 465 passed, 43 skipped.** Jest (`yarn test`): 6/6.
- **Browser** (`/root/shots_ov.py`, account jordan.qa7731), no page errors:
  - Counts: 286 → Classified applied 351 → Privacy-Moderate 421 → both removed 286.
  - AC-11 label checks out.
  - CSV download is 56 rows (55 overlay parameter rows), with a toast.
  - The Workbench overlay note and the page-size selector are visible on all six pages.
  - The Mapping Review "Awaiting assessor (SCA) (2)" tab shows.

## Click path
Sidebar **3 · Select → Baseline, overlays & tailoring** → **Overlays** panel:
1. Answer each overlay question, e.g. Classified "Yes – apply", or Privacy "Apply Moderate privacy risk".
2. **Show what … changes in this system** lists each control with "Added by / Removed by … (CNSSI …, p. N)" and its guidance.
3. **Remove** reverses exactly that overlay's changes.

Intelligence / CDS: as a platform admin, use **Import official data (JSON)** with `reference/cnssi1253/derived/cnssi1253_restricted_overlays.json`.
