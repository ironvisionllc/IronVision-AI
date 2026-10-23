# CCI-level Policy Auditor + policy/CCI filters

Preview: https://aegis-rmf-demo.preview.emergentagent.com. Browser check account: `jordan.qa7731@example.com` (existing, no new sign-up). Screenshots: `docs/screenshots/sme-cci/`. The Droplet was not touched.

## What's built
1. **Requirement model.** Each control a policy maps to (approved, or proposed with High/Medium confidence) gets its requirements from the loaded reference data:
   - the **DISA CCIs** (`cci_control_maps`, Rev 5, with the definition text from the 5,137-CCI list; RA-1 has 21);
   - the **SP 800-53A objectives** with prose (3,715 loaded; RA-1 has 17, e.g. `RA-01a.[01]`, `RA-01c.02[01]`).

   Results are stored per policy × control × requirement in `policy_requirement_coverage` (migration 0018).
2. **Coverage analysis** (`services/policy_coverage.py`): deterministic.
   - Each requirement's wording is classified into a concept:
     - the 7 policy elements: purpose, scope, roles, responsibilities, management commitment, coordination, compliance;
     - consistency with laws/directives;
     - dissemination;
     - the personnel or roles it is disseminated to;
     - the designated official;
     - review frequency;
     - review-triggering events;
     - procedures developed/documented;
     - each split between policy and procedures.
   - The policy text is then searched sentence by sentence. Each requirement gets **MET / PARTIAL / MISSING**, the matched snippet(s) with **page/section** (the existing `locate()`), a confidence, the reason and, when not met, **"Would satisfy it: …"** example text.
   - **Organization-defined values** are extracted next to the parameter (e.g. `review frequency (policy)` = "at least annually"; recipients = "all system owners, ISSOs and the ISSM"; designated official = "ISSM"). They feed the system-wide **parameter comparison CSV** (`policy_requirement_parameter` rows next to the ODP value).
   - Coverage is recomputed whenever the policy is analysed or a mapping is approved or rejected. "Covered elsewhere" overrides and approval links are kept across recomputes.
3. **Status suggestion** (Mapping Review kind `policy_status`, for `XX-1` Policy and Procedures controls):
   - All requirements MET gives "Implementation → Implemented", listing the coverage. Some met plus gaps gives "Partially Implemented", naming the gaps (e.g. "RA-1: 30 of 38 requirements met … – missing: review frequency for the policy; review frequency for the procedures").
   - **Never auto-applied.** Approval needs `implementation.write` and is checked before any write, so SoD and the deadlock fix stay in force.
   - Reject needs a justification (≥10 characters) and is remembered per coverage fingerprint, so the item returns only if the coverage changes.
   - Approval:
     - sets the implementation status;
     - links the policy as evidence: each MET requirement gets `linked` = {assignment, system, by, at}, and the policy's evidence file gets an `EvidenceControl` link;
     - approves the proposed policy→control mapping;
     - writes `control.policy_coverage_status_approved` (before/after, linked CCIs, coverage, justification) plus the per-item `mapping_review.item_approved`.
   - Assessment still needs the SCA. The message and next step are the same as for STIG status suggestions.
4. **UI:**
   - **Policy detail:** a **Requirement coverage** panel with a per-control expandable CCI/objective checklist (badge, ID with a CCI tooltip, requirement text, extracted value, snippet with location, "would satisfy it", linked-by). It also has **Show only mapped (approved) controls**, **View these N controls in the Workbench →** (opens `/systems/{id}/controls?policy=<id>`) and **View the CCIs →**.
   - **Workbench control detail:** policy coverage line per policy plus "Show coverage per CCI".
   - **Mapping Review:** "Policy coverage" tab, with an item line "38 of 38 requirements met – missing: …".
   - **Traceability:** new **Policy → CCIs** column (policy titles with mapped/proposed and "21/21 CCIs met", linking to the CCI view), a **Policy-mapped only** checkbox, a per-policy select and CSV export.
   - The CCI tooltip explains CCIs vs 800-53A objectives in plain words.
5. **Gaps → action** (on every PARTIAL/MISSING row):
   - **Add to POA&M** creates a POA&M prefilled with the policy, CCI, control, reason and needed text (`poam.manage`), and gives a next step to add milestones.
   - **Mark as covered elsewhere** needs a reason (≥10 characters), takes optional linked evidence, counts as met and is audited.

## Filters (addition)
- **Workbench** (URL-driven, combinable with the existing filters):
  - **Policy mapping**: Mapped to a policy / Not mapped / Proposed (awaiting review);
  - **Policy coverage**: All requirements met / Partially met / Gaps (any MISSING);
  - **Policy**: tick one or more policies.

  Each option shows its count. Counts and lists come from one helper (`policy_coverage.index` + `matches`), so the count always equals the list length. **Export controls (CSV)** uses the active filters.
- **CCI view** (sidebar 4 · Implement → **CCI view**, `/ccis`):
  - filters: mapped / not mapped, coverage MET/PARTIAL/MISSING, policy, control, family and text, all in the URL;
  - each row: CCI ID, definition, parent control (link), implementation status, coverage, mapped policy link and snippet with location;
  - counts line; page size; **Export CSV (current filters)**.
