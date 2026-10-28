# IronVision AI – RMF product demo · scene timeline

Video: 1920×1080, 30 fps, H.264, no audio, duration 300.02 s. Times below are measured from the recording (event log of the recorder).

## Scene 1 · Intro & Login

- **Start / end:** 0:00.0 – 0:20.0
- **Screens:** Intro card (synthetic-data notice) → login → Explore the demo → RMF overview
- **Actions:** Intro card; points at brand and the synthetic-data caption; clicks Explore the demo; points at the SYNTHETIC banner and the persona switcher (ISSO).
- **Production notes:** Intro card is an authored HTML branding card. Sign-in load time is cut.

| Time | On-screen event |
|---|---|
| 0:00.0 | `open intro.html` |
| 0:05.9 | `open /login` |
| 0:14.2 | `click [data-testid="demo-login-btn"]` |
| 0:14.8 | `persona isso` |
| 0:15.9 | `open /rmf-workflow` |

**Narration**

- 0:00.0–0:06.0: IronVision AI: human-approved AI for the NIST Risk Management Framework.
- 0:06.5–0:13.0: This is a shared demonstration workspace with synthetic data only, one click from sign-in.
- 0:13.5–0:20.0: Personas let one presenter act as ISSO, assessor or AO; the active role is always shown.

## Scene 2 · Command center & navigation

- **Start / end:** 0:20.0 – 0:45.0
- **Screens:** RMF overview (LTP)
- **Actions:** Walks the 7 step cards and Next action; points at Import Center and Policies in the RMF-ordered navigation and the system selector; opens the Import Center.
- **Production notes:** Persona and system were set before the scene (cut).

| Time | On-screen event |
|---|---|
| 0:38.7 | `click nav [data-testid="nav-import-center"]` |

**Narration**

- 0:20.0–0:31.0: The RMF overview is the command center: all seven NIST 800-37 steps, computed from live records.
- 0:31.0–0:38.0: Navigation follows the RMF steps, with the Import Center and Policies one click away.
- 0:38.0–0:45.0: Every screen works on the selected system, shown at the top.

## Scene 3 · Import Center

- **Start / end:** 0:45.0 – 1:35.0
- **Screens:** System Import Center; eMASS import review
- **Actions:** Uploads SYNTHETIC_LTP_ControlInfo.xlsx; type detected; Import; opens the review; points at Accept all conflict-free changes; Apply.
- **Production notes:** The file is a synthetic 3-row Control Information export. The apply wait is cut.

| Time | On-screen event |
|---|---|
| 0:48.1 | `upload SYNTHETIC_LTP_ControlInfo.xlsx` |
| 0:53.5 | `click [data-testid="ic-import-0"]` |
| 0:57.9 | `click [data-testid="ic-result-0"] a` |
| 1:06.6 | `click [data-testid="import-accept-safe"]` |
| 1:11.4 | `click [data-testid="import-apply-btn"]` |

**Narration**

- 0:45.0–0:56.0: The Import Center takes eMASS workbooks, test results, inventories, scans and policies, and detects each file's type.
- 0:56.0–1:06.0: Here a synthetic eMASS Control Information export is imported into the current system.
- 1:06.0–1:20.0: Review shows every change before it lands: current value, imported value, and anything that needs a decision.
- 1:20.0–1:35.0: Conflict-free changes are accepted in one step and applied through the normal save paths, with full audit.

## Scene 4 · Manage imported data

- **Start / end:** 1:35.0 – 2:20.0
- **Screens:** Import Center history; Manage imported data; scan run findings
- **Actions:** Opens Manage imported data from history; sections and Imported-from chips; selects a field; Delete everything this import created; Undo from History; scan run shows Imported-from chips and the multi-select delete bar (not clicked).
- **Production notes:** After recording the demo import is reverted in full (audited).

| Time | On-screen event |
|---|---|
| 1:35.0 | `open /import-center` |
| 1:39.4 | `click [data-testid^="ic-hist-emass-"]:has-text("SYNTHETIC_LTP_ControlInfo.xlsx") [data-testid^="ic-manage-"]` |
| 1:50.2 | `click [data-testid^="mid-select-"]` |
| 1:54.5 | `click [data-testid="mid-delete-everything"]` |
| 1:59.8 | `click [data-testid^="mid-undo-"]` |
| 2:03.4 | `open /ingest-runs/20f9864f-ee1d-4664-9586-9fcad887f375` |
| 2:07.7 | `click [data-testid^="imp-select-"]` |

