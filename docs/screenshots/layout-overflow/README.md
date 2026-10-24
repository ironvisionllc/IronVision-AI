# Layout overflow fix: right side of pages cut off

**Root cause:** the main column (`AppShell` `<main>`) had `min-w-0` but also `overflow-x-hidden`. Its page sections are CSS grid / flex
containers whose children default to `min-width: auto`. One wide child stretched the whole column far past the viewport, e.g. the parameter
comparison table on Select, the health and JSON panels in Admin, or the decision-rules table. That made every panel up to 2,589 px wide at a
1280 px viewport, and `overflow-x-hidden` clipped it with no way to scroll.

**Global fix (no per-page patches):**
- `index.css`:
  - `.panel` and grid / flex-1 / flex-col children of main get `min-width: 0`;
  - long text wraps (`overflow-wrap: break-word`; `anywhere` for mono/code/td/dd; `pre` wraps);
  - dialogs get `max-width: calc(100vw - 2rem)` and scroll internally;
  - new `.iv-table-scroll` with a visible thin scrollbar and an optional sticky first column.
- Main is `overflow-x-auto` instead of `hidden`, as a safety net so nothing is ever unreachable. The check still fails if main overflows.
- New `components/common/TableScroll.tsx`. The shared `Table` and the 20 raw tables that had no scroll container now use it.
- `Panel` header actions wrap.

**Check:** `scripts/check_layout_overflow.py` covers 38 routes plus interactions (Select overlays expanded, parameter comparison, Policy
Auditor side-by-side, Mapping Review side-by-side) at 1280×800, 1440×900 and 1920×1080, plus 8 pages at 390×844. That is 122 page views.
- Before: 21 failures. After: 0.
- The full results are in `results-before.json` and `results-after.json`.
- Rerun: `SHOT_BASE=<preview url> SHOT_EMAIL=jordan.qa7731@example.com SHOT_PASSWORD=… python3 scripts/check_layout_overflow.py after`.
  It needs `pip install playwright httpx && python -m playwright install chromium`.

Pages that failed before (all other route × size combinations passed both times):

| Page | 1280x800 | 1440x900 | 1920x1080 | 390x844 |
|---|---|---|---|---|
| admin | FAIL→PASS | FAIL→PASS | pass | FAIL→PASS |
| control-detail | FAIL→PASS | pass | pass | – |
| control-detail-fips | FAIL→PASS | pass | pass | – |
| mapping-review | pass | pass | pass | FAIL→PASS |
| parameter-comparison | FAIL→PASS | FAIL→PASS | FAIL→PASS | FAIL→PASS |
| policy-detail | pass | pass | pass | FAIL→PASS |
| reviews | FAIL→PASS | FAIL→PASS | pass | – |
| select | FAIL→PASS | FAIL→PASS | FAIL→PASS | FAIL→PASS |
| select-fips | FAIL→PASS | FAIL→PASS | FAIL→PASS | – |
| test-results | pass | pass | pass | FAIL→PASS |

Screenshots: `before_*` and `after_*` for Select and Admin at 1280 and 1440.
