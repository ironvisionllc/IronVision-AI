# SME test findings – Section 1 (broken features) + UX pass

Preview: https://aegis-rmf-demo.preview.emergentagent.com (dev-password sign-up). The Droplet was not touched.
Test accounts: see `/app/memory/test_credentials.md` (SME fresh + SME demo-loaded).
Screenshots: `docs/screenshots/sme-section1/before-*.png` (commit 726bd01, before Section 1) and `after-*.png` (current).

| # | Root cause | Fix | Files |
|---|---|---|---|
| 1 Demo data in new accounts | Tenant tables were already clean. The leak came from **global** `content_versions`: the synthetic sample STIG/KEV versions plus "available" updates were shown to every tenant, and the diff preview ran against synthetic content. | `content-updates`, `content/versions` and the preview hide synthetic content unless the tenant is the demo, a non-sandbox tenant, or has loaded demo data. A tenant with no systems sees reference content as installed, never as updates or diffs. New **Load demo data (SYNTHETIC)**: sandbox only, idempotent, removed by Clear my workspace. | services/sandbox.py, content_updates.py, api/v1/phase4.py, content.py, sandbox.py, Sandbox.tsx |
| 2 Control counts | Each screen counted something different, unlabelled: 1,196 (catalog incl. withdrawn), 1,014 (selectable), 324 (base), the system's assigned count after baseline + privacy + overlays + tailoring. | `services/counts.py` is the single source (`/content/counts`, `/content/stats.counts`, workbench summary `counts`, RMF Select stage). Every number now carries a label and a reconciliation line ("N baseline − removed + overlay + tailored in = assigned"). | counts.py, workbench.py, rmf.py, StatsStrip.tsx, ControlsTable.tsx, WorkbenchPage.tsx |
| 3 Policy Auditor mapped RA policy to AC-17 | The analyser never extracted control IDs. The only control-level output was `REQUIRED_SECTIONS`, which flagged a missing "remote access" section as **AC-17** on *every* policy. | `services/policy_mapping.py` extracts:<br>• Explicit IDs (RA-1, RA-1a, RA-1a.1, RA-1.a, AC-2(1), AC-2 (1)).<br>• "-1 policy and procedures" statement language (family name + purpose/scope/roles/…).<br>• Control-title language.<br>Each mapping gets High/Medium/Low confidence with its basis and snippets. Required-section checks apply only to the policy's own family. | policy_mapping.py, rmf.py |
| 4 Manual mapping | Not available before. | **Map to control**: searchable multi-select, on the panel and on each finding. **Reject mapping**: justification of at least 10 characters required. Mappings are stored in the versioned table `policy_control_maps` (migration 0014; rows are never edited, a decision closes the old row) and audited. Mapped policies show on the control in the Workbench (source, who, when). | 0014 migration, models.py, phase3.py, PolicyMappings.tsx, StatusSection.tsx |
| 5 Empty parameter export | The export iterated only over linked systems (none, so empty) and started with a comment line instead of a header. | Header row first. One row per policy value (even with no system linked) plus one row per control mapping. | phase3.py |
| 6 Workbench filters | The status filter only applied to the "All controls" list. The default view (work queue) ignored it. Only 2 filters existed. | Filters: implementation, assessment, inheritance, origin, monitoring, family, has-evidence, evidence freshness. They live in the URL, and any active filter switches to the filtered list. The list and summary refetch after a status change. | workbench.py, WorkbenchPage.tsx |
| 7 "Has evidence" | No filter; the dashboard number was not a link. | `has_evidence=yes/no` and `evidence=current`, using the same predicate as the counts service. Workbench and Leadership numbers link to the pre-filtered list. | workbench.py, counts.py, LeadershipPage.tsx |
| 8 Legacy mappings "View" | **Not found.** No "legacy mappings" view/button exists in the frontend or backend. The only "view" links open finding detail and work. | Unchanged. Please send a screenshot / page URL. | – |
| 9 Status save | Status was saved only as a side effect of "Save draft version", which needs a narrative. | Separate **Status** section with Save, toast + next step, inline plain-language errors, "Last changed by … at …" from the audit trail, and RMF tooltips. Assessment status is shown read-only (set by the SCA). | workbench.py (`PUT …/status`), StatusSection.tsx, ImplementationPanel.tsx |
| 10 Evidence file types | (a) The upload picker accepted only `.nessus/.csv/.ckl/.cklb`, so `.xml` could not be chosen. (b) XCCDF was detected only when `TestResult` appeared in the first 2 MB, but SCC/DISA results put it after all rules. (c) Detection keyed on the extension. | Detection is now by content (root element / JSON keys / CSV header) for .ckl, .cklb, XCCDF results (any size), ARF, .nessus, Nessus/ACAS CSV (incl. "Plugin/IP Address" columns) and SARIF. Rejections say why (e.g. "XML but not a supported scan format – root element is <inventory>", or "XCCDF Benchmark without results") and list the supported formats. PDF/DOCX are pointed to the Policy Auditor. | parsers.py, EvidencePages.tsx |

Also fixed: policy upload crashed in an account with no system (`evs[0]`), and modals inside animated panels were clipped (Modal now uses a portal).

## UX pass (screens touched)
- **Empty states:** "No system yet → Register your first system" on Controls and on every system-scoped page. It explains what a system is and points to Load demo data.
- **Load demo data:** a primary button with a tooltip, labelled SYNTHETIC. After loading, a green **Next step** banner: "open the Control Workbench".
- **Policy Auditor:**
  - A one-line purpose for the mapping panel.
  - Plain basis wording ("the policy quotes this control ID") and control titles.
  - Plain statuses ("Suggested – needs your review").
  - A confidence tooltip and a reason prompt on reject.
  - After a mapping decision, Next step: "review RA-1 in the Control Workbench".
- **Status section:** purpose line, RMF tooltips, toast plus "Next step: write the implementation statement", and errors that say how to fix them (e.g. switch role).
- **Evidence upload:** button renamed "Upload scan results", accepted formats listed in plain words. Errors use a What happened / How to fix / Accepted formats box. A successful upload shows a next step to the Workbench.

## Tests
- Backend `tests/test_sme_section1.py` (25), including:
  - DB-level check that every tenant-scoped table has 0 rows for a fresh sign-up except users/personas and tenant configuration.
  - Every filter value compared with the DB.
  - RA policy fixtures in .docx and .pdf.
  - Format detection fixtures.
- Live preview checks `tests/test_sme_preview_live.py` (10, run with `REACT_APP_BACKEND_URL` set).
- Frontend Jest `StatusSection.test.tsx` (4).
- Full backend suite: 432 passed, 33 skipped. Jest: 6 passed. Testing agent iteration 13: all passed.
