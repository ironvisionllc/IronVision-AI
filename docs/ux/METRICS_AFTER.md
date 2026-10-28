# Task metrics after the redesign (R1–R7)

Same 12 scripted tasks, ISSO persona, synthetic sandbox, fresh `UXB*` system per walk (archived automatically at the end). Rerun: `UX_PHASE=after python3 scripts/ux_baseline/tasks.py && python3 scripts/ux_baseline/compare.py`.

Selector changes made for the new layout are commented in `tasks.py` (step header navigation, Workbench tabs, one-off evidence upload). The evidence walk now uploads a valid SARIF file (the baseline file was rejected as unsupported in both runs).

| Task | Clicks | Page changes | Fields | Next action shown | Completed |
|---|---|---|---|---|---|
| Register a system | 6 → **6** | 2 → **3** | 3 → **3** | yes → **yes** | yes |
| Categorize | 4 → **4** | 1 → **1** | 3 → **3** | yes → **yes** | yes |
| Select a baseline | 5 → **5** | 1 → **1** | 1 → **1** | yes → **yes** | yes |
| Import implementation info (Implementation Plan) | 6 → **6** | 2 → **2** | 2 → **2** | no → **yes** | yes |
| Update a control | 6 → **5** | 2 → **2** | 2 → **2** | no → **yes** | yes |
| Attach evidence | 7 → **4** | 2 → **2** | 3 → **1** | no → **yes** | yes |
| Import test results | 4 → **5** | 2 → **3** | 1 → **1** | no → **yes** | yes |
| Review a finding | 5 → **3** | 3 → **1** | 1 → **1** | no → **no** | no – not found: [data-testid^=queue-open-] |
| Create/update a POA&M (from the finding) | 2 → **5** | 1 → **3** | 0 → **1** | no → **no** | yes |
| Generate an SSP | 3 → **3** | 1 → **1** | 0 → **0** | yes → **yes** | yes |
| Prepare an authorization package | 3 → **4** | 3 → **3** | 0 → **0** | yes → **yes** | yes |
| Configure continuous monitoring | 5 → **5** | 1 → **1** | 3 → **3** | yes → **yes** | yes |
| **Total** | 56 → **55** | 21 → **23** | 19 → **18** | 6/12 → **10/12** | 11/12 |
