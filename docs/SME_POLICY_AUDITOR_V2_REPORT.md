# Policy Auditor v2 – fixes A1–A6, non-XX-1 coverage (B), automatic processing & propagation

Synthetic demo data only. Nothing is applied automatically: every status change still goes through Mapping Review (RBAC/SoD, justification, audit event).

## A. Root causes and fixes

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| A1 | A mapped policy with gaps produced no Mapping Review item | `policy_coverage.suggestions()` skipped a `partially_implemented` target whenever the control was already `implemented` (dedupe). The mapping-approval path *did* recompute coverage, and the worker was not the cause. | A policy gap now always produces an item. When the control is Implemented it is a **downgrade suggestion**: “RA-1 is Implemented but the latest policy version (v3) is missing … – suggest Partially Implemented”. Verified on jordan.qa7731 (RA v3). |
| A1-AO | AO could not see that approval was blocked | The UI hid the Approve button when the role lacked `finding.map` | AO sees every item. Approve and the checkbox are **disabled** with “Approving needs the ISSO or ISSM role – your current role can view this item but not approve it.” The backend still returns 403 (tested). |
| A3 | `policy=v3` borrowed MET results from other policies; `coverage=missing&policy=v3` returned 0 | The CCI view and Workbench used one combined row set per control, then filtered on policy ids | New `scoped(entry, policies)`: with a policy filter, only that policy's rows count. Without one, the best result per requirement is used and each CCI shows **“Matched by <policy vN>”**. `mapped=true/false/1/0` now works the same as `yes/no`. Workbench and CCI view use the same function. |
| A4 | A Scope snippet was labelled “§1 Purpose” | `locate()` only searched the lines *before* the snippet's offset, so a sentence on its own heading line (“2. Scope. …”) got the previous heading | The snippet's own line is now included and the label is trimmed to the heading (“§ 2. Scope”). |
| A5 | Policy-level `values` was empty | `analyze_policy()` overwrote `policy.analysis` after coverage had run | Coverage now runs after that point and merges every requirement-level value (frequency, designated official, recipients, ODP values) into `analysis.values`. The parameter comparison and CSV read the same list. |
| A6 | Old and new versions were combined | Versions that share a title were superseded correctly; nothing told the user which version was current | Policy detail returns `is_current` and `superseded_by`, and shows a banner on old versions. Coverage, filters and suggestions use current versions only. Suggestion titles name the version (vN). Tested: uploading v2 leaves v1 with no coverage in the CCI view. |

## B. Non-XX-1 controls (all families)

* **Requirement profiles** (`services/policy_profile.py`). Each 800-53A objective or CCI is reduced to:
  * the concepts it names (a lexicon of about 45 concepts, e.g. *logon attempts*, *audit records*, *baseline configuration*, *backup*, *authenticator*);
  * the organization-defined values it needs (`[Assignment: frequency | time period | number | authorities]`; for a Selection, the first option).
* **Matching order:**
  1. Explicit control ID near the matching sentence → High confidence.
  2. All concepts and values in one sentence (or two adjacent sentences) → MET.
  3. At least half present → PARTIAL; otherwise MISSING.
  4. Optional **AI refinement** (`policy.coverage_refine` prompt, strict JSON) through the existing AI provider, worker only. An AI MET counts only if its quote is an exact substring of the policy; otherwise it is discarded and the reason says so. If the AI disagrees with a deterministic MET, the result drops to PARTIAL with Low confidence (review needed).
* **Policy vs implementation:**
  * Each requirement is labelled *policy* (define/document/review/report) or *technical* (enforce/employ/retain/protect/monitor/configure…).
  * For non-XX-1 controls, policy coverage alone is at most **Partially Implemented**, and the suggestion lists the requirements that still need technical evidence.
  * **Implemented** is suggested only when the policy covers every requirement **and** current, passing technical evidence (not the policy file) is linked with no open findings.
  * A downgrade happens only for a real policy gap, never just because scan evidence is missing.
* **Confidence:** each requirement shows High/Medium/Low plus how it was matched (explicit ID, concept match, AI-verified quote, policy-element rule). A control with any Low, non-missing requirement gets **no status suggestion**. It is listed under “Review needed” in Mapping Review instead. In jordan's tenant this applies to IA-5: 5 low-confidence CCIs.
* A “Policy vs implementation ⓘ” explanation is shown in the coverage checklist, and each technical requirement is tagged “needs technical evidence”.

