
## Usability-test rounds (2026-10-28) – what changed the numbers

The after walk takes the shortest path the new UI offers (`NEW` branches in `tasks.py`; the old-UI steps stay for the baseline record). A select that already holds the requested value is not counted.

- Categorize 4→2 clicks, 3→0 fields: information types and PII captured at registration are shown as "Answered · Edit".
- Update a control 6→4 (re-measured after the label change): "Jump to control" box (Enter → Implementation tab, editor focused, sticky "Save statement"); the status keeps its own "Save status".
- Attach evidence 7→3 clicks, 2→0 page changes: "Attach evidence" on the control's Evidence tab opens an in-app dialog (target control, drop zone + Choose file, progress) → upload + link, no source; "Completed – next: …" stays on the tab.
- Import test results 4→3, page changes 2→1: Import Center directly, selected system pre-set.
- Prepare a package, page changes 3→1: Authorize step → "Submit package / record AO decision".
- Continuous monitoring 5→4: one "Save & submit for ISSM approval" (ISSM approval still required).

Tasks that did not improve and why:
- Register (6 clicks, 2→3 page changes): the start choice (scratch / eMASS migration / copy) is a real decision; the extra page change is the hand-off to Select.
- Select a baseline (5): Preview → Apply is kept – it shows the control-set change before it is made.
- Import Implementation Plan (6→5): Open review → Apply is the approval step for imported changes.
- Review a finding (5 clicks, 3 page changes): the finding is on another system (switch system), then control → Findings tab → finding.
- POA&M (2), SSP (3): already minimal.
