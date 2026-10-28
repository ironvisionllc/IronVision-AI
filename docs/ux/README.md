# IronVision UX simplification – Phase 1 (audit, proposal, baseline, mockups)

No app behaviour or production UI was changed. The mockups are static HTML in `mockups/`. They are not routed or wired into the app.

| File | Content |
|---|---|
| `AUDIT.md` | Route inventory (33 routes with file refs), per-screen findings, top-15 complexity sources |
| `CONNECTEDNESS.md` | 9 "should flow" links: works, partial or not, with the exact gap; duplicate copies |
| `IA.md` | Navigation, step contents and page moves, status model, dashboard, My Work, Workbench 2-pane, glossary, Guided Mode, standard flows |
| `METRICS.md` | Baseline for 12 tasks on the current UI, with an eMASS reference column (cited, approximate) |
| `FLOWS.md` | Mermaid diagrams for the standard flows and the connected system record |
| `BACKLOG.md` | 7 incremental releases: effort, risk, data/permission impact, target metric |
| `COMPAT.md` | Deep links, testids, role matrix, tenant sweep: how each is preserved |
| `screens/current/` | 33 current-UI screenshots (evidence) |
| `screens/tasks/` | End-of-task screenshots |
| `mockups/png/` | 13 mockups |
| `before_after/` | 6 side-by-sides |
| `data/` | Raw crawl and metrics JSON |

**Scripts** in `scripts/ux_baseline/`. Re-run unchanged after the redesign:
- `crawl.py` – screens plus counts
- `tasks.py` – the 12 task walks
- `metrics_table.py` – rebuilds METRICS.md
- `mockups.py` + `render.py` – mockups, PNGs and side-by-sides

## Top 15 sources of complexity (detail and evidence in AUDIT.md)

| # | Source | Evidence |
|---|---|---|
| 1 | Two navigation systems: 29 sidebar links + stepper + 7 hub pages that only link onward | assess.png, nav.ts |
| 2 | Workbench overload: 13 selects, 15 checkboxes, 4 export buttons; list hidden until a filter is chosen | workbench.png |
| 3 | Generic, wrong "Next action: Assign key roles" on every step page | select.png, assess.png |
| 4 | SSP/SAR/RAR generation in 4 places | implement.png, authorization.png |
| 5 | SCA work scattered across Reviews, Workbench, Test Results and Mapping Review | assess.png, reviews.png |
| 6 | Mapping Review: 6 tabs + 3 sections, internal labels | mapping_review.png |
| 7 | Data entered twice: info type + PII at registration and in Categorize; inheritance in two editors | metrics register/categorize |
| 8 | Imports end without a next action | metrics import_impl/test_results/evidence |
| 9 | ISCM strategy (28 fields) inside Select | select.png |
| 10 | Evidence upload needs a "source" first (+3 clicks) | metrics evidence |
| 11 | Internal terminology (Ledger, ingest run, CCI view, eMASS Sync/import, S-5, Trigraph…) | per-route table |
| 12 | Status dimensions mixed without labels (implementation vs coverage vs assessment) | workbench.png |
| 13 | System detail is a second dashboard with no step status or "continue" | system_detail.png |
| 14 | No role-based home | nav.ts |
| 15 | Finding → POA&M → control only partly linked | metrics finding/poam |

## Connectedness

| Link | Status |
|---|---|
| eMASS TR import → Assess workspace | Partial – historical results stored, no SCA queue |
| SLCM → strategy + schedules | Strategy works; schedules partial (wait for ISSM approval, no notice) |
| Policy upload → mapping suggestions | Works (not shown on the control) |
| Approved mapping → coverage only | Works |
| ACAS → findings + assets + POA&M | Partial – no POA&M creation step |
| Categorization change → baseline notice | Works (Select); not on a dashboard |
| Completed assessment → package readiness | Partial – only when a document is generated |
| Evidence discoverable | Partial – not in finding, POA&M or assessment |
| Implementation Plan import → Implement + next action | Partial – no next action |

## IA summary

- **Global:** My Work · Systems · Import Center · Search · Admin.
- **System context:** dashboard + 7 RMF steps, visitable in any order. Each step has a status: complete / remaining / awaiting role / optional / blocked.

| Step | Sub-pages |
|---|---|
| Prepare | Roles, Profile & boundary, Inventory, PPSM |
| Categorize | Info types, PII, AO approval |
| Select | Baseline, Tailoring, Monitoring strategy |
| Implement | Workbench, Policies, Evidence, Inheritance |
| Assess | SCA workspace, Test results, Findings, Mapping review |
| Authorize | Package & documents, POA&M, Risk acceptance, Decision |
| Monitor | Dashboard, Schedules, Freshness, eMASS sync |

- **Workbench** becomes 2 panes: tree + 4 filters on the left; 6 tabs and 4 labelled status chips on the right; advanced eMASS fields collapsed.
- **Glossary** with exact labels and colours: `IA.md` §3.6.

## Baseline metrics (current UI, scripted; ISSO, SYNTHETIC sandbox)

| Task | Clicks | Page changes | Fields | Next action |
|---|---|---|---|---|
| Register | 6 | 2 | 3 | yes¹ |
| Categorize | 4 | 1 | 3 | yes¹ |
| Baseline | 5 | 1 | 1 | yes¹ |
| Import Implementation Plan | 6 | 2 | 2 | no |
| Update control | 6 | 2 | 2 | no |
| Attach evidence | 7 | 2 | 3 | no |
| Import test results | 4 | 2 | 1 | no |
| Review finding | 5 | 3 | 1 | no |
| POA&M (link to matching) | 2 | 1 | 0 | no |
| Generate SSP | 3 | 1 | 0 | yes¹ |
| Package | 3 | 3 | 0 | yes¹ |
| ISCM | 5 | 1 | 3 | yes¹ |
| **Total** | **56** | **21** | **19** | **6/12** |

- 3 tasks involve data entered twice: register and categorize share the info type and PII; evidence needs a source name first.
- ¹ Often only the generic banner.
- Scripted times, the eMASS reference column and the caveats are in METRICS.md.

## Backlog (UI-only; data and permission impact: none)

| Release | Items |
|---|---|
| R1 | Dashboard + step status + step-specific next action; RMF navigation |
| R2 | Workbench 2-pane; status glossary chips |
| R3 | Import Center 4-step flow with next action and auto evidence source; Mapping Review (3 tabs) |
| R4 | SCA assessment workspace; Package & documents + live readiness |
| R5 | My Work per role; registration de-duplication |
| R6 | Guided Mode; connectedness gaps (ACAS → POA&M suggestion, strategy-awaiting notice, suggestions on the control) |
| R7 | Saved filters, search, Help merge |
