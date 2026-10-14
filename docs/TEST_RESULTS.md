# Test results

Generated 2026-10-14T18:25:30+00:00 by `scripts/run_acceptance.sh` (pod run, PostgreSQL 16).

## Acceptance suite (AT-1 … AT-12)
| # | Test | Scenario | Result |
|---|---|---|---|
| 01 | `test_at01_ingest_stig_acas_with_provenance` | AT-1: STIG + ACAS ingestion → immutable evidence (SHA-256, unsigned), canonical findings, reconciled source cards. | **PASSED** |
| 02 | `test_at02_rescan_dedup_observations_not_duplicates` | AT-2: Re-ingest / rescan adds observations to canonical findings; duplicate files are rejected by hash. | **PASSED** |
| 03 | `test_at03_end_to_end_poam_closure_leadership_audit` | AT-3: finding → POA&M → remediated rescan (closure eligible, never auto-closed) → closure approval → leadership + audit. | **PASSED** |
| 04 | `test_at04_rbac_separation_of_duties` | AT-4: system-scoped RBAC; ISSO cannot accept risk; self-approval denied and audited. | **PASSED** |
| 05 | `test_at05_ai_statement_grounded_and_human_approved` | AT-5: AI implementation statement uses only real evidence citations and requires human review. | **PASSED** |
| 06 | `test_at06_freshness_per_asset_and_queue` | AT-6: per-asset freshness → partially stale control → ISSO queue reason and leadership freshness. | **PASSED** |
| 07 | `test_at07_policy_auditor_35_vs_90` | AT-7: policy 35-day vs observed 90-day AC-2(3) discrepancy; confirm creates finding; dismissal keeps justification. | **PASSED** |
| 08 | `test_at08_attestation_expiry_cascade` | AT-8: owner-only attestation; expiry cascades to evidence, control queue, notification and audit. | **PASSED** |
| 09 | `test_at09_oscal_poam_schema_valid` | AT-9: OSCAL POA&M (and SSP/AR/AP) validate against the official NIST OSCAL v1.2.2 JSON schemas. | **PASSED** |
| 10 | `test_at10_emass_failure_retry_never_claims_success` | AT-10: simulated eMASS failure → local change preserved, pending retry; retry succeeds; conflict needs human choice. | **PASSED** |
| 11 | `test_at11_controlled_content_update` | AT-11: STIG V1R2 diff (6/3/11/2) + impact (P-0027 CAT II→CAT I) previewed before apply; history not rewritten. | **PASSED** |
| 12 | `test_at12_persistence_across_reinit` | AT-12: data written through the API survives app re-init / a brand-new DB connection pool. | **PASSED** |

Acceptance summary: `============================= 12 passed in 23.25s ==============================`

## Full regression suite (`pytest tests`)
`201 passed, 2 skipped, 2 warnings in 67.50s (0:01:07)`

## Manual persistence check (AT-12, restart)
1. Create a POA&M milestone in the UI.  2. `docker compose restart backend worker` (pod: `supervisorctl restart backend worker`).
3. Reload the POA&M – the milestone and its audit event are present.  (Automated part: AT-12 disposes the connection pool and reads back via a new engine.)

## Not executed here
- Docker image builds / `docker compose up` (no Docker daemon in the build pod) – see CI workflow and verify_portability.sh.
- OIDC against a real IdP (Keycloak profile provided, untested here); ClamAV scanning (profile provided, untested); GitHub Actions CI (not runnable here).
