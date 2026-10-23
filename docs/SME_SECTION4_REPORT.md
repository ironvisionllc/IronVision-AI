# SME test findings – Section 4 (evidence sources)

Preview: https://aegis-rmf-demo.preview.emergentagent.com. Browser check account: `sme-s3-9bb8b8@example.com` / `Sme-S3-2026!x` (clean sign-up, system S3P). A new sign-up hit the sign-up rate limit (429), so the clean Section 3 account was reused.
Screenshots: `docs/screenshots/sme-section4/`. The Droplet was not touched.

| # | Root cause | Change | Files | Click path |
|---|---|---|---|---|
| 22 Split "Add evidence" | One "Add source" form mixed file-import types and live connectors and **always showed a credential field**, even for STIG/ACAS file sources. Upload lived in a toolbar of the "Latest ingest" table. Policies had to be uploaded elsewhere. | Two side-by-side panels under **Add evidence**:<br>**a. Upload a file** (manual / air-gapped). Lists STIG .ckl/.cklb, SCAP/XCCDF/ARF .xml, ACAS .nessus/CSV, SARIF and policies .docx/.pdf, each with a one-line "when to use". Policies are sent to the Policy Auditor automatically (Next step → Policy Auditor). It never asks for credentials. Recurring file sources can be created here with a name and type only.<br>**b. Connect a tool.** Only live API types (eMASS, AWS GovCloud, Azure Gov, DevSecOps pipeline, on-prem collector, manual attestation), each with "when to use". This is the **only** place with a token field, and it says the connectors are MOCK/DEMO adapters here.<br>**Backend root fix:** `POST /systems/{id}/sources` now **rejects a credential for any file-import type** (422 with a plain message), so the UI cannot store one by mistake. `/source-types` returns a `when` sentence for every type. | api/v1/evidence.py, services/connectors.py (`SOURCE_WHEN`), pages/EvidencePages.tsx (`UploadFilePanel`, `ConnectToolPanel`) | Sidebar → 4 · Implement → Evidence Sources → Add evidence |
| 23 "No source" option | The bare "(no source)" option did not say what it meant. | Kept and explained, as the clearer option: **"One-off file – don't link to a source"**, with help text: upload without linking to a source for single files; create a file source for files you upload regularly, so their history and freshness are grouped. | EvidencePages.tsx | Evidence Sources → Upload a file → "Link to a source (optional)" |
| 27 (early) Sample STIG files link | The link sat in the sandbox "Get started" bar, an unexpected place. | Kept, since it is intentional for sandbox trials. Moved under the **Upload a file** help and labelled **"Sample/test data (SYNTHETIC) – download sample STIG and ACAS files"**, with a tooltip. Sandbox accounts only. | shell/Sandbox.tsx (`SampleFilesLink`), EvidencePages.tsx | Evidence Sources → Upload a file (bottom) |

## Tests
- `backend/tests/test_sme_section4.py` (2): every source type has "when to use"; file sources refuse credentials, while live connectors accept and encrypt them.
- Browser:
  - "Upload a file" has 0 password fields; "Connect a tool" has 1.
  - The first option reads "One-off file – don't link to a source"; the sample link is present.
  - Uploading `ltp_api-gateway-04.ckl` → "received – processing" + "Next step: see the controls it affects in the Control Workbench →".
- Full suite: see the Section 5 report (run after each section).
