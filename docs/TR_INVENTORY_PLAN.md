# eMASS Test Results (TR), HW/SW Inventory and STIG→Asset: plan

Order (per user): 1. TR import/mapping/generation/SCA review/export (done, validated) → 2. AI evidence analysis for TR → 3. HW/SW inventory + STIG→asset (with AI-assisted consistency/correlation).

Labels: **Implemented** = in code and tested · **Mockup** = UI only · **Future** = not built.

## 1. TR (Phases 1–2), implemented

| Piece | Reused | New |
|---|---|---|
| Upload/storage | object storage (`services/storage`), SHA-256 + versioning pattern from ingest | `tr_workbooks` (0019) |
| Detection/mapping | CCI→control map, control catalog, Mapping Review semantics (matched/ambiguous/unmatched + reason) | `services/tr/xlsx.py` header-role detection, Assignment Values vocabulary |
| Generation | assessments, STIG/ACAS findings + finding→control maps, policy CCI coverage, evidence (freshness), POA&Ms, worker jobs | `tr.generate` job, `tr_rows` |
| Review/approval | RBAC `assessment.perform` (SCA) enforced in the API; audit events | review screen `/test-results` |
| Export | none (a byte-level copy of the original workbook) | bounded cell writer + XML/cell diff validation report, `tr_exports` |

Data mapping: AP Acronym/CCI/definitions = "Provided by eMASS" (never written). Written only: `Template!M:P` (Compliance Status, Date Tested, Tested By, Test Results) for approved rows, plus `A,F,G,H` identifiers for rows the user explicitly adds from the system. Compliance Status only from an assessment record or the SCA in review; Tested By/Date Tested only from that assessment/SCA.

## 2. AI evidence analysis for TR: reuse vs new

**Reuse**
- AI provider abstraction `services/ai` (OpenRouter / Anthropic / Emergent, strict JSON schema with pydantic output model, one repair retry, usage logging in `ai_interactions`), via `get_ai_service().run(prompt_id, version, …)`.
- Deterministic fallback pattern (as in `policy_coverage.ai_refine`): no provider, or any AI failure, means the deterministic result stands.
- TR row sources (assessment, STIG, ACAS, policy coverage, evidence with freshness, POA&M) already gathered by `tr.generate`; the current implementation statement (`implementations`); the conflict/stale/missing logic.
- Worker job queue (`jobs.enqueue` + `worker/handlers.py`), audit (`audit.record`), RBAC (`assessment.perform`, `implementation.write`), TR export/validation (unchanged).

**New**
- Prompt `tr.evidence_analysis@1.0.0` with output schema `EvidenceAnalysisOutput` (`extra="forbid"`: no status/tester/date fields can exist).
- `services/tr/analysis.py`: bundle builder, deterministic analysis, server-side reference/quote validation (drops recorded), run/store.
- Table `tr_analyses` (migration 0020): mode, provider, model, prompt version, input record IDs, input bundle, output, drops, error, requester.
- Job `tr.analyze` (one row or bulk); endpoints `POST …/analyze`, `GET …/rows/{rid}/analysis`, `POST …/rows/{rid}/use-analysis` (text only, `extra="forbid"`).
- Review-screen panel with the badges "AI suggestion" / "Deterministic analysis (no AI)", "Recorded assessment" and "Approved SCA decision", plus a "Use this text" button. Applied text is editable, audited (`tr.ai_text_applied`) and attributed as AI-assisted; an approved row returns to *edited* and needs SCA re-approval before it is exported.

## 3. HW/SW inventory + STIG→asset (with AI-assisted consistency/correlation): reuse vs new

Template facts (`HWSWList_Template-eMASS3.xlsm`): sheets `Hardware` (header row 7: # · Component Type · Machine Name (Required) · Nickname · IP Address · Virtual Asset? · Manufacturer · Model Number · Serial Number · OS/iOS/FW Version · Memory Size / Type · Location · Approval Status · Critical Information System Asset?), `Software` (# · Software Type · Software Vendor (Required) · Software Name (Required) · Version (Required) · Subsystem · License or Contract · Total Licenses · Licenses Used · License POC · License Expiration Date · Approval Status · Approval Date · Critical… · Purpose), `Instructions`, hidden `(U) Lists` (tables `Tab_HWType`, `Tab_SWType`, `Tab_Approval`; names `HWType`, `SWType`, `Approval`, `Yes_or_No`). Signed VBA project (`xl/vbaProject.bin` + 3 signature parts). Macros are never executed. Export copies the package byte-for-byte, so VBA and its signatures stay byte-identical.

**Reuse**
- `Asset` model (extended additively: fqdn, mac_address, serial_number, ip_addresses[], inventory{template fields}, correlated_asset_id). No second asset table.
- Ingest parsers and pipeline (`_match_asset` now delegates to the correlation engine; findings, finding IDs and source IDs stay unchanged).
- TR bounded workbook writer and verifier (`services/tr/xlsx.write/verify`), one sheet at a time, each step verified.
- AI provider abstraction + strict schema + deterministic fallback (as in TR analysis); server-side reference validation.
- Worker jobs, object storage, audit, RBAC (`system.read` / `system.write`), Mapping Review page (asset correlations are surfaced there and decided in the inventory screen), evidence freshness policies (stale window), MOCKED labelling (`MockAdapter`, `source="mock_adapter"`).

**New**
- `services/ingest/parsers.asset_facts`: CKL `ASSET` (HOST_NAME/IP/FQDN/MAC, ASSET_TYPE, ROLE), CKLB `target_data`, Nessus `HostProperties` (hostname, host-fqdn, host-ip, mac-address, operating-system, cpe-*), XCCDF `target`/`target-address`/`target-facts`, Nessus CSV host columns. Only facts present in the file are used.
- `services/inventory/`: `ident` (normalisation), `correlate` (deterministic matching, identifier history), `consistency` (checks → discrepancies, proposal → approval → apply), `hwsw` (template detect/import/export), `ai` (explain/rank, validated).
- Tables (migration 0021): `asset_identifiers` (history, multiple IPs/MACs), `software_items`, `inventory_imports`, `inventory_exports`, `inventory_discrepancies`, `asset_correlations`.
- Jobs `inventory.import`, `inventory.check`, `inventory.ai`; page `/inventory`; Mapping Review banner for pending asset correlations.

Rules: deterministic matching only on reliable identifiers (MAC, serial, FQDN, hostname without conflicting IP). IP-only, shared-IP, conflicting or multiple candidates go to review. AI only ranks/explains ambiguous items (confidence + identifiers used); it never links, never creates assets, findings or vulnerabilities. Inventory data is never overwritten silently: discrepancy → "Accept resolution" (pending) → "Approve change" (applied) → audit; or "Ignore" with a reason.
