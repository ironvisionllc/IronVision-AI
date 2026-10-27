# Policy Auditor – performance re-architecture (analyzer v2)

Preview only, not deployed. Benchmarks use real OpenRouter calls to `anthropic/claude-sonnet-5.5`, the current configuration.
Numbers: `policy_auditor_results.md`, `policy_auditor_baseline.json` and `policy_auditor_benchmarks.json`. Raw runs: `docs/perf/runs/`.

## Versions (side by side)
`POLICY_ANALYZER=v-current|v2` selects the analyzer; the default is `v2` (commit 6d00cb4, after the benchmarks); `v-current` stays selectable for comparison. Each analysis records its analyzer in `policy.analysis.analyzer`, and v2 records its stats in `policy.analysis.v2`.

* **v-current:** one AI call per ≤8 requirements of one control. Every call sends the whole policy, truncated to its first 24,000 characters. Prompt: `policy.coverage_refine` 1.0.0.
  * Consequence found by the baseline: requirements whose policy text sits after character 24,000 are never really seen by the AI. This is why its citation validity is low on long policies.
* **v2:** prompt `policy.coverage_refine` 2.0.0 (strict JSON; multiple controls per call; every item carries control ID, requirement/CCI/objective ID, status, verbatim quote, section label and rationale).

## Pipeline v2
1. **Extract / normalize once (A).** DOCX paragraphs *and tables* are read in document order (text-3; one line per table row). `sections()` splits on headings (Markdown, numbered headings and short `AC-2(1) Title` lines). Table rows and prose starting with an ID ("RA-10 is outside …") are not headings: as one-row sections they outranked the real section in retrieval (found on the RA UAT policy). Headless text is windowed at paragraph boundaries. Each section keeps its heading, page (from `--- Page N ---` / form-feed markers), start/end offsets and a content hash.
2. **Deterministic stage.** This is the existing evaluator, unchanged in behaviour. It is now about 10x faster through a per-document regex match index, and the results are byte-identical (verified on 171 requirements). It is memoised per analysis, so the worker's prefetch and `analyze()` no longer compute it twice. On the 284-control policy this stage took 140 s, and it used to run twice.
3. **Relevance screening (B).** BM25 over the sections, using the requirement text plus the control title, plus a strong boost for sections that name the control ID (heading +25, body +8).
   * Up to `POLICY_AI_TOPK` (default 3) sections with a score ≥ `POLICY_AI_MIN_SCORE` (default 4) are examined.
   * Requirements with no retrieved section are labelled *"Not examined by AI: no policy section was retrieved … (not a pass, fail or N/A)"*. Their deterministic status is kept and never upgraded.
   * A deterministic sample (`POLICY_AI_VERIFY_FRACTION`, default 10%) of not-examined requirements still gets an AI pass with the 2 best sections, to measure screening false negatives (`verification_found`).
   * **Embeddings: not used.** No local embedding model is installed, and adding torch/sentence-transformers is a large dependency. OpenRouter's Anthropic route has no embeddings endpoint, and sending customer text to a second provider for embeddings would widen data exposure. Lexical BM25 plus explicit IDs costs $0, runs locally, and keeps the text inside the tenant's analysis process. The benchmark recall below shows whether that is enough; if it isn't, a local ONNX MiniLM model is the next step.
4. **Batched AI (C).** Requirements are grouped by (family, primary section) and packed up to 25 per call (`POLICY_AI_BATCH_REQS`), with the union of their retrieved sections ≤ `POLICY_AI_BATCH_CHARS` (16,000). Only near-best sections (≥ 0.6 × top score) are kept. The output budget is `160 × requirements + 400` tokens.
5. **Validation (D).**
   * Items for IDs that were not requested are dropped and counted (`invalid_items`).
   * Each requirement is accepted once; missing answers are re-asked once (`reasked`).
   * Truncated replies are split in half and retried (`truncated`).
   * Quotes are located in the actual section, and section, page and offset are attached; if the model cited the wrong section, it is corrected and counted (`citation_section_fixed`).
   * Stage 3 is unchanged and still enforces verbatim quote verification against the policy text: nothing is MET without a verified quote, and the deterministic fallback stays readable.
6. **Concurrency.**
   * `POLICY_AI_WORKERS` (default 16, chosen from the sweep) threads, with RPM/TPM token buckets (`POLICY_AI_RPM` 300, `POLICY_AI_TPM` 2,000,000).
   * `policy.audit` 1.1.0 runs with `reasoning_effort=low` (hidden reasoning had consumed the whole token budget), and its result is cached per tenant (text + model + prompt version).
   * Exponential backoff with jitter (up to 4 attempts) on 429, timeout and 5xx; the per-request timeout is the provider adapter's.
   * The `policy.audit` AI call now runs concurrently with the coverage AI.
   * Batches are idempotent by cache key.
   * OpenRouter rate-limit headers are not exposed by the current adapter; the buckets are configured instead.
7. **No transaction across AI.** The worker ends its read-only transaction before any AI call. AI threads touch the DB only through their own short sessions (cache get/put, progress). Bulk approvals keep their dedicated worker lane.
8. **Cache (tenant-scoped).** Table `policy_ai_cache` (migration 0035, additive; downgrade drops it). It has a unique key `(org_id, cache_key)`.
   * `cache_key` = sha256 of: org ID, analyzer version, prompt version, model, catalog revision, the batch's (control, requirement, requirement text, deterministic result) tuples, and the hashes of the sections sent.
   * The policy version is deliberately *not* in the key: an edited policy version reuses the batches whose sections did not change (incremental reanalysis); the provenance records the policy and sections the result came from.
   * There is no cross-tenant hit (org ID is in the key and in every lookup) and no global cache. Tests prove that an identical document in tenant B gets no tenant-A hit.
   * The CCI-mapping revision is covered by the requirement text in the key. There is no system-context input to policy analysis.
   * Human approvals and mappings are untouched: reanalysis only recomputes coverage and proposals, as before.
9. **Progress (UX).** `policy.analysis.progress` is updated every 3 batches: % complete, controls screened, requirements analyzed, validated findings so far ("analysis in progress"), elapsed time, ETA, failed batches and retries. The Policy Auditor page polls it every 3 s while an analysis is running. The job keeps running in the background when the user navigates away.
