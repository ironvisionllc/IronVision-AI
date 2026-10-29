# IronVision AI – RMF product demo · scene timeline

Video: 1920×1080, 30 fps, H.264, no audio, duration 300.00 s. Times below are measured from the recording (event log of the recorder).

## Scene 1 · Intro & sign-in

- **Start / end:** 0:00.0 – 0:14.0
- **Screens:** Intro card, /login
- **Actions:** Explore the demo; act as ISSO; select LTP
- **Production notes:** Persona emails masked in every frame

| Time | On-screen event |
|---|---|
| 0:00.0 | `open intro.html` |
| 0:04.9 | `open /login` |
| 0:08.7 | `click [data-testid="demo-login-btn"]` |
| 0:09.3 | `persona isso` |

**Narration**

- 0:00.0–0:05.0: IronVision AI – human-approved AI for the NIST Risk Management Framework
- 0:05.0–0:14.0: Shared SYNTHETIC demo workspace · sign in and act as the ISSO persona

## Scene 2 · Dashboard, RMF steps, Guided Mode

- **Start / end:** 0:14.0 – 0:39.6
- **Screens:** /dashboard, /rmf/categorize
- **Actions:** Point at the 7 RMF steps; Guided Mode on → panel → off
- **Production notes:** —

| Time | On-screen event |
|---|---|
| 0:14.0 | `open /dashboard` |
| 0:29.1 | `click [data-testid="guided-toggle"]` |
| 0:30.5 | `open /rmf/categorize` |
| 0:38.6 | `click [data-testid="guided-toggle"]` |

**Narration**

- 0:14.0–0:25.0: System dashboard: the 7 RMF steps with live status and the next action
- 0:25.0–0:39.0: Guided Mode explains each step: purpose, why it matters, who acts, what's next

## Scene 3 · Import Center

- **Start / end:** 0:39.6 – 1:02.0
- **Screens:** /systems/:id/import-center, review page
- **Actions:** Upload SYNTHETIC Control Information; detect; review; accept safe; apply
- **Production notes:** Synthetic workbook

| Time | On-screen event |
|---|---|
| 0:39.6 | `open /systems/f2e6b2e4-57d2-4529-8105-4170076b05cc/import-center` |
| 0:40.5 | `upload SYNTHETIC_LTP_ControlInfo.xlsx` |
| 0:44.6 | `click [data-testid="ic-import-0"]` |
| 0:47.9 | `click [data-testid="ic-result-0"] a` |
| 0:54.2 | `click [data-testid="import-accept-safe"]` |
| 0:57.4 | `click [data-testid="import-apply-btn"]` |

**Narration**

- 0:39.0–0:50.0: Import Center: drop eMASS, STIG, Nessus, PPSM or policy files – each is detected and routed
- 0:50.0–1:02.0: Review before apply: safe changes are accepted, conflicts wait for a person

## Scene 4 · Manage imported data

- **Start / end:** 1:02.0 – 1:24.0
- **Screens:** /import-center/manage/:id
- **Actions:** Sections; delete everything; Undo
- **Production notes:** System shell kept

| Time | On-screen event |
|---|---|
| 1:02.0 | `open /import-center` |
| 1:03.1 | `click [data-testid^="ic-hist-emass-"]:has-text("SYNTHETIC_LTP_ControlInfo.xlsx") [data-testid^="ic-manage-"]` |
| 1:10.0 | `click [data-testid="mid-delete-everything"]` |
| 1:14.7 | `click [data-testid^="mid-undo-"]` |

**Narration**

- 1:02.0–1:13.0: Manage imported data: every applied import, grouped by section, with provenance
- 1:13.0–1:24.0: Delete everything an import created – the system stays – and undo for 30 days

## Scene 5 · Control Workbench & evidence

- **Start / end:** 1:24.0 – 1:52.0
- **Screens:** /systems/:id/controls/ac-2
- **Actions:** Evidence tab → Attach evidence → upload → Completed – next
- **Production notes:** Synthetic .txt evidence

| Time | On-screen event |
|---|---|
| 1:24.0 | `open /systems/f2e6b2e4-57d2-4529-8105-4170076b05cc/controls/ac-2` |
| 1:30.3 | `click [data-testid="wb-tab-evidence"]` |
| 1:32.5 | `click [data-testid="wb-attach-evidence-btn"]` |
| 1:41.3 | `upload SYNTHETIC_AC-2_quarterly_account_review.txt` |

**Narration**

- 1:24.0–1:38.0: Control Workbench: status, statement, evidence and assessment for one control
- 1:38.0–1:52.0: Attach evidence from inside the control: upload → linked → “Completed – next”

