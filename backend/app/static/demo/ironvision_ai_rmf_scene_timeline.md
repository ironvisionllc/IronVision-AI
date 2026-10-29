# IronVision AI – 3:10 product demo · scene timeline

Video: 1920×1080, 30 fps, H.264 High, silent, no burned-in captions, duration 190.00 s. Scene starts measured by the recorder.

| # | Scene | Start | End | Screens | What happens |
|---|---|---|---|---|---|
| 1 | Intro | 0:00.0 | 0:08.0 | Intro card | Brand card fades in and out |
| 2 | RMF dashboard & Guided Mode | 0:08.0 | 0:30.0 | /dashboard, /rmf/categorize | Point through the seven RMF steps and readiness; Guided Mode on → panel → off |
| 3 | Import Center | 0:30.0 | 0:57.0 | /systems/:id/import-center, review page | Upload SYNTHETIC eMASS Control Information → detected → review → accept safe → apply |
| 4 | Import management | 0:57.0 | 1:05.0 | /import-center/manage/:id | Delete everything this import created → 30-day Undo (restore) |
| 5 | Control Workbench | 1:05.0 | 1:25.0 | /systems/:id/controls/ac-2 | Status + statement, Evidence tab → Attach evidence → upload → Completed – next |
| 6 | AI Policy Auditor | 1:25.0 | 2:00.0 | /policy-auditor/:id | AC-2 checklist (AC-2 not yet mapped): CCI-000010 met with AI-verified quote; CCI-002124 needs manual review with candidate passages → Use this passage → “Sent to Mapping Review as a human proposal – an authorized reviewer decides.” |
| 7 | Mapping Review | 2:00.0 | 2:10.0 | /mapping-review | Policy coverage tab: that new AC-2 human proposal (pending) → Approve → “1 item(s) approved” |
| 8 | SCA workspace | 2:10.0 | 2:30.0 | /assess/workspace | SCA persona: evidence panel → objective, method, result → Save → Saved – moved to next control |
| 9 | Authorization & exports | 2:30.0 | 2:50.0 | /systems/:id/authorization, /test-results | SSP/SAR/RAR status, OSCAL, eMASS Implementation Plan; TR export mode + history |
| 10 | Continuous monitoring | 2:50.0 | 3:05.0 | /rmf/monitor, /traceability | Current/stale evidence, findings, POA&Ms, schedule; traceability |
| 11 | Closing | 3:05.0 | 3:10.0 | Closing card | IronVision AI · Enterprise GRC, Made Intelligent. · Get audit-ready. Stay audit-ready. · Request Your Demo Today |

## On-screen events

| Time | Event |
|---|---|
| 0:00.0 | `open intro_mkt.html` |
| 0:08.0 | `open /dashboard` |
| 0:20.5 | `click [data-testid="guided-toggle"]` |
| 0:21.3 | `open /rmf/categorize` |
| 0:28.5 | `click [data-testid="guided-toggle"]` |
| 0:30.0 | `open /systems/8897c4f4-2113-438a-88f5-2d9847990c24/import-center` |
| 0:31.7 | `upload SYNTHETIC_LTP_ControlInfo.xlsx` |
| 0:36.2 | `click [data-testid="ic-import-0"]` |
| 0:39.3 | `click [data-testid="ic-result-0"] a` |
| 0:45.5 | `click [data-testid="import-accept-safe"]` |
| 0:48.3 | `click [data-testid="import-apply-btn"]` |
| 0:57.0 | `open /import-center` |
| 0:57.9 | `click [data-testid^="ic-hist-emass-"]:has-text("SYNTHETIC_LTP_ControlInfo.xlsx") [data-testid^="ic-manage-"]` |
| 1:00.4 | `click [data-testid="mid-delete-everything"]` |
| 1:03.0 | `click [data-testid^="mid-undo-"]` |
| 1:05.0 | `open /systems/8897c4f4-2113-438a-88f5-2d9847990c24/controls/ac-2` |
| 1:11.3 | `click [data-testid="wb-tab-evidence"]` |
| 1:13.3 | `click [data-testid="wb-attach-evidence-btn"]` |
| 1:20.3 | `upload SYNTHETIC_AC-2_quarterly_account_review.txt` |
| 1:25.0 | `open /policy-auditor/c447178e-589f-4699-bf13-5bdec938e058` |
| 1:28.5 | `click [data-testid="coverage-toggle-ac-2"]` |
| 1:53.3 | `click [data-testid="use-candidate-ac-2-CCI-002124"]` |
| 2:00.0 | `open /mapping-review` |
| 2:00.9 | `click [data-testid="queue-tab-policy_map"]` |
| 2:04.8 | `click [data-testid^="queue-item-pm:"]:has-text("Raven Logistics"):has(:text-is("AC-2")) [data-testid^="queue-approve-"]` |
| 2:10.0 | `persona sca` |
| 2:10.1 | `open /assess/workspace` |
| 2:11.1 | `click [data-testid^="sca-item-"]` |
| 2:17.3 | `click [data-testid="sca-determination"] input[type=checkbox]` |
| 2:18.5 | `click [data-testid="method-examine"]` |
| 2:21.3 | `click [data-testid="assessment-save"]` |
| 2:30.0 | `persona issm` |
| 2:30.1 | `open /systems/f7ed8e22-0df5-4738-b5cf-0a7dce0c76ab/authorization` |
| 2:39.7 | `open /test-results` |
| 2:50.0 | `open /rmf/monitor` |
| 2:57.4 | `open /traceability` |
| 3:05.0 | `open closing_mkt.html` |