### Accuracy (synthetic, hand-labelled set: `tests/policy_eval_set.py`)
Six policies (AC, AU, CM, IR, CP, IA) with deliberate gaps across AC-7, AC-11, AU-6, AU-11, CM-2, IR-6, CP-9 and IA-5: 33 objectives, 16 labelled MET.

| Method | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|
| Deterministic, first run | 16 | 1 | 0 | 0.94 | 1.00 |
| Deterministic, after adding the *membership / group-role accounts* concepts (fixes the IA-5.i false MET) | 16 | 0 | 0 | **1.00** | **1.00** |
| Deterministic + AI (configured provider, first lexicon) | 14 | 0 | 2 | 1.00 | 0.875 (AI downgraded 2 true METs; 0 quotes discarded) |

Thresholds enforced in tests: precision ≥ 0.90, recall ≥ 0.60.

**Caveat:** the lexicon was tuned on this same set, so these are not held-out numbers. AC-2 and IR-4 are not labelled yet (AC-2 has many objectives). CCIs are evaluated by the same engine but are not part of the labelled metrics.

## C. Automatic processing pipeline (per upload type)

| Upload | Synchronous (request) | Worker job | Automatic result | Needs a human |
|---|---|---|---|---|
| .ckl / .cklb (STIG) | SHA-256, format detected from content, original stored, Evidence row, IngestRun `queued` (identical file → `duplicate`, not double-counted) | `ingest.process`: parse → findings (dedupe) → CCI→control mappings → EvidenceControl links → `evaluate_system` (freshness, open findings, priorities) → POA&M closure eligibility → risk snapshot | Workbench, CCI view, traceability, ledger, dashboards, stepper | Unmapped/automated mappings in Mapping Review, status suggestions, POA&M creation, SCA assessment |
| XCCDF / ARF (SCAP) | same | same parser family (XCCDF tested; no ARF sample is shipped – not tested) | same | same |
| .nessus / Nessus CSV (ACAS) | same | same (plugin → control mapping) | same | same |
| Policy .docx / .pdf / .txt | Text extracted, version number set (same title → previous version superseded), Evidence row | `policy.analyze`: mapping extraction → proposed policy→control mappings → rule findings (+ optional AI audit) → CCI/objective coverage (+ optional AI refinement) → top-level values | Policy detail, coverage, CCI view, Workbench policy filters | Mapping approval, status suggestions (Mapping Review), covered-elsewhere/POA&M gap actions |

* **Processing state:** `GET /systems/{sid}/processing` reports *Processing… / Analysed / Failed (reason)* for recent uploads and policies, with a summary. Example: “7 rules/results parsed, 3 open findings, 6 mapped to controls, 1 unmapped sent to Mapping Review, 6 controls updated”.
  * The Evidence Sources upload panel lists recent uploads with these badges.
  * Failed items show the reason and a **Retry** button (`POST /ingest-runs/{id}/retry`, `POST /policies/{id}/reanalyze`).
  * A policy job that raises is now marked `failed` with the error. It no longer stays `queued` silently.
* **Notifications:** a global watcher polls every 3 s while anything is processing (every 60 s otherwise). When an item finishes it shows a toast with the summary and a Next-step link (or an error toast with the reason).
* **Propagation:** every `useApi` screen quietly refetches after any successful write (approval, upload, status change) and after any job finishes. This covers the stepper, dashboard, Workbench, CCI view, traceability, ledger, Mapping Review counts, POA&M, portfolio and step progress. Counts still come from `services/counts.system_counts`. Browser tour: 11 screens with **0 full page loads**.
* **Worker robustness:**
  * Coverage stores `analysis.coverage_version`. On startup the worker re-runs every policy analysed by an older version (`ANALYZER_VERSION = coverage-2`). This restart re-analysed 8.
  * Re-analysis replaces coverage rows and keeps “covered elsewhere” overrides.
  * Ingest retries are idempotent: `process_run` only runs `queued`/`failed` runs, and findings are deduplicated.

## Tests
* `tests/test_policy_auditor_v2.py` (12) covers:
  * A1 downgrade on an Implemented control;
  * AO can view but gets 403 on approve;
  * A3 per-policy CCI and Workbench filters, plus `matched_by`;
  * A4 section labels; A5 top-level values; A6 supersession;
  * non-XX-1 controls never suggested Implemented on policy alone;
  * Low confidence gives review-only; AI quote must be an exact substring;
  * tenant isolation with a second test org;
  * precision/recall thresholds; stale `analyzer_version` reprocessing.
