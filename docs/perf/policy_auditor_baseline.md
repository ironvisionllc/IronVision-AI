# Policy Auditor – baseline profile (analyzer v-current, measured BEFORE any v2 change)

Raw data: `policy_auditor_baseline.json` and `runs/base_*.json`. Real OpenRouter `anthropic/claude-sonnet-5.5`, 4 concurrent coverage calls (v-current setting), preview DB, SYNTHETIC bench org.

| policy | controls | requirements | wall | coverage AI calls | p50 / p95 per call | input / output tokens | cost | deterministic stage | AI stage | DB queries (time) | pool checkouts | idle-in-txn before/after |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| p20 | 20 | 185 | 76.5 s | 30 | 4.9 / 10.6 s | 195k / 23k | $0.62 | – | – | – | – | 0/0 |
| p100 | 100 | 888 | 204.3 s | 142 | 3.9 / 9.4 s | 1.07M / 77k | $2.92 | 15.8 s (×2) | – | – | – | 0/0 |
| p284 | 284 | 2,986 | 692.5 s | 421 (+1 audit) | 3.8 / 5.9 s | 3.20M / 197k | $8.38 | 139.9 s, computed twice (store_and_coverage 141.3 s) | 548.4 s | 9,527 (1.13 s) | 429 | 0/0 |

Findings:
- **Wall time is dominated by the AI stage.** 421 sequential-ish calls run at 4-way concurrency. Each call re-sends the policy text (up to 24k chars), so about 94% of tokens are repeated input.
- **The deterministic stage was the second-largest cost**, at 140 s on p284. It ran twice per analysis (prefetch, then analyze), with a regex per (requirement × sentence). This is now memoised and indexed, giving identical results about 10× faster.
- DB time is negligible: 1.1 s across 9.5k queries. No idle-in-transaction after the `65d8146` fix.
- No rate-limit (429) waits or retries were observed at 4 concurrent calls. Queue wait was not measured separately here; the bench runs the handler directly, so active time equals wall time.
- Large inputs were truncated: v-current sends ≤24k chars per call. On p284 (357k chars), later sections were never visible to the AI, which explains its low citation validity (0.456).
