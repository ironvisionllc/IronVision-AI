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

## Tester round 5: requirement quoted verbatim, ODPs rendered, AI language gated

Gap/fix text no longer rewrites requirement clauses. It has three parts:
1. A fixed sentence: "The policy does not clearly address this requirement." or "Manual review needed: …".
2. `Requirement (<DISA CCI / NIST SP 800-53A objective>): “<verbatim text>”`. ODP placeholders are rendered as `[organization-defined …]` and `[organization-selected …: …]`, and `_ODP[nn]` references are removed or rewritten.
3. `Fix: … including the organization-defined value(s): …`.

Values the linked system has already defined are added, labelled "(organization-defined: <value>)". AI-suggested language (prompt `policy.coverage_refine@2.2.0`, field `suggestion`) is shown only if it passes `fluent()`.

Catalog sweep (`tests/test_tester_round5.py`): 1,579 CCIs and 1,030 objectives in RA, AC, SC, AU, CM and IR, 3 variants each, 7,827 texts. Result: 0 placeholder leaks, 0 empty values, 0 doubled words, 0 "a" before a vowel, 0 "will <non-verb>", 0 sentences without a finite verb. These checks apply to the synthesized text. Quoted authoritative text is not altered; for example, DISA's own "Conduct a impact-level categorization" in CCI-004617 is quoted as written.

| policy | run | wall | precision | recall | exact | false gaps | gold gaps flagged | citation validity | off-subject met | gap-text problems | AI suggestions shown | violations |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| RA (user) | r9 | 16.5 s | 0.987 | 1.000 | 0.744 | 0 | 4/4 | 1.0 | 0 | n/m | – | none |
| RA (user) | **r10** | 20.2 s | 0.987 | 1.000 | 0.744 | 0 | 4/4 | 1.0 | 0 | 0 | 11 of 35 | none |
| AC demo | r9 | 14.5 s | 0.909 | 1.000 | 0.737 | 0 | 24/24 | 1.0 | 0 | n/m | – | none |
| AC demo | **r10** | 21.8 s | 0.909 | 1.000 | 0.753 | 0 | 23/24 | 1.0 | 0 | 0 | 50 of 51 | none |
| SC demo | r9 | 13.6 s | 0.917 | 1.000 | 0.795 | 0 | 18/18 | 1.0 | 0 | n/m | – | none |
| SC demo | **r10** | 16.6 s | 0.924 | 1.000 | 0.861 | 0 | 18/18 | 1.0 | 0 | 0 | 25 of 25 | none |

Notes:
- Wall time rose by 3–7 s because the model now also writes suggestion text: output tokens went up roughly 15–25%.
- AC 23/24: AC-8 CCI-002248 was met in r10 through a table-cell quote. It was partial in r9 because the AI disagreed then. This is model variance, not a wording change.

## Round 5 follow-ups: values list, selection placeholders, single table-cell quotes (r11)

- Values are listed bracketed. The unbracketed CCI phrase stops at a stop word, max 4 words ("[organization-defined corrective actions]"). Selections list their actual options.
- AI suggestions (prompt `coverage_refine@2.3.0`) must use the same ODP types as the requirement: Assignment ↔ `[organization-defined …]`, Selection ↔ `[organization-selected: …]`.
- A quote that is only a single table cell can't make a row met unless a prose sentence also states it.

| policy | wall | precision | recall | exact | false gaps | gold gaps flagged | citation validity | violations |
|---|---|---|---|---|---|---|---|---|
| RA | 21.0 s | 0.987 | 0.994 | 0.724 | 0 | 4/4 | 1.0 | none |
| AC | 23.3 s | 0.909 | 1.000 | 0.747 | 0 | 24/24 | 1.0 | none |
| SC | 21.6 s | 0.917 | 1.000 | 0.848 | 0 | 18/18 | 1.0 | none |