* `tests/test_processing_pipeline.py` (7) covers:
  * .ckl, .cklb, XCCDF, .nessus and Nessus CSV: processing → analysed with a summary; all screen APIs return data; Workbench filter count = dashboard count; portfolio open findings = system dashboard; queue counts are consistent; approving a mapping lowers the Mapping Review count and screens stay consistent;
  * policy .docx and .txt;
  * a broken .ckl fails with a visible reason, and Retry works idempotently.
* Full backend suite (`pytest tests`): **492 passed, 43 skipped**. Frontend (`craco test`): **6/6**. `tsc --noEmit` clean.

## Browser check (jordan.qa7731, no new sign-ups)
1. Evidence Sources → upload `qa-web.ckl` → the badge shows Processing…, then the toast “qa-web.ckl analysed: 7 rules/results parsed, 3 open findings, 6 mapped …”.
2. Upload `IA Standard QA.docx` → toast “1 control mappings (1 sent to Mapping Review), 8 of 27 CCI/objective requirements met” plus a Next step.
3. Client-side navigation, no reload: Dashboard → Workbench → CCI view → Traceability → Evidence Ledger → Mapping Review → POA&M → Portfolio → Implement/Assess/Monitor. 0 page loads, no page errors.
4. Mapping Review → Policy coverage shows “RA-1 is Implemented but the latest policy version (v3) is missing … – suggest Partially Implemented”, and “Review needed (1): IA-5”.
5. Switch to AO → Approve is disabled with the role message → switch back to ISSO.
6. Bug found and fixed during the tour: the “This needs a different role” dialog stayed open after navigating away. It now closes on route change.

Screenshots: `docs/screenshots/sme-auditor2/`.

## Limitations
* The concept lexicon is hand-built. Objectives that name no lexicon concept fall back to keyword similarity with Low confidence, so they never create suggestions.
* AI refinement runs in the worker only, not during pytest. It sends one call per non-XX-1 control (cost grows with the number of mapped controls).
* “Technical evidence” means current, non-policy evidence linked to the control with no open findings. Scan coverage of the specific objective is not checked.
* ARF has no sample file and was not tested end-to-end.
* Ingest runs carry no analyzer version (their parsing is deterministic and idempotent); only policies are re-analysed automatically.
* The DigitalOcean Droplet was not touched; recovery remains paused.

---

# Fix round 2 (independent test of 48456d3)

