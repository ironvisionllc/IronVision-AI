# SME test findings – Section 2 (STIG and evidence detail) + item 8 follow-up

Preview: https://aegis-rmf-demo.preview.emergentagent.com. Browser check account: `sme-s2-a41c5d@example.com` / `Sme-S2-2026!x` (fresh sign-up → Load demo data).
Screenshots: `docs/screenshots/sme-section2/`. The Droplet was not touched.

| # | Root cause | Change | Files | Click path |
|---|---|---|---|---|
| 8 (follow-up) | I searched the UI for "legacy", "superseded", `>View<` and buttons with no/no-op `onClick`. None found: superseded mapping versions in mapping history are plain text (no button), and the only "view" links (ingest run → finding) open the finding detail and work. | Nothing to fix in code. Still needs the SME's screenshot/URL. | – | – |
| 11 STIG import detail | The ingest run page listed only findings/unmapped items. Rule status, details and comments were stored (`finding_observations.raw`) but never shown. STIG name/version/release were never read. | `GET /ingest-runs/{id}/stig`:<br>• Header (title, version, release, benchmark date) read from the source file for .ckl / .cklb / XCCDF.<br>• Every rule: Vuln ID, Rule ID, title, CAT I/II/III, status (Open / Not a Finding / Not Applicable / Not Reviewed), finding details, comments.<br>• Totals per status and severity.<br>• "Matches the source file: N rules parsed, N stored" check (the stored file is re-parsed).<br>UI panel adds search, status and severity filters, sort, and tooltips. | ingest/parsers.py (`stig_header`), api/v1/evidence.py, components/evidence/StigDetail.tsx, EvidencePages.tsx | Evidence Sources → Recent ingest runs → open a .ckl run → "STIG checklist detail" |
| 12 Passing evidence → suggested status | Not implemented before. | `services/review_queue.status_suggestions` covers controls with current evidence linked, no open finding mapped, not yet Implemented + Satisfied, and not dismissed for the same evidence set. Each lands in Mapping Review with its evidence links and reasoning. Nothing changes until approved.<br>Approve → implementation = Implemented. Assessment = Satisfied **only if the approver holds the assessor permission** (SoD); otherwise it is left for the SCA and reported. Audited with evidence IDs, who and when. Reject → dismissed with a reason until the evidence changes. | services/review_queue.py, api/v1/phase4.py | Mapping Review → "Status suggestions" tab → Approve |
| 13 Mapping Review always empty | STIG→CCI→control mappings are written as `auto_from_authoritative_source`, but the queue listed only `suggested / needs_review / low confidence`, so it was always empty. Policy Auditor proposals lived in a separate table and never reached the queue. | Unified **Review queue**: STIG mappings (grouped per rule → control), Policy Auditor proposals and status suggestions. Approve / reject / edit, singly or in bulk, with **one shared justification** (required for reject and edit). Edit replaces the mapping with the control(s) you enter. Confirmation + Next step: "review the updated controls in the Workbench". The old "Pending review" list is kept. | api/v1/phase4.py (`/mapping-review` `queue`, `POST /mapping-review/decide`), components/evidence/ReviewQueue.tsx, Phase4Pages.tsx | Mapping Review → tick items → type a reason → Approve/Reject/Edit selected |
| 14 Evidence Ledger explanations | Labels only ("installed vs available", "added/removed…"), with no explanation. | Intro line and tooltips: what Installed vs Available mean, that applying never rewrites history, and what Added / Removed / Changed requirement / Changed severity mean "from V… to V…". | Phase4Pages.tsx | Evidence Ledger → Content updates (needs demo data or a system); Preview |
| 15 "no Rev 5 mapping / unmapped" | The Unmapped panel said only "No authoritative/approved mapping – requires explicit mapping or disposition". | A plain "What this means" note (the CCI has no Rev 5 mapping in DISA's CCI list, or the result names no CCI) and a "What to do" note: Map it (RA-5/SI-2 for vulnerabilities), or **No control needed** with a reason. The button "Disposition" was renamed "No control needed". | EvidencePages.tsx | Evidence Sources → an ingest run with unmapped results |

## Tests
- `backend/tests/test_sme_section2.py` (5):
  - STIG detail totals and source check.
  - The queue lists all three kinds.
  - Listing never changes a status.
  - Bulk approve / reject-needs-justification / edit.
  - Status suggestion approval with SoD, and rejection.
- Full backend suite: 436 passed, 43 skipped. One flaky test (`test_env_templates`) passes on its own; it touches the `.env*.example` files that were already uncommitted before this work.
- Jest: 6 passed.
- Browser (fresh sign-up + demo data):
  - STIG header and "✓ Matches the source file: 7 rules parsed, 7 stored".
  - Queue with 25 items (15 status / 2 policy / 8 STIG).
  - Reject without a reason shows the plain error.
  - Approve shows the confirmation + Next step.
