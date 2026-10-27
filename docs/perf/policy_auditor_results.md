# Policy Auditor – benchmark results (preview only, never deployed)

All numbers are REAL end-to-end runs. Each run goes through the worker handler `handle_policy_analyze` in-process, against the preview DB, with real OpenRouter calls to `anthropic/claude-sonnet-5.5`, in SYNTHETIC bench orgs.
- Raw per-run data: `docs/perf/runs/*.json`.
- Aggregates: `policy_auditor_baseline.json` (v-current), `policy_auditor_benchmarks.json` (v2) and `policy_auditor_ra_benchmark.json` (RA UAT policy).
- Regenerate with `python scripts/perf/build_report.py`.
- Cost uses the OpenRouter list price for anthropic/claude-sonnet-5.5: $2.00 per M input tokens, $10.00 per M output tokens (https://openrouter.ai/anthropic/claude-sonnet-5.5, checked 2026-10-27).

## Headline: first run, cold tenant cache

| policy | controls / requirements | v-current wall | v2 wall | speed-up | v-current calls | v2 calls | v-current cost | v2 cost | accuracy (P / R) old → new |
|---|---|---|---|---|---|---|---|---|---|
| p20 (AC) | 20 / 185 | 76.5 s | 22.8 s | 3.4× | 30 | 7 | $0.62 | $0.25 | 0.827/1.0 → 0.827/1.0 |
| p100 (multi-family) | 100 / 888 | 204.3 s | 43.9 s | 4.7× | 142 | 33 | $2.92 | $1.15 | 0.824/1.0 → 0.824/1.0 |
| p284 (representative) | 284 / 2986 | 692.5 s (11.5 min) | **138.5 s** (w16) / 121.4 s (w32) | 5.0–5.7× | 422 | 104 | $8.38 | $3.64 | 0.802/0.998 → 0.802/0.998 |
| RA UAT policy (user's DOCX) | 22 maps / 156 | 31.6 s | 17.0 s | 1.9× | 24 | 6 | $0.64 | $0.25 | 0.993/0.922 → 0.993/0.948 |

Targets:
- Typical policy under 2 min: **PASS** (p20 22.8 s, p100 43.9 s, RA 17.0 s).
- Representative 284-control policy in 2–3 min: **PASS** (138.5 s at the default 16 workers, 121.4 s at 32).
- Stretch goal of under 60 s for 284 controls: **not met**. The critical path is output-token throughput: about 278k output tokens across 104 batches, with p50 15 s per batch.

## Cache and incremental runs (v2)

| policy | first | repeat (no change) | incremental (one section edited) |
|---|---|---|---|
| p20 | 22.8 s, 7 calls | 7.9 s, 0 coverage calls (6 hits) | 21.4 s, 3 calls (4 hits) |
| p100 | 43.9 s, 33 calls | 9.5 s, 0 coverage calls (32 hits) | 16.6 s, 2 calls (31 hits) |
| p284 | 138.5 s, 104 calls | 31.3 s, 0 calls (103 hits) | 50.2 s, 4 calls (100 hits) |
| RA UAT | 17.0 s, 6 calls | **0.7 s, 0 calls** (5 batch hits plus the cached audit) | 16.1 s, 4 calls (2 hits) |

- The remaining repeat time on p284 (about 30 s) is not AI time. It is the deterministic stage plus writing 2,986 coverage rows plus verification.
- Incremental runs re-ask only the batches whose sections changed. A batch key covers the tenant, every requirement and every section hash (see the architecture doc).

## Concurrency sweep (p100, cache off)

| workers | wall | calls | p50 / p95 per call |
|---|---|---|---|
| 4 | 151.2 s | 45 | 12.8 / 19.6 s |
| 8 | 74.9 s | 39 | 13.5 / 19.4 s |
| 16 | 53.6 s | 43 | 14.1 / 20.1 s |
| 32 | 54.4 s | 43 | 14.7 / 20.6 s |

- For p100 the gain saturates at 16 workers, because the critical path is the longest batches. For p284, 32 workers gives 121 s vs 138 s.
- No 429s and no retries were observed at 32.
- **Default: 16** (`POLICY_AI_WORKERS`). The provider-aware token bucket is `POLICY_AI_RPM`/`POLICY_AI_TPM`.

## Accuracy

Synthetic corpus (builder-authored gold, `scripts/perf/score.py`):
- Precision and recall are identical old vs new on every policy.
- Citation validity is equal or better (p284: 0.456 → 0.461).
- Gap-guidance readability ≥ 0.95.
- Negative tests:
  - `neg_ra`: no AC-17 rows and no spurious positives, both analyzers.
  - `neg_unrel` (a travel policy): 0 coverage rows, both analyzers.
- The FP count (e.g. 589 on p284) is a corpus artefact shared by both analyzers. The generator reuses CCI/objective wording, so "not addressed" requirements get deterministic *partial* hits.

RA UAT policy, gold-labelled (`docs/perf/corpus/ra_raven.gold.json`: 156 requirements RA-1..RA-10, not-selected, withdrawn and a 15-control negative set; scored with `scripts/perf/score_ra.py`):

| run | recall (addressed) | false gaps on met | exact label | gold gaps flagged | review items | possible related (not proposed) | violations |
|---|---|---|---|---|---|---|---|
| v-current, before RA fixes (what the user saw) | 0.903 | 13 | 0.571 | 4/4 | 36 | 0 | RA-6 gap rows; not-selected not flagged |
| v-current, after fixes | 0.922 | 10 | 0.667 | 4/4 | 22 | 19 | none |
| v2, after fixes | **0.948** | **6** | **0.692** | 4/4 | 22 | 19 | none |

In every RA run after the fixes:
- No AC-17 or other negative-set maps, rows or findings, and no "remote access" mentions.
- RA-6 and RA-3(4) are flagged "policy states not selected", with no gap rows.
- Withdrawn RA-4 and RA-5(1)/(7)/(9) are not mapped.
- All 22 non-withdrawn traceability-matrix rows are quoted verbatim in their control's map.

## Reliability and responsiveness

- `idle in transaction` sessions before/after every run: 0/0. The test `test_no_transaction_during_ai_and_no_idle_in_transaction_after` checks that no pool connection is checked out during an AI call.
- Review Queue latency (`scripts/perf/queue_probe.py`, 3 s polling of `/mapping-review`): p50 377 ms / p95 424 ms idle, vs p50 364 ms during a v2 analysis. Bulk review keeps its own worker lane (`review.bulk`); `policy.analyze` never enters it.
- Failed and truncated batches keep their deterministic results and are split and re-asked. Split results are cached under the parent key.
- Tenant isolation:
  - Full OpenAPI sweep: 298/301 ops, 1,480 requests, 5 roles, PASS.
  - Storage-key probe: 924 probes, PASS.
  - v2 cache: the tenant-B identical document gets no tenant-A hit (`test_cache_tenant_scoped_and_incremental`).

## Baseline notes (v-current)

- One AI call per ≤8 requirements, 4 concurrent calls.
- Full policy text is sent each time (truncated at 24k chars), so on p284 most input tokens are repeated policy text: 3.2M input tokens, 422 calls.
- Deterministic stage on p284 was 140 s and computed twice. It was memoised and indexed for **both** analyzers: identical results, about 10× faster.
- The baseline p284 numbers were measured before that change.

## Tester round 2: evidence guard and generalisation (AC / SC demo policies)

Gold sets:
- `ra_raven.gold.json`: the user's RA policy, 156 requirements.
- `ac_raven.gold.json`: 194 requirements, 24 deliberate gaps, with AC-17 remote access as a positive case.
- `sc_raven.gold.json`: 151 requirements, 18 deliberate gaps.

Each set also has negative controls (15 per policy), not-selected and withdrawn controls. The AC/SC policies are SYNTHETIC demo-style DOCX files built by `scripts/perf/make_demo_policies.py`: numbered sections, tables, part tags, a traceability matrix, and not-selected / withdrawn / inherited lines. Scorer: `GOLD=<file> scripts/perf/score_ra.py <run>`.

| policy | analyzer | wall | AI calls | cost | precision | recall | exact | false gaps | gold gaps flagged | citation validity | off-subject met quotes | review items | possible related | violations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| RA (user) | v-current | 31.1 s | 24 | $0.64 | 0.987 | 0.981 | 0.660 | 2 | 4/4 | 1.0 | 0 | 22 | 19 | none |
| RA (user) | **v2** | 16.1 s | 6 | $0.24 | 0.987 | **1.000** | **0.699** | **0** | 4/4 | 1.0 | 0 | 22 | 19 | none |
| AC demo | v-current | 48.2 s | 29 | $0.43 | 0.909 | 1.000 | 0.732 | 0 | 23/24 | 1.0 | 0 | 18 | 8 | none |
| AC demo | **v2** | 14.7 s | 8 | $0.23 | 0.909 | 1.000 | 0.701 | 0 | 24/24 | 1.0 | 0 | 18 | 8 | none |
| SC demo | v-current | 28.9 s | 25 | $0.34 | 0.917 | 1.000 | 0.821 | 0 | 18/18 | 1.0 | 0 | 21 | 9 | none |
| SC demo | **v2** | 14.2 s | 6 | $0.17 | 0.924 | 1.000 | 0.815 | 0 | 18/18 | 1.0 | 0 | 21 | 9 | none |

Before and after the evidence guard, for RA under v2 (`ra_v2_first` → `ra_v2_final`):
- Recall 0.948 → 1.000.
- False gaps on met requirements 6 → 0.
- Met quotes that do not address the requirement's subject 32 → 0. The scorer ignores xx-1 policy-element rows, which legitimately quote section headings.

How to read precision: it treats any met or partial result as "addressed". Deliberate gaps that the analyzer flags as *partial* therefore count against precision, even though they are shown to the reviewer as gaps. "Gold gaps flagged" counts them as found.

## Tester round 3: progress, evidence wording, trigger relevance, snippet sentences

All v2, real model calls (`anthropic/claude-sonnet-5.5`), scored with the current scorer (`GOLD=docs/perf/corpus/<k>_raven.gold.json scripts/perf/score_ra.py <run>`). Before = `<k>_v2_final` (round 2); after = `<k>_v2_r7`.

| policy | run | wall | precision | recall | exact | false gaps | gold gaps flagged | citation validity | off-subject met quotes | violations |
|---|---|---|---|---|---|---|---|---|---|---|
| RA (user) | before | 16.1 s | 0.987 | 1.000 | 0.699 | 0 | 4/4 | 1.0 | 5 | none |
| RA (user) | **after** | 16.8 s | 0.987 | 1.000 | **0.737** | 0 | 4/4 | 1.0 | **0** | none |
| AC demo | before | 14.7 s | 0.909 | 1.000 | 0.701 | 0 | 24/24 | 1.0 | 3 | none |
| AC demo | **after** | 14.9 s | 0.909 | 1.000 | **0.753** | 0 | 24/24 | 1.0 | **0** | none |
| SC demo | before | 14.2 s | 0.924 | 1.000 | 0.815 | 0 | 18/18 | 1.0 | 0 | none |
| SC demo | **after** | 14.4 s | 0.917 | 1.000 | 0.795 | 0 | 18/18 | 1.0 | 0 | none |

Changes in this round:
- Trigger clauses ("when new vulnerabilities are identified and reported") need two condition terms when the condition has three or more. "Identified / reported / announced / published" count as one term. CCI-001056 is now backed by the re-scan sentence, not by threat-monitoring text.
- An AI quote that is only part of a sentence is widened to the full sentence before it is shown.

Intermediate run r6 had only the trigger rule. Its RA recall dropped to 0.994 because "announced" did not count as "reported", and it showed one fragment quote. r7 fixes both.

## Tester round 4: readable gaps, agreement, consistency across uploads

Before = `<k>_v2_r7` (round 3), after = `<k>_v2_r9`. All v2, real `anthropic/claude-sonnet-5.5`, same scorer.

| policy | run | wall | precision | recall | exact | false gaps | gold gaps flagged | citation validity | off-subject met | unreadable gaps | agreement errors | violations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| RA (user) | before | 16.8 s | 0.987 | 1.000 | 0.737 | 0 | 4/4 | 1.0 | 0 | 43 | 6 | none |
| RA (user) | **after** | 16.5 s | 0.987 | 1.000 | 0.744 | 0 | 4/4 | 1.0 | 0 | **0** | **0** | none |
| AC demo | before | 14.9 s | 0.909 | 1.000 | 0.753 | 0 | 24/24 | 1.0 | 0 | n/m | n/m | none |
| AC demo | **after** | 14.5 s | 0.909 | 1.000 | 0.737 | 0 | 24/24 | 1.0 | 0 | 0 | 0 | none |
| SC demo | before | 14.4 s | 0.917 | 1.000 | 0.795 | 0 | 18/18 | 1.0 | 0 | n/m | n/m | none |
| SC demo | **after** | 13.6 s | 0.917 | 1.000 | 0.795 | 0 | 18/18 | 1.0 | 0 | 0 | 0 | none |

- The RA "before" counts for unreadable gaps (43) and agreement errors (6) are the tester's, from one RA upload. n/m = not measured.
- Progress denominator now matches the final total: RA 156 = 156, AC 194 = 194, SC 151 = 151.
- Audit suggestions vs stored findings: SC had 8 suggestions and 7 findings stored, with a note explaining the one that was dropped.
