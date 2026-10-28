# 1 · UI audit (current UI, Phase 1 – no behaviour changed)

How this was gathered:
- `scripts/ux_baseline/crawl.py` visited all 33 major routes as the ISSO persona on the SYNTHETIC demo sandbox (system LTP).
- Screenshots are in `screens/current/`. Counts per route are in `data/screens.json`: visible buttons, inputs, selects, checkboxes and headings.
- Every route was also inspected in code. File refs are `frontend/src/…`.

## 1.1 Route inventory

| Route | Component · file | Buttons / fields¹ | Audit notes (dup = duplicate action · term = confusing label · clicks · filters · early fields · merge · remember · disconnected · automate) |
|---|---|---|---|
| `/rmf-workflow` | RmfWorkflowPage · pages/Phase3Pages.tsx | 1 / 0 | **merge:** static overview; overlaps the stepper on every step page and the system detail. |
| `/systems` | SystemsPage · pages/SystemsPage.tsx | 3 / 0 | **remember:** list only; no step status per system. |
| `/systems/new` | RegisterSystemPage · pages/SystemsPage.tsx + components/rmf/RegisterStart.tsx | start choice, then 3 required inputs | **disconnected:** an information type and PII are required at registration, then shown again in Categorize. The task script had to pick a different type in Categorize because the first was already added. **clicks:** the start-choice screen comes before the form. |
| `/systems/:id` | SystemDetailPage · pages/SystemDetailPage.tsx | 39 / 0 | **merge:** overview, roles, assets, Import Center, package and workbench links. This is a second "dashboard" next to the step pages. **dup:** Import Center and Authorization package buttons, also in the sidebar. **term:** "Archive system", "Revoke" sit next to normal actions. |
| `/rmf/prepare` | PreparePage · pages/RmfStepPages.tsx | – | Roles. **merge:** PPSM, boundary and inventory live elsewhere (`/inventory`, eMASS import). |
| `/rmf/categorize` | CategorizePage · pages/RmfStepPages.tsx + components/rmf/CategorizeForm.tsx | 43 / 9 | **early fields:** framework, mission/system type, environment, privacy, approval and history all on one page. **term:** "FIPS 199 / CNSSI 1253 mode", "Trigraph", "legacy_unreviewed". |
| `/rmf/select` | SelectPage · pages/RmfStepPages.tsx | 33 / 33 | **dup:** the categorization summary repeats Categorize, and "Next action: Assign key roles" shows on every step page (it is system-level, not step-level). **early fields:** the ISCM strategy (28 inputs) sits under baseline/tailoring. **term:** "Make it the AC/AU/SC/AT/CM profile value" (×8 buttons), "ISCM", "S-5". |
| `/catalog` | ControlsPage · pages/ControlsPage.tsx | – | **merge:** reference catalog plus a "Reference catalog" toggle inside the Workbench. Two ways into the same tree. |
| `/rmf/implement` | ImplementPage · pages/RmfStepPages.tsx | 4 / 0 | **dup:** "Generate SSP (DOCX, PDF)" also appears on Authorize and on the Authorization package page. **clicks:** the hub only links onward. |
| `/systems/:id/controls[/:cid]` | WorkbenchPage · pages/WorkbenchPage.tsx + components/workbench/* | 49 / 13 selects, 15 checkboxes | **filters:** 13 selects plus 15 checkboxes. **early fields:** advanced eMASS fields sit inline with the status. **clicks:** the list stays hidden until a filter or "All controls" is chosen (the script needed 3 clicks just to open a control on a new system). **dup:** 4 export buttons in the header. **term:** "eMASS validation", "Reference catalog", "Mine/All in system", "CONTROL"/"POA&M" prefixes in the queue. |
| `/inheritance` | InheritancePage · pages/Phase3Pages.tsx | – | **remember:** inheritance is set here and as "designation" inside Workbench advanced fields (same data, two places). |
| `/inventory` | InventoryPage · pages/InventoryPage.tsx | – | **disconnected:** assets also appear under System detail "Asset inventory". |
| `/ccis` | CciPage · pages/CciPage.tsx | – | **merge:** belongs under the control's Requirements tab. **term:** "CCI view". |
| `/policy-auditor[/:id]` | PolicyAuditorPage, PolicyDetailPage · pages/Phase3Pages.tsx | – | **disconnected:** suggestions land in `/mapping-review`, a different step section, with no link back from the control. |
| `/evidence-sources`, `/ingest-runs/:id` | SourcesPage, IngestRunPage · pages/EvidencePages.tsx | – | **clicks:** on a new system a "source" must be created before the first upload (+3 clicks, +1 field). **term:** "Evidence Sources", "ingest run", "connector". |
| `/evidence-ledger` | LedgerPage · pages/EvidencePages.tsx | 68 / 1 | **term:** "Ledger", "Verify integrity", "Preview diff & impact", "Content updates (installed vs available)", "Demo: −45d". Evidence browsing and content-pack updates are mixed on one page. |
| `/rmf/assess` | AssessPage · pages/RmfStepPages.tsx | 7 / 0 | **merge:** a hub of 5 link cards. The real work lives in Reviews, Workbench, Test Results and Mapping Review. **dup:** Generate SAR/RAR. |
| `/reviews[/:id]`, `/findings/:id` | ReviewsPage, ReviewDetailPage, FindingPage · pages/ReviewPages.tsx | 4 / 0 | **term:** "Reviews", "Who can decide what". **remember:** SCA determinations are in Reviews, not in Assess. |
| `/test-results` | TestResultsPage · pages/TestResultsPage.tsx | 3 / 1 | **term:** "Templates → Test Results" (nav), "Import from eMASS" vs "Import…" (two import buttons). |
| `/mapping-review` | MappingReviewPage · pages/Phase4Pages.tsx | 51 / 26 checkboxes | **filters:** 6 tabs ("All open", "Status suggestions", "Status suggestions from policy coverage", "Policy mappings", "STIG mappings", "Awaiting assessor (SCA)"), then 3 more sections. **term:** "Accept as informational", "Out of scope / N/A (needs approval)", "Map manually". |
| `/rmf/authorize` | AuthorizePage · pages/RmfStepPages.tsx | – | **dup:** SSP/SAR/RAR generation again. |
| `/systems/:id/authorization` | AuthorizationPage · pages/Phase3Extras.tsx | 14 / 0 | **dup:** "Generate ssp / poam / assessment-plan / assessment-results" plus DOCX/PDF again, plus OSCAL. **merge with `/rmf/authorize`.** |
| `/poams[/:id]` | PoamListPage, PoamDetailPage · pages/PoamPages.tsx | 8 / 4 | **term:** column header "RISK ▲" (sortable header read as a button). **disconnected:** POA&Ms are created from a finding, but the list isn't reachable from the finding's control tab. |
| `/emass` | EmassPage · pages/Phase4Pages.tsx | 7 / 0 | **term:** "eMASS Sync" next to "eMASS import" and the Import Center. |
| `/rmf/monitor` | MonitorPage · pages/RmfStepPages.tsx | 8 / 0 | **filters:** 6 chips. **term:** "Never monitored (204)", "No SLCM Frequency". |
| `/traceability` | TraceabilityPage · pages/RmfStepPages.tsx | – | **merge:** belongs on the control and dashboard. |
| `/import-center`, `/systems/:id/import-center` | ImportCenterPage · pages/ImportCenterPage.tsx | – | Good base (detection, routing, history). **next action:** after import there is no "what next" (metrics: import_impl shows no next action). |
| `/systems/:id/emass-import[/:iid]`, `/emass-import` | EmassImportPage · pages/EmassImportPage.tsx | – | **merge:** the review step of the Import Center flow. |
| `/systems/:id/migration-report` | MigrationReportPage · pages/MigrationReportPage.tsx | – | Becomes the "Completed" step of import. |
| `/portfolio` | LeadershipPage · pages/LeadershipPage.tsx | 3 / 0 | Locked for ISSO. Shown greyed in the nav. |
| `/help`, `/docs-center[/:slug]` | HelpPage, DocsCenterPage | – | **term:** "Help: who can do what". Two help locations. |
| `/audit-log` | AuditLogPage · pages/Phase3Extras.tsx | 27 / 7 | Admin/oversight only. Shown to ISSO in "Tools". |
| `/admin`, `/settings/notifications` | AdminPage, NotificationPrefsPage | 5 / 0 | Fine. |

¹ Visible on first load at 1440×900, from `data/screens.json`.

**Navigation today** (`frontend/src/lib/nav.ts`, `components/shell/AppShell.tsx`):
- 29 sidebar entries under 9 headings.
- A second horizontal stepper on each step page.
- Step hubs (`/rmf/*`) that mostly link to other pages.

## 1.2 Top 15 sources of complexity (ranked)

| # | Source | Evidence | Impact |
|---|---|---|---|
| 1 | **Two navigation systems.** 29 sidebar links plus a 7-step stepper plus 7 hub pages that mostly link elsewhere (Assess hub = 5 link cards). | `screens/current/assess.png`, `implement.png`, nav.ts | You must remember where work lives. The step hubs add a page change to every task. |
| 2 | **The Workbench is overloaded.** 13 selects, 15 checkboxes, 8 stat cards and 4 export buttons. The list is hidden until a filter is chosen. | `workbench.png`; metrics update_control = 6 clicks, 2 page changes | The core daily screen is the hardest to read. |
| 3 | **"Next action" is generic and often wrong.** "Next action: Assign key roles" appears on Select, Implement, Assess and Monitor for a system mid-assessment. | `select.png`, `assess.png`, `monitor.png` | Users learn to ignore guidance. |
| 4 | **Document generation in 4 places.** SSP in Implement, Authorize and Authorization package. SAR/RAR in Assess and the package. | `implement.png`, `authorization.png` | Duplicate actions, unclear "official" place. |
| 5 | **Assessment work is scattered** across Reviews, Workbench assessment section, Test Results and Mapping Review "Awaiting assessor". | `assess.png`, `reviews.png` | The SCA has no single queue. |
| 6 | **Mapping Review: 6 tabs plus 3 sections.** Internal wording such as "Accept as informational" and "Status suggestions from policy coverage". | `mapping_review.png` | Policy coverage vs status vs assessment is unclear. |
| 7 | **Data entered twice:** an information type and PII at registration, then again in Categorize. Inheritance is set on `/inheritance` and as "designation" in the Workbench. Assets appear in two places. | metrics register/categorize; `register.png` | Disconnected copies, conflicting values. |
| 8 | **Imports end without "what next".** Implementation Plan, Test Results and Evidence uploads show no next action. | metrics import_impl/test_results/evidence: next_action_shown = false | The user stops at the import. |
| 9 | **The ISCM strategy (28 fields) sits on the Select page.** "Make it the … profile value" appears 8×. | `select.png` | Advanced fields shown before they're relevant. |
| 10 | **Evidence upload needs a "source" first** on a new system (+3 clicks, +1 field). | metrics evidence = 7 clicks, 3 fields | Internal model (connector/source) leaks into the UI. |
| 11 | **Internal terminology**, e.g.: "Ledger", "ingest run", "CCI view", "Templates → Test Results", "eMASS Sync" vs "eMASS import" vs "Import Center", "legacy_unreviewed", "S-5", "Trigraph", "Never monitored". | per-route table | Not eMASS words, so it needs training. |
| 12 | **Status vocabularies mixed.** Implementation status, policy coverage, assessment result, authorization status and evidence freshness share colours and appear side by side without labels. | `workbench.png`, `mapping_review.png` | Users confuse "covered by policy" with "assessed". |
| 13 | **System detail is a second dashboard.** 39 buttons, with no step status and no "continue". | `system_detail.png` | No single starting point per system. |
| 14 | **No role-based home.** The ISSO, SCA, ISSM and AO all land on the same pages. Irrelevant actions are shown greyed (Portfolio, Audit Log). | nav.ts; `reviews.png` | New users don't know what's theirs. |
| 15 | **Findings → POA&M → control are only partly linked.** No "Add to POA&M" when the finding is already linked. POA&M edits happen on a separate page, 2 page changes away. | metrics finding/poam | Users must remember IDs. |
