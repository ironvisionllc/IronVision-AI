# 7 · Prioritized implementation backlog (incremental releases)

Rules for every release:
- **UI-only.** Existing APIs and records are reused.
- Data impact: **none**. Permission impact: **none**. The role matrix and SoD are unchanged; actions are only hidden where they are already denied.
- Each release ships on its own, behind no flag, with:
  - unit/RTL tests
  - the baseline task script re-run
  - the tenant sweep plus the full serial suite
  - old deep links redirected

| Rel | Item | Effort | Risk | Data / permission impact | Target metric |
|---|---|---|---|---|---|
| R1 | **System RMF dashboard** + "Continue where you left off" + per-step status model (computed from existing counts) + step-specific next action (replaces the generic "Assign key roles") | M (5–7 d) | Low | None / none | next_action_shown 6/12 (several only the generic banner) → 12/12 step-specific. Page changes to start any task −1. |
| R1 | **RMF navigation**: 7 steps + 5 global items, breadcrumbs, recently viewed. Old routes stay as aliases. | M (4–5 d) | Medium (deep links, testids) | None / none | Sidebar entries 29 → 12 (+ sub-items in context). Hub page changes removed. |
| R2 | **Workbench 2-pane**: always-visible tree, 4 filters, labelled status chips, 6 tabs, advanced fields collapsed | L (8–10 d) | Medium (most-used screen; many testids) | None / none | update_control clicks 6 → 3. Visible selects 13 → 4. |
| R2 | **Glossary in UI**: one StatusChip component per dimension + label renames | S (2–3 d) | Low | None / none | Terminology issues (audit list) → 0 |
| R3 | **Import Center flow**: Upload → Preview → Import → Completed, with next action and an "open in step" link. Evidence upload creates a default source automatically. | M (4–6 d) | Low | None / none. The source is the existing model, auto-created per system. | import_impl next action false → true. Evidence clicks 7 → 3, fields 3 → 1. |
| R3 | **Mapping Review simplified**: 3 tabs, reason inline, row actions, bulk approve high-confidence with a shared rationale (existing bulk API) | M (4–5 d) | Low | None / none (human approval kept) | Tabs 6 → 3. Visible buttons 51 → ≈20. |
| R4 | **Assessment workspace (SCA)**: one queue, with evidence + implementation + historical eMASS results side by side. Save & next. | L (7–9 d) | Medium (SCA independence: read-only for others) | None / none | Clicks per determination ≈ 5 → 2. TR import → SCA queue link closed. |
| R4 | **Package & documents** merged (one place for SSP/SAR/RAR/POA&M/OSCAL) + live readiness blockers | M (4–5 d) | Low | None / none | ssp: page changes 1. Duplicate doc buttons 4 → 1. |
| R5 | **My Work per role** (ISSO/SCA/ISSM/AO) from the existing queue, reviews and notifications | M (5–6 d) | Low | None / none | Time-to-first-action for a new user (scripted) −50% |
| R5 | **Registration de-duplication**: info types/PII owned by Categorize. Registration keeps a link to it. | S (2 d) | Medium (registration tests, PII binary flow) | None (fields still saved on the same record) / none | Fields entered twice 2 → 0 |
| R6 | **Guided Mode** toggle (per user preference, existing user settings) | M (4–5 d) | Low | User preference only / none | New-ISSO walkthrough without help pages |
| R6 | **Connectedness gaps**: ACAS → "create POA&M for N new findings" suggestion (human confirm); Monitor notice "strategy awaiting ISSM approval"; pending policy suggestions shown on the control | M (5 d) | Low | None / none (suggestions only, human creates) | Connectedness table: all rows → Works |
| R7 | Saved filters, ⌘K search everywhere, Help merge | S–M (3–4 d) | Low | User preference only | – |

Order rationale: dashboard and navigation first, because every later screen hangs off them. Then the three heaviest daily screens: Workbench, Import, Mapping Review. Then assessment, which fixes the SCA's scattered work.