AC-8 CCI-002248 is now partial with manual review, so the AC gold gaps flagged are back to 24/24. There were 4 table-cell downgrades in AC.

## No silent misses – spend log (2026-10-28, preview only)

Prices: OpenRouter list price for anthropic/claude-sonnet-5.5. Input $2.00/M, output $10.00/M. Anthropic prompt cache: write 1.25× ($2.50/M), read 0.1× ($0.20/M). Token counts come from the provider usage fields (`prompt_tokens`, `completion_tokens`, `prompt_tokens_details.cached_tokens` / `cache_write_tokens`), logged per run in `v2.tokens_*`.

| run | design | wall | AI calls | input | cached read | cache write | output | cost (actual tokens × list price) |
|---|---|---|---|---|---|---|---|---|
| cache probe (2 calls) | 12.5k-token prefix | – | 2 | 25,026 | 12,491 | 12,491 | 10 | ≈ $0.06 |
| p284 whole-doc in every batch (ABORTED) | whole document per batch, 16 parallel, 70 truncation splits | ~20 min | 322 | 33,868,252 | not recorded (stats lost on abort) | not recorded | 396,901 | **≈ $10–17 estimated** (all reads ≈ $10.7; realistic with ~16 first-wave writes ≈ $14.6; the no-cache upper bound would be $71.7, but caching was verified working) |
| RA before (retrieval only) | – | 22.4 s | 5 | 40,827 | 0 | 0 | 15,085 | $0.233 |
| RA after (whole doc, cached) | before warm-first fix | 13.9 s | 23 | 365,323 | 93,142 | 212,896 | 15,801 | $0.827 |
| AC before | – | 27.8 s | 8 | 31,823 | 0 | 4,657 | 20,688 | $0.273 |
| AC after | before warm-first fix | 28.0 s | 8 | 58,647 | 4,657 | 34,356 | 23,153 | $0.358 |
| SC before | – | 24.5 s | 6 | 24,287 | 0 | 4,666 | 14,500 | $0.196 |
| SC after | warm-first | 44.4 s | 6 | 43,492 | 24,334 | 4,917 | 15,870 | $0.204 |
| p284 adaptive (ABORTED by the spending guard) | retrieval + index fill + second look | ~3 min | 140 | 557,355 | n/a | n/a | 401,940 | ≈ $5.13 |

Account check: OpenRouter `/api/v1/key` reports `usage_daily` = $23.15 for 2026-10-28 (UTC). That figure covers every call today on this key, including the RA re-analysis.

Quality on the gold fixtures (builder-authored gold, NOT SME reviewed; `scripts/perf/score_ra.py`, `GOLD=` per fixture):

| fixture | precision before → after | recall before → after | exact before → after | gold gaps flagged | false gaps on met | citation validity |
|---|---|---|---|---|---|---|
| RA | 0.987 → 0.987 | 1.000 → 1.000 | 0.724 → 0.744 | 4/4 | 0 | 1.0 |
| AC | 0.890 → 0.890 | 1.000 → 1.000 | 0.706 → 0.737 | 24/24 | 0 | 1.0 |
| SC | 0.887 → 0.887 | 1.000 → 1.000 | 0.801 → 0.808 | 18/18 | 0 | 1.0 |

Coverage guard: after = 25/25, 17/17 and 17/17 chunks available to at least one check. Before (retrieval only), RA = 19/25.

What these runs taught us:
- With a 16-way parallel first wave, every call writes the cache: RA after shows 212,896 write tokens. The fix runs the first batch alone, then the rest in parallel. This is in code and was used for SC after.
- In whole-document mode, batches are now sized by requirement count only, so there are fewer calls.
- Sending the whole document in every batch is only cheap for small policies. The design is now adaptive:
  - ≤ 60k characters: whole document per batch.
  - Larger documents: retrieved sections per batch, plus the hybrid index filling anything keyword screening missed (nothing is excluded), plus the cached whole document only for the focused second look on MISSING verdicts.
