# Task metrics after the redesign (R1–R7)

Same 12 scripted tasks, ISSO persona, synthetic sandbox, fresh `UXB*` system per walk (archived automatically at the end). Rerun: `UX_PHASE=after python3 scripts/ux_baseline/tasks.py && python3 scripts/ux_baseline/compare.py`.

Selector changes made for the new layout are commented in `tasks.py` (step header navigation, Workbench tabs, one-off evidence upload). The evidence walk now uploads a valid SARIF file (the baseline file was rejected as unsupported in both runs).

| Task | Clicks | Page changes | Fields | Next action shown | Completed |
|---|---|---|---|---|---|
| Register a system | 6 → **6** | 2 → **3** | 3 → **3** | yes → **yes** | yes |
| Categorize | 4 → **2** | 1 → **1** | 3 → **0** | yes → **yes** | yes |
| Select a baseline | 5 → **5** | 1 → **1** | 1 → **1** | yes → **yes** | yes |
| Import implementation info (Implementation Plan) | 6 → **5** | 2 → **2** | 2 → **1** | no → **yes** | yes |
| Update a control | 6 → **4** | 2 → **2** | 2 → **3** | no → **yes** | yes |
| Attach evidence | 7 → **2** | 2 → **0** | 3 → **1** | no → **yes** | yes |
| Import test results | 4 → **3** | 2 → **1** | 1 → **1** | no → **yes** | yes |
| Review a finding | 5 → **5** | 3 → **3** | 1 → **1** | no → **yes** | yes |
| Create/update a POA&M (from the finding) | 2 → **2** | 1 → **1** | 0 → **0** | no → **yes** | yes |
| Generate an SSP | 3 → **3** | 1 → **1** | 0 → **0** | yes → **yes** | yes |
| Prepare an authorization package | 3 → **3** | 3 → **1** | 0 → **0** | yes → **yes** | yes |
| Configure continuous monitoring | 5 → **4** | 1 → **1** | 3 → **3** | yes → **yes** | yes |
| **Total** | 56 → **44** | 21 → **17** | 19 → **14** | 6/12 → **12/12** | 12/12 |

## Usability-test round (2026-10-28) – what changed the numbers

The after walk now takes the shortest path the new UI offers (`NEW` branches in `tasks.py`; baseline steps are kept for the old-UI record). A select that already holds the requested value is not counted.

- Categorize 4→2 clicks, 3→0 fields: information types and PII captured at registration are shown as "Answered · Edit".
- Update a control 6→4: Workbench "Jump to control" box (Enter → Implementation tab, editor focused, sticky Save).
- Attach evidence 7→2 clicks, 2→0 page changes: "Attach evidence" on the control's Evidence tab (upload + link, no source).
- Import test results 4→3, page changes 2→1: Import Center directly, selected system pre-set.
- Prepare a package page changes 3→1: Authorize step → "Submit package / record AO decision".
- Continuous monitoring 5→4: one "Save & submit for ISSM approval" (ISSM approval still required).

Tasks that did not improve and why:
- Register (6 clicks, 2→3 page changes): the start choice (scratch / eMASS migration / copy) is a real decision; the extra page change is the hand-off to Select after registering.
- Select a baseline (5): Preview → Apply is kept on purpose – it shows the control-set change before it is made.
- Review a finding (5 clicks, 3 page changes): the finding is on another system (switch system), then control → Findings tab → finding.
- POA&M (2), SSP (3): already minimal; the SSP validate step is kept before download.
- Import Implementation Plan (6→5): Open review → Apply is the approval step for imported changes and is kept.
