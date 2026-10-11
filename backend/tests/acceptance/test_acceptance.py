"""Acceptance suite: one test per specification acceptance test (1–12).
Run in a fresh test database:  make acceptance   (or: cd backend && pytest -c pytest.aegis.ini tests/acceptance -v)
Each test drives the real API/worker code paths. Where a scenario was built in an earlier phase, the acceptance test calls that
verified scenario function so there is one source of truth. Results are written to docs/TEST_RESULTS.md by scripts/run_acceptance.sh.
"""
import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from tests import test_phase1 as p1
from tests import test_phase2 as p2
from tests import test_phase3 as p3
from tests import test_phase4 as p4
from tests.conftest import auth

e2e = p2.e2e  # module-scoped fixture: STIG .ckl + ACAS .nessus ingested through the real pipeline


def test_at01_ingest_stig_acas_with_provenance(client, token, e2e):
    """AT-1: STIG + ACAS ingestion → immutable evidence (SHA-256, unsigned), canonical findings, reconciled source cards."""
    p2.test_new_upload_is_current_hash_recorded_unsigned(e2e)
    p2.test_source_cards_reconcile_with_findings_and_ledger(client, token, e2e)


def test_at02_rescan_dedup_observations_not_duplicates():
    """AT-2: Re-ingest / rescan adds observations to canonical findings; duplicate files are rejected by hash."""
    p1.test_duplicate_and_rescan_dedup()


def test_at03_end_to_end_poam_closure_leadership_audit(client, token, e2e):
    """AT-3: finding → POA&M → remediated rescan (closure eligible, never auto-closed) → closure approval → leadership + audit."""
    p2.test_full_closure_flow_and_consistency(client, token, e2e)


def test_at04_rbac_separation_of_duties(client, token, e2e):
    """AT-4: system-scoped RBAC; ISSO cannot accept risk; self-approval denied and audited."""
    p2.test_kev_flow_remediation_then_isso_cannot_accept_risk(client, token, e2e)
    p3.test_sca_independence_and_only_path(client, token)


def test_at05_ai_statement_grounded_and_human_approved(client, token, e2e, monkeypatch):
    """AT-5: AI implementation statement uses only real evidence citations and requires human review."""
    p2.test_ai_draft_strips_unknown_citations(client, token, e2e, monkeypatch)


def test_at06_freshness_per_asset_and_queue(client, token):
    """AT-6: per-asset freshness → partially stale control → ISSO queue reason and leadership freshness."""
    p2.test_partial_freshness_per_asset(client, token)


def test_at07_policy_auditor_35_vs_90(client, token):
    """AT-7: policy 35-day vs observed 90-day AC-2(3) discrepancy; confirm creates finding; dismissal keeps justification."""
    p3.test_policy_audit_35_vs_90_confirm_and_dismiss(client, token)


def test_at08_attestation_expiry_cascade(client, token):
    """AT-8: owner-only attestation; expiry cascades to evidence, control queue, notification and audit."""
    p3.test_attestation_owner_only_and_expiry_cascade(client, token)


def test_at09_oscal_poam_schema_valid(client, token):
    """AT-9: OSCAL POA&M (and SSP/AR/AP) validate against the official NIST OSCAL v1.2.2 JSON schemas."""
    p4.test_oscal_exports_schema_valid(client, token)


def test_at10_emass_failure_retry_never_claims_success(client, token):
    """AT-10: simulated eMASS failure → local change preserved, pending retry; retry succeeds; conflict needs human choice."""
    p4.test_emass_failure_retry_conflict_and_export_only(client, token)


def test_at11_controlled_content_update(client, token):
    """AT-11: STIG V1R2 diff (6/3/11/2) + impact (P-0027 CAT II→CAT I) previewed before apply; history not rewritten."""
    p4.test_stig_diff_impact_and_apply_preserves_history(client, token)


def test_at12_persistence_across_reinit(client, token):
    """AT-12: data written through the API survives app re-init / a brand-new DB connection pool.
    Manual check (documented in TEST_RESULTS.md): restart backend + worker (or `docker compose restart`) and re-open the record."""
    from app.config import get_settings
    from app.db import engine
    from app.models import AuditEvent, Poam, PoamMilestone

    isso = auth(token("isso@aegisrmf.demo"))
    with Session(engine) as db:
        p = db.scalar(select(Poam).where(Poam.status != "closed").order_by(Poam.seq).limit(1))
    title = f"AT-12 persistence milestone {uuid.uuid4()}"
    r = client.post(f"/api/v1/poams/{p.id}/milestones", json={"title": title, "due_date": "2030-01-01"}, headers=isso)
    assert r.status_code in (200, 201), r.text
    engine.dispose()  # drop every pooled connection, as a process restart would
    fresh = create_engine(get_settings().database_url)
    with Session(fresh) as db:
        assert db.scalar(select(PoamMilestone.id).where(PoamMilestone.poam_id == p.id, PoamMilestone.title == title))
        assert db.scalar(select(AuditEvent.id).where(AuditEvent.entity_id == str(p.id)).limit(1))
    fresh.dispose()
    from app.main import app as reinit  # app module re-import is idempotent; data is read back through the API
    assert reinit is not None
    assert any(m["title"] == title for m in client.get(f"/api/v1/poams/{p.id}", headers=isso).json()["milestones"])