**Narration**

- 1:35.0–1:46.0: Manage imported data shows everything one import populated, grouped by section, with the value before and after.
- 1:46.0–1:57.0: Restore, clear or delete per field, per section, or everything the import created. The system itself is kept.
- 1:57.0–2:08.0: Every operation can be undone for thirty days, and approved decisions are never removed, only flagged for re-review.
- 2:08.0–2:20.0: Destination screens mark imported rows with their source file, with multi-select delete and undo.

## Scene 5 · Policy Auditor – no silent misses

- **Start / end:** 2:20.0 – 3:05.0
- **Screens:** Policy detail (Access Control Policy)
- **Actions:** Coverage checklist; keyword-only/needs manual review labels, confidence, candidate passages; reading report warnings; Found it here (not sent).
- **Production notes:** Shows the stored analysis; no AI call is made during recording.

| Time | On-screen event |
|---|---|
| 2:20.0 | `open /policy-auditor/e8568b6c-88cf-443b-a461-a85f80f119f9` |
| 2:29.8 | `click [data-testid="coverage-toggle-ac-2"]` |

**Narration**

- 2:20.0–2:32.0: The Policy Auditor checks each policy against every control requirement, reading the whole document.
- 2:32.0–2:44.0: No silent misses: a requirement is only reported missing after a second look finds nothing.
- 2:44.0–2:55.0: Otherwise it says needs manual review, with confidence and the closest candidate passages.
- 2:55.0–3:05.0: If the reviewer finds the language, Found it here records the passage for a human mapping decision.

## Scene 6 · Assess & Authorize

- **Start / end:** 3:05.0 – 3:45.0
- **Screens:** Scan run (ltp_weekly_scan.nessus); Authorization package; POA&M
- **Actions:** Findings mapped to controls; package POA&Ms and OSCAL exports; AO-only decision panel; POA&M list.
- **Production notes:** No decision is recorded.

| Time | On-screen event |
|---|---|
| 3:05.0 | `open /ingest-runs/20f9864f-ee1d-4664-9586-9fcad887f375` |
| 3:11.2 | `open /systems/0e65c746-fca5-49e2-b0a4-07b2fab17ee6/authorization` |
| 3:21.1 | `click nav [data-testid="nav-poam"]` |

**Narration**

- 3:05.0–3:16.0: Scan findings arrive hashed, deduplicated and mapped through CCIs to NIST 800-53 controls.
- 3:16.0–3:30.0: The authorization package brings the SSP, assessment results, POA&Ms and OSCAL exports together.
- 3:30.0–3:45.0: The decision is AO-only: the ISSO submits, the ISSM endorses, and separation of duties is enforced.

## Scene 7 · Continuous Monitoring

- **Start / end:** 3:45.0 – 4:25.0
- **Screens:** Step 7 Monitor; Evidence Ledger; Traceability
- **Actions:** Monitor stat cards; ledger with Verify integrity and hashes; traceability count.
- **Production notes:** The audit log is not shown (it lists client IP details).

| Time | On-screen event |
|---|---|
| 3:45.0 | `open /rmf/monitor` |
| 3:54.9 | `click [data-testid="mon-go-ledger"]` |
| 4:06.1 | `open /traceability` |

**Narration**

- 3:45.0–3:55.0: Continuous monitoring watches evidence freshness, CAT I findings, CISA KEV and overdue POA&Ms.
- 3:55.5–4:10.0: The Evidence Ledger keeps every artifact with its SHA-256 hash, provenance and versions.
- 4:10.0–4:25.0: Traceability links each control to evidence, findings, POA&Ms and assessments.

## Scene 8 · Closing

- **Start / end:** 4:25.0 – 5:00.0
- **Screens:** RMF overview; closing card
- **Actions:** Returns to the RMF overview; closing card fades in and holds.
- **Production notes:** Authored HTML branding card.

| Time | On-screen event |
|---|---|
| 4:25.0 | `open /rmf-workflow` |
| 4:38.0 | `open closing.html` |

**Narration**

- 4:25.0–4:38.0: From preparation to continuous monitoring, the whole lifecycle stays in one place.
- 4:38.5–4:50.0: IronVision AI: AI does the heavy lifting; people keep the authority.
- 4:50.5–4:59.5: Get audit-ready, and stay audit-ready. Request your demo today.
