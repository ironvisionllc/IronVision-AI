"""phase5 performance indexes (from perf smoke test hot paths)

Revision ID: 0009
Revises: 0008
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

IDX = [
    ("ix_findings_system_state", "findings", ["system_id", "current_state"]),
    ("ix_findings_benchmark", "findings", ["benchmark"]),
    ("ix_finding_observations_finding_observed", "finding_observations", ["finding_id", "observed_at"]),
    ("ix_audit_events_entity", "audit_events", ["entity_type", "entity_id"]),
    ("ix_emass_changes_entity", "emass_changes", ["entity_type", "entity_id"]),
    ("ix_jobs_status_type", "jobs", ["status", "job_type"]),
    ("ix_control_assignments_system", "control_assignments", ["system_id", "control_id"]),
    ("ix_evidence_controls_assignment", "evidence_controls", ["assignment_id"]),
    ("ix_auth_sessions_user", "auth_sessions", ["user_id"]),
]


def upgrade() -> None:
    for name, table, cols in IDX:
        op.create_index(name, table, cols, if_not_exists=True)


def downgrade() -> None:
    for name, table, _ in IDX:
        op.drop_index(name, table_name=table, if_exists=True)
