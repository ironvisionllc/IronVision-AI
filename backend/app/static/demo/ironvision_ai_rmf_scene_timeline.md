# IronVision AI – 3:45 product demo · scene timeline

Video: 1920×1080, 30 fps, H.264 High, silent, no burned-in captions, duration 225.01 s. Scene starts measured by the recorder.

| # | Scene | Start | End | Screens | What happens |
|---|---|---|---|---|---|
| 1 | Intro | 0:00.0 | 0:07.0 | Intro card | Brand card fades in and out |
| 2 | RMF dashboard & Guided Mode | 0:07.0 | 0:25.0 | /dashboard, /rmf/categorize | Seven RMF steps and readiness; Guided Mode on → panel → off |
| 3 | CNSSI 1253 categorization | 0:25.0 | 0:37.0 | /rmf/categorize (LTP) | NSS = yes → CNSSI 1253 → C Moderate, I High, A Low → security category per objective (no single high-water mark) → Appendix D baseline (not saved) |
| 4 | Import Center – eMASS round-trip | 0:37.0 | 1:02.0 | /systems/:id/import-center, /test-results | Upload BLANK_TRExport.xlsx + SYNTHETIC Control Information (2 s, removed before import) → detected → Import → TR column mapping → generate (rules, no AI) → validated export into the same template |
| 5 | Import management | 1:02.0 | 1:08.0 | /import-center/manage/:id | Control Information import (applied off-camera): delete everything → Undo |
| 6 | Control Workbench | 1:08.0 | 1:24.0 | /systems/:id/controls/ac-2 | Implementation status + statement → Evidence → Attach evidence → Completed |
| 7 | AI Policy Auditor | 1:24.0 | 1:56.0 | /policy-auditor/:id | Stored AI result: CCI-000010 verified quote; CCI-002124 manual review + candidate passages → Use this passage → human proposal |
| 8 | Mapping Review | 1:56.0 | 2:05.0 | /mapping-review | That AC-2 proposal → Approve |
| 9 | SCA workspace | 2:05.0 | 2:22.0 | /assess/workspace | “Acting as SCA” → evidence → objective, method, result → Save |
| 10 | POA&M | 2:22.0 | 2:42.0 | /ingest-runs/:id (ACAS), /poams/:id | Open ACAS finding → Add to POA&M → due date + plan → milestone with date → Request risk acceptance (ISSM endorses → AO decides) → pending |
| 11 | Tamper-evident audit log | 2:42.0 | 2:52.0 | /admin (Audit events) | Verify chain → “CHAIN VALID · N events” |
| 12 | Continuous monitoring | 2:52.0 | 3:05.0 | /rmf/monitor, /traceability | Current/stale evidence, findings, POA&Ms, schedule; traceability |
| 13 | Authorization package | 3:05.0 | 3:12.0 | /systems/:id/authorization | SSP/SAR/RAR, OSCAL, eMASS Implementation Plan |
| 14 | AO decision | 3:12.0 | 3:38.0 | /systems/:id/authorization (AO persona) | “Acting as AO” → options ATO / IATT / DATO / ATO with conditions → expiry +3 years, 2 conditions, rationale → Record decision (simulated signature) → “Authorized (ATO w/ conditions) · expires …” |
| 15 | Closing | 3:38.0 | 3:45.0 | Closing card | IronVision AI · Enterprise GRC, Made Intelligent. · Get audit-ready. Stay audit-ready. · Request Your Demo Today |

## On-screen events

