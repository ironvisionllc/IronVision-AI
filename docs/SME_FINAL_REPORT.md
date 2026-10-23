# SME remediation – final report (Sections 1–7 + end-to-end flow)

Preview: https://aegis-rmf-demo.preview.emergentagent.com. The Droplet was not touched and recovery stays paused.
Per-section reports: `docs/SME_SECTION1_REPORT.md` … `docs/SME_SECTION7_REPORT.md`. Screenshots: `docs/screenshots/sme-section*/` and `docs/screenshots/sme-final/`.

## Commits
| Section | Commit |
|---|---|
| 1 Broken features | `ea7421c` |
| 2 STIG and evidence detail | `94002f0` |
| 3 RMF 7 steps | `79c2433` |
| 4 Evidence sources | `f24d0da` |
| 5 Inheritance | `435ce50` |
| 6 Roles | `fa0e3d4` |
| 7 Smaller improvements | `b32fcc6` |
| Final flow fixes (audit-lock deadlock, SCA-pending label, demo overlay hidden in clean accounts) | see `git log -1` |

## Final SME flow – fresh sign-up `sme-final-e5f7d2@example.com`
Driven in the browser, with API checks after each step (`/root/final_flow.py` and `/root/final_resume.py`; results in `/root/final_flow.json`).

| Step | Result |
|---|---|
| Fresh account | The Getting-started page shows "Start your first authorization"; 0 systems (screenshot 01). |
| Register system → Prepare roles | ISSO = the user; System Owner, ISSM, AO and SCA as name placeholders. Prepare step = **Complete**. |
| Categorize | SP 800-60 types C.2.1.1 (L/L/L) + D.16.3 (M/M/M) → high-water mark **Moderate**, with the calculation shown (screenshot 02). Mission ME, IS Major Application, PII = Yes → privacy baseline. Categorize = **Complete**. |
| Select with tailoring/overlay | Moderate + privacy = 340. Tailored out AC-2(1) with a rationale → "340 baseline − 1 removed … = **339 assigned**". Applying the CNSSI Privacy Overlay is refused in plain words as "structure only – load the official control list". The synthetic demo overlay is **not listed** in a clean account. Select = **Complete**. |
| Upload DISA STIG .ckl + XCCDF | `ltp_web-server-03.ckl` → completed (ckl); `demo_linux_xccdf_results_SYNTHETIC.xml` → completed (xccdf). STIG run detail page (screenshot 04). |
| Upload RA policy | Synthetic RA policy .docx → RA-1 mapped at **High** confidence ("explicit control ID … RA-1 statement language … 8/8 policy elements"). |
| Approve in Mapping Review | STIG→CCI→control mappings and policy mappings approved (13 STIG mappings now `human_approved`), then 5 evidence-based status suggestions approved in bulk with one justification. As ISSO, assessment stays for the SCA (SoD); those items now read "implementation approved – waiting for the SCA". |
| Controls updated in the Workbench | `implementation_status=implemented` filter = **5** (the 5 approved controls). Implement step: "5 of 339 implemented". |
| Filters | `has_evidence=yes` = **6** = summary "with evidence" **6**. Implemented filter = 5. Satisfied = 0, which is correct because the ISSO cannot assess. |
| Export parameter comparison | `GET /policies/{id}/parameters.csv` → 200 `text/csv` with a header row (`row_type,policy,…,mapping_basis`) and data rows. |
| Counts match across screens | Workbench total **339** = Select **339** = traceability rows **339** = system metrics **339** = Implement-step denominator **339**. |
| No demo data | 1 system (the one registered); no synthetic overlays listed; no providers; demo data never loaded. No browser page errors. |

## Bug found during the final flow (fixed)
- **Mapping Review bulk approval of status suggestions hung the backend.** Root cause: the endpoint wrote audit rows, which take the audit-chain advisory lock, then checked the SCA permission with `enforce()`. A denial writes its own audit row in a **separate** session (`record_now`), which waited forever for the lock its own request held: a self-deadlock. Logins then queued behind it, and the preview returned 502.
- Fix:
  - `implementation.write` is enforced **before** any audit write.
  - The SCA check uses `has_permission()`, which writes no audit row.
  - The stuck connection was terminated.
- Regression test: `test_bulk_status_approval_without_assessor_role_does_not_deadlock` (60 s alarm).

## Tests
- Full backend suite after Section 7: **453 passed, 43 skipped**.
  - One intermediate run showed 270 errors from a transient environment blip; the immediate rerun was clean.
  - `test_route_authz` and env-lint show occasional parallel-run flakes that pass when run alone.
- SME test files:
  - `test_sme_section1.py` … `test_sme_section6.py` (Section 7 has no backend test file).
  - Each runs in an isolated fresh sign-up so shared demo data is never mutated.
- Jest: 6 passed.

## Could not fix / limits (honest list)
1. **Item 8 "View" on legacy mappings:** searched the whole UI for "legacy", "superseded", "View" and buttons with no or no-op handler. No dead button was found; superseded mapping versions are plain text. A screenshot or URL from the SME is needed to find it.
2. **CNSSI 1253 overlay contents and per-objective control tables:** not reproduced, because the official CNSS text is not public in a machine-readable form and must not be invented. The overlays are seeded as "Structure only – load the official control list" with a validated CSV import (admins). CNSSI mode uses the highest objective for the 800-53B baseline and says so.
3. **eMASS field lists** (system type, ACAT, authorization type) are labelled "eMASS-aligned; verify against your eMASS instance".
4. **Live API connectors** (ACAS/Tenable.sc, pipelines, AWS…) remain **MOCK/DEMO adapters** in this deployment; the "Connect a tool" panel says so.
5. **Page-size choice** is remembered per user **per browser** (localStorage), not server-side.
6. **New sign-ups are rate-limited** (HTTP 429) after several in a short time. Some section checks therefore reused an earlier clean sign-up account; this is noted in each report.
7. **Not yet re-run by the independent testing agent** for Sections 2–7. Root said it will test independently.