- **Traceability:** mapped-only / per-policy filter, as above. Its CSV respects the filters.

## Click path
1. Sidebar **4 · Implement → Policy Auditor** → upload a policy (link it to the system) → open it → **Requirement coverage** → click **RA-1** for the CCI checklist.
2. **View these N controls in the Workbench →** opens the Workbench pre-filtered by the policy. Then try **Policy mapping / Policy coverage**.
3. Sidebar **5 · Assess → Mapping Review** → **Policy coverage** tab → **Approve**, then the SCA confirms under **Awaiting assessor (SCA)**.
4. Sidebar **4 · Implement → CCI view**, and **Tools → Traceability matrix** → **Policy-mapped only**.

## Files
- **New:**
  - `backend/app/services/policy_coverage.py`
  - `backend/alembic/versions/0018_policy_requirement_coverage.py`
  - `backend/tests/test_policy_coverage.py`
  - `frontend/src/components/policy/Coverage.tsx`
  - `frontend/src/pages/CciPage.tsx`
- **Changed (backend):**
  - `models.py`
  - `services/rmf.py` (analysis hook)
  - `services/policy_mapping.py` (recompute on decision)
  - `api/v1/phase4.py` (queue + decide branch)
  - `api/v1/phase3.py` (policy detail coverage, gap actions, export rows)
  - `api/v1/workbench.py` (filters, facets, CSV, CCI endpoint, control coverage)
  - `api/v1/rmf_steps.py` (traceability filter/CSV)
- **Changed (frontend):**
  - `pages/Phase3Pages.tsx`
  - `pages/WorkbenchPage.tsx`
  - `pages/RmfStepPages.tsx`
  - `components/evidence/ReviewQueue.tsx`
  - `App.tsx`
  - `lib/nav.ts`

## Tests (`tests/test_policy_coverage.py`, 8 tests, isolated fresh sign-up with two systems)
- **Complete synthetic RA policy:**
  - CCI IDs equal the reference list (21);
  - objectives are present;
  - **every requirement is MET**;
  - values are extracted ("at least annually", recipients), and the location is "p. 1";
  - an **Implemented** suggestion is created, and the status is **unchanged until approval** (no auto-apply).
- **Missing review frequency:**
  - both frequency CCIs are not met and carry "annually" fix text;
  - a **Partially Implemented** suggestion names "review frequency for the policy / procedures";
  - **reject without a justification returns 422**; with one, the suggestion disappears and the status is unchanged.
- **Unrelated policy:** no RA coverage and no RA suggestions.
- **Approval:**
  - the status becomes Implemented;
  - every requirement is linked (system/by/at);
  - the audit events `control.policy_coverage_status_approved` and `mapping_review.item_approved` are written;
  - the item leaves the queue;
  - the **Mapped filter includes RA-1 immediately**;
  - the Workbench control detail shows coverage.
- **Filters:**
  - for every Policy mapping / Policy coverage value, the list length equals the facet count;
  - the policy filter count equals the list;
  - combined filters work;
  - CCI view: `control=ra-1&mapped=yes` returns 21, all met, with definitions; not-mapped returns only unmapped rows; the CSV has 22 lines;
  - traceability per policy shows 21/21.
- **Gap actions:** covered-elsewhere (reason too short gives 422; otherwise it counts as met); Add to POA&M creates a POA&M citing CCI-001040 and RA-1.
- **Tenant isolation:** a different-org account gets 403/404 on the policy, the coverage action, the CCI view and the facets.
- **Full backend suite: 473 passed, 43 skipped.** Jest: 6/6.
- **Browser** (`/root/shots_cci.py`, jordan.qa7731), no page errors:
  - RA-1 38/38 checklist (38 rows) and the Mapping Review coverage item.
  - Approve showed "Implementation set to Implemented. Assessment status needs SCA confirmation" plus the SCA next step.
  - "View these 1 controls in the Workbench" opened `?policy=<id>`.
  - Filter options showed counts (Mapped 1 / Not mapped 283 / Proposed 2 = 286), and the URL survived a reload.
  - The control detail coverage showed.
  - CCI view: 21 CCIs, 21 met; the CSV downloaded (22 lines).
  - Traceability per policy: "21/21 CCIs met".

## Limitations
- **Heuristic accuracy:**
  - The deterministic engine is keyword/sentence based. It is reliable for the -1 Policy and Procedures controls, whose CCIs follow a fixed pattern (validated on the synthetic RA policies).
  - It can be fooled by unusual phrasing, e.g. a review frequency written as "each fiscal year" or recipients given as a table.
  - For other controls a generic word-overlap check is used, which gives Low-confidence PARTIAL at best. **Status suggestions are therefore only generated for `XX-1` controls.**
- **AI vs deterministic:** **AI refinement is not wired into the coverage step yet.** Coverage is deterministic-only (`source = "deterministic"` on every row), even though the AI provider is configured and still used for policy→control mapping.
- **Worker restart:** the background worker does not hot-reload, so it was restarted to pick up the analysis hook. Policies analysed before this change get coverage on their next analysis or mapping decision.
- Only the first linked system of a policy is used for the "Add to POA&M" and "View in Workbench" links on the policy page.