| # | Finding | Root cause | Fix |
|---|---|---|---|
| 1 | Flip-flop: approving the RA-1 downgrade created "RA-1: 38 of 38 → Implemented" (count 16 → 17) | **Two separate causes.** (a) Jordan's tenant has two *different* current policies mapped to RA-1: “RA” v3 (26/38, gaps) and “Risk Assessment Policy (synthetic)” v1 (38/38). Their titles differ, so neither supersedes the other. Suggestions were computed **per policy**: while RA-1 was Implemented only the gap policy disagreed; after the downgrade the complete policy disagreed. (b) Approving links the policy file as evidence, and the evidence-based `status_suggestions()` counted that policy document as "passing evidence" and offered Implemented + Satisfied. Superseded versions were *not* involved (only current versions contribute). | **One decision per control** across all current policy versions mapped to it, the most conservative wins (`control_decision`). The reasoning lists each policy's result. Coverage is read from policy text only: `effective()` = text status, "covered elsewhere" and "linked as evidence" are shown separately and never turn MISSING into MET. Policy documents no longer count as technical evidence in evidence-based suggestions. Dismissals are keyed per control. |
| 1-cleanup | Bogus RA-1 suggestion in jordan's tenant | – | Analyzer bumped to `coverage-4`; the worker re-analysed 11 policies on restart (recompute, no manual deletes). RA-1 now has no item, and the note reads “RA-1 is already Partially Implemented – this matches the current policy coverage.” |
| 2 | AC-7 “7 attempts” from the heading; “30 days” on the AC-2 approval sentence; window/lockout missing | The rule regex matched “**7** Unsuccessful Logon Attempts” inside “AC-7 …”. The coverage value was read from a 2-sentence window, so a neighbouring sentence's “30 days” was attached. | `mask()` blanks control IDs and section numbering (same length, offsets kept) before any value extraction. Each value is bound to the one sentence that states it. New ODPs: `logon_attempt_window_minutes` (ac-07_odp.02) and `lockout_minutes`, next to attempts and AC-2(3) inactivity days. Jordan's new AC upload extracted 5 attempts / 10 min / 20 min / 45 days. |
| 3 | No AC-2/AC-7 status suggestion; `tech_needed` empty | Most AC-2 objectives named only one lexicon concept, so they fell back to keyword matching and produced **Low-confidence** rows. AC-7 also had one Low CCI. The rule “any Low row blocks the suggestion” then suppressed both. | Low rows never count as MET but no longer block the confident ones; they are listed as "review needed" inside the reasoning. New account-management concepts: account, assign, approval, create, disable, notify, authorize, prohibit, in accordance with, monitor, termination, transfer, aligned. AC-7 now shows “… → Partially Implemented – technical evidence needed for: CCI-000044, CCI-002236, …”. When there is no item, Mapping Review explains why, e.g. “Status suggestion for RA-3 will appear after you approve the RA-3 mapping …”, “already Partially Implemented”, “stays Implemented: … technical evidence still needed”. |
| 4 | Second AC upload (9913) added no Mapping Review items | **Not deduplication.** Its extracted text is a single placeholder line (“Policy Content for QA AC Policy 9913”) that names no control. | The processing summary now says “No controls found: the extracted text (N characters) names no NIST control …”. Two *different* policies on the same control each get their own mapping items (tested). An **identical** re-upload (same title and SHA-256) is deduplicated with “Identical to “X” v1 (same SHA-256) – not re-analysed and no new review items were created.” |
| 5 | Only “analysed” was ever visible | The worker set `processing` in the same transaction as completion, and the list showed upload runs before policies | States are now **Queued – waiting for the worker → Processing… → Analysed / Failed (reason)**. The worker commits `processing` when a job starts, and items are sorted by time. Browser: the badge read “Queued – waiting for the worker | AC Standard 98bc v1” immediately after upload, then the toast followed. |

**Evaluation set** now has 7 policies (an AC-2/AC-7 account-management policy was added) and 39 labelled objectives, plus expected values:

| Run | TP | FP | FN | Precision | Recall |
|---|---|---|---|---|---|
| Deterministic, first run | 21 | 2 | 0 | 0.91 | 1.00 |
| Deterministic, after adding termination/transfer/aligned (fixes AC-2 l-1/l-2) | 21 | 0 | 0 | **1.00** | **1.00** |

The precision/recall threshold applied to status suggestions is the same one the eval uses: MET counts only at High/Medium confidence. Values are asserted for AC-7 attempts=3, window=15, lockout=30 and AC-2(3) days=30.

**New tests** (`tests/test_policy_auditor_v2.py`):
* `test_stability_downgrade_then_upgrade_then_complete_v4`
  * Implemented + gap policy → downgrade → approve → re-analyse → no policy_status item, and open count −1.
  * Linked rows stay non-MET.
  * Complete v2 of the gap policy → a legitimate Implemented item → approve → re-analyse → no item.
* `test_ac2_ac7_policy_gives_partial_with_technical_evidence_needed`
* `test_values_never_from_ids_and_bound_to_their_sentence`
* `test_two_different_policies_each_get_mapping_items_and_identical_reupload_is_deduplicated`
* Updated: one item per control (A1), Low-confidence semantics, covered elsewhere ≠ MET, Queued state in the pipeline tests.
* **Full suite: 496 passed, 43 skipped.** Frontend 6/6, `tsc` clean.

**Browser recheck (jordan.qa7731)**
* Mapping Review → Policy coverage: no RA-1 item, and the "why" note is shown.
* Upload an AC policy: Queued badge → toast “2 control mappings (2 sent to Mapping Review), 11 of 69 …”. Its two mapping items appear.
* Approve the AC-7 “Partially Implemented – technical evidence needed” item: open count 20 → 18 (the status item plus the AC-7 mapping it approves), and **no new AC-7 item**. No page errors.
* Screenshots: `docs/screenshots/sme-auditor3/`.

**Limitation:** the most-conservative rule means one incomplete current policy keeps a control at Partially Implemented even if another current policy covers it. Users resolve this by superseding or retiring the incomplete policy; the reasoning names both policies.
