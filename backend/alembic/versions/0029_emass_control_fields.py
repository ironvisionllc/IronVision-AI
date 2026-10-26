"""eMASS Implementation Plan + Risk Assessment fields per system control (one row per control assignment).

Revision ID: 0029
Revises: 0028
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emass_control_fields",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("system_id", sa.Uuid, sa.ForeignKey("systems.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("assignment_id", sa.Uuid, sa.ForeignKey("control_assignments.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("control_id", sa.String(50), nullable=False),
        sa.Column("manually_inherited", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("control_designation", sa.String(30)),
        sa.Column("estimated_completion_date", sa.Date),
        sa.Column("responsible_entities", sa.Text),
        sa.Column("slcm_criticality", sa.Text),
        sa.Column("slcm_frequency", sa.String(30)),
        sa.Column("slcm_method", sa.String(30)),
        sa.Column("slcm_reporting", sa.Text),
        sa.Column("slcm_tracking", sa.Text),
        sa.Column("slcm_comments", sa.Text),
        sa.Column("na_justification", sa.Text),
        sa.Column("common_control_provider", sa.String(20)),
        sa.Column("severity", sa.String(20)),
        sa.Column("relevance_of_threat", sa.String(20)),
        sa.Column("likelihood", sa.String(20)),
        sa.Column("impact", sa.String(20)),
        sa.Column("impact_description", sa.Text),
        sa.Column("residual_risk_level", sa.String(20)),
        sa.Column("vulnerability_summary", sa.Text),
        sa.Column("recommendations", sa.Text),
        sa.Column("mitigations", sa.Text),
        sa.Column("assisted", JSONB),
        sa.Column("updated_by", sa.Uuid),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_table("emass_control_fields")