## Scene 6 · Policy Auditor

- **Start / end:** 1:52.0 – 2:28.0
- **Screens:** /policy-auditor/:id
- **Actions:** RA-1 met rows with verified quotes; candidates; reading report; Found it here
- **Production notes:** Stored AI result copied from an existing SYNTHETIC analysis – no new AI call

| Time | On-screen event |
|---|---|
| 1:52.0 | `open /policy-auditor/48263f48-6819-4b3b-8b57-86b2c6d69c46` |
| 1:58.5 | `click [data-testid="coverage-toggle-ac-2"]` |

**Narration**

- 1:52.0–2:04.0: Policy Auditor: a stored AI analysis – every 'met' needs an exact, verified policy quote
- 2:04.0–2:16.0: No silent misses: unclear requirements show candidate passages for a human to decide
- 2:16.0–2:28.0: Reading report: what was read, whole-document check, second look, “Found it here”

## Scene 7 · Mapping Review

- **Start / end:** 2:28.0 – 2:44.0
- **Screens:** /mapping-review
- **Actions:** Review-needed note; queue items; approve buttons (not clicked)
- **Production notes:** —

| Time | On-screen event |
|---|---|
| 2:28.0 | `open /mapping-review` |

**Narration**

- 2:28.0–2:44.0: Mapping Review: every automatic link or suggestion waits for a person to approve

## Scene 8 · SCA workspace

- **Start / end:** 2:44.0 – 3:14.0
- **Screens:** /assess/workspace
- **Actions:** SCA persona records a determination → Saved – moved to next control → Undo
- **Production notes:** Human determination only

| Time | On-screen event |
|---|---|
| 2:44.0 | `persona sca` |
| 2:44.1 | `open /assess/workspace` |
| 2:47.5 | `click [data-testid^="sca-item-"]` |
| 2:51.2 | `click [data-testid="sca-determination"] input[type=checkbox]` |
| 2:52.7 | `click [data-testid="method-examine"]` |
| 2:56.0 | `click [data-testid="assessment-save"]` |
| 3:01.2 | `click [data-testid="sca-moved-undo"]` |

**Narration**

- 2:44.0–2:59.0: SCA workspace: the assessor records the determination – AI never does
- 2:59.0–3:14.0: “Saved – moved to next control”, with Undo

## Scene 9 · Authorize & eMASS exports

- **Start / end:** 3:14.0 – 3:46.0
- **Screens:** /systems/:id/authorization, /test-results
- **Actions:** Package, OSCAL, eMASS Implementation Plan; TR export mode + history
- **Production notes:** Deterministic TR export

| Time | On-screen event |
|---|---|
| 3:14.0 | `persona issm` |
| 3:14.1 | `open /systems/f2e6b2e4-57d2-4529-8105-4170076b05cc/authorization` |
| 3:25.7 | `open /test-results` |

**Narration**

- 3:14.0–3:30.0: Authorize package: SSP/SAR/RAR drafts, OSCAL and the eMASS Implementation Plan
- 3:30.0–3:46.0: eMASS Test Results export: pre-populated or blank-template mode, with validation

## Scene 10 · Monitoring

- **Start / end:** 3:46.0 – 4:04.0
- **Screens:** /rmf/monitor, /traceability
- **Actions:** Monitor tiles; traceability count
- **Production notes:** —

| Time | On-screen event |
|---|---|
| 3:46.0 | `open /rmf/monitor` |
| 3:52.8 | `open /traceability` |

**Narration**

- 3:46.0–4:04.0: Continuous monitoring and traceability across controls, evidence and findings

## Scene 11 · Themes & phone

- **Start / end:** 4:04.0 – 4:44.0
- **Screens:** /dashboard, /rmf-workflow, phone card
- **Actions:** Light → dark → light; live 390 px dark capture
- **Production notes:** Phone frame is a live capture

| Time | On-screen event |
|---|---|
| 4:04.0 | `open /dashboard` |
| 4:06.2 | `click [data-testid="theme-toggle-btn"]` |
| 4:09.9 | `open /rmf-workflow` |
| 4:14.2 | `click [data-testid="theme-toggle-btn"]` |
| 4:17.5 | `open phone.html` |

**Narration**

- 4:04.0–4:17.0: Light and dark themes
- 4:17.0–4:44.0: Works at phone width

## Scene 12 · Closing

- **Start / end:** 4:44.0 – 5:00.0
- **Screens:** Closing card
- **Actions:** —
- **Production notes:** —

| Time | On-screen event |
|---|---|
| 4:44.0 | `open closing.html` |

**Narration**

- 4:44.0–5:00.0: IronVision AI · Get audit-ready. Stay audit-ready.