| Time | Event |
|---|---|
| 0:00.0 | `open intro_mkt.html` |
| 0:07.0 | `open /dashboard` |
| 0:16.2 | `click [data-testid="guided-toggle"]` |
| 0:16.9 | `open /rmf/categorize` |
| 0:22.3 | `click [data-testid="guided-toggle"]` |
| 0:25.0 | `open /rmf/categorize` |
| 0:32.3 | `open /rmf/select` |
| 0:34.7 | `click [data-testid="select-next-1"]` |
| 0:37.0 | `open /systems/a6cb0a78-8961-4ae8-ad0b-093feb575f9e/import-center` |
| 0:37.8 | `upload BLANK_TRExport.xlsx + SYNTHETIC_LTP_ControlInfo.xlsx` |
| 0:40.3 | `click [data-testid^="ic-file-"]:has-text("SYNTHETIC_LTP_ControlInfo.xlsx") [data-testid^="ic-remove-"]` |
| 0:43.0 | `click [data-testid^="ic-file-"]:has-text("BLANK_TRExport.xlsx") [data-testid^="ic-import-"]` |
| 0:45.5 | `click [data-testid^="ic-file-"]:has-text("BLANK_TRExport.xlsx") [data-testid^="ic-open-"]` |
| 0:51.2 | `click [data-testid="tr-generate-populate"], [data-testid="tr-generate-btn"]` |
| 0:54.6 | `click [data-testid="tr-export"]` |
| 1:02.0 | `open /import-center` |
| 1:02.8 | `click [data-testid^="ic-hist-emass-"]:has-text("SYNTHETIC_LTP_ControlInfo.xlsx") [data-testid^="ic-manage-"]` |
| 1:03.7 | `click [data-testid="mid-delete-everything"]` |
| 1:04.7 | `click [data-testid^="mid-undo-"]` |
| 1:08.0 | `open /systems/a6cb0a78-8961-4ae8-ad0b-093feb575f9e/controls/ac-2` |
| 1:13.1 | `click [data-testid="wb-tab-evidence"]` |
| 1:14.7 | `click [data-testid="wb-attach-evidence-btn"]` |
| 1:20.2 | `upload SYNTHETIC_AC-2_quarterly_account_review.txt` |
| 1:24.0 | `open /policy-auditor/a40d89a7-6e36-4325-8c58-6f4550949e76` |
| 1:26.8 | `click [data-testid="coverage-toggle-ac-2"]` |
| 1:47.7 | `click [data-testid="use-candidate-ac-2-CCI-002124"]` |
| 1:56.0 | `open /mapping-review` |
| 1:56.7 | `click [data-testid="queue-tab-policy_map"]` |
| 2:00.0 | `click [data-testid^="queue-item-pm:"]:has-text("Raven Logistics"):has(:text-is("AC-2")) [data-testid^="queue-approve-"]` |
| 2:05.0 | `persona sca` |
| 2:05.1 | `open /assess/workspace` |
| 2:08.2 | `click [data-testid^="sca-item-"]` |
| 2:11.8 | `click [data-testid="sca-determination"] input[type=checkbox]` |
| 2:12.9 | `click [data-testid="method-examine"]` |
| 2:15.4 | `click [data-testid="assessment-save"]` |
| 2:22.0 | `persona isso` |
| 2:22.1 | `open /ingest-runs/20741b7e-dc26-4812-a7d1-18f13732f1de` |
| 2:24.0 | `click [data-testid^="add-to-poam-"]` |
| 2:28.6 | `click [data-testid="poam-form-submit"]` |
| 2:30.6 | `click [data-testid="milestone-add"]` |
| 2:31.7 | `click [data-testid="poam-request-risk-btn"]` |
| 2:36.2 | `click [data-testid="poam-risk-submit"]` |
| 2:42.0 | `persona issm` |
| 2:42.1 | `open /admin` |
| 2:45.1 | `click [data-testid="audit-verify-btn"]` |
| 2:52.0 | `open /rmf/monitor` |
| 2:58.3 | `open /traceability` |
| 3:05.0 | `open /systems/a6cb0a78-8961-4ae8-ad0b-093feb575f9e/authorization` |
| 3:12.0 | `persona ao` |
| 3:12.1 | `open /systems/a6cb0a78-8961-4ae8-ad0b-093feb575f9e/authorization` |
| 3:21.6 | `click [data-testid="authz-conditions"]` |
| 3:24.7 | `click [data-testid="authz-rationale"]` |
| 3:27.2 | `click [data-testid="authz-record-btn"]` |
| 3:38.0 | `open closing_mkt.html` |
