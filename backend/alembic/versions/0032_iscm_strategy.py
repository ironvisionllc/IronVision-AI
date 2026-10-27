"""System-level Continuous Monitoring Strategy (ISCM, SP 800-37 Task S-5) feeding the eMASS SLCM fields; per-control SLCM follow flag.

Revision ID: 0032
Revises: 0031
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def _core():
    return [sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def upgrade() -> None:
    op.create_table(
        "iscm_strategies", *_core(),
        sa.Column("system_id", sa.Uuid, sa.ForeignKey("systems.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("narrative", sa.Text), sa.Column("scope", sa.Text),
        sa.Column("defaults", JSONB, nullable=False, server_default="{}"),
        sa.Column("reporting", JSONB, nullable=False, server_default="[]"),
        sa.Column("review_activities", JSONB, nullable=False, server_default="[]"),
        sa.Column("evidence_requirements", JSONB, nullable=False, server_default="[]"),
        sa.Column("approved_snapshot", JSONB),
        sa.Column("submitted_by", JSONB), sa.Column("approved_by", JSONB),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("is_synthetic", sa.Boolean, nullable=False, server_default=sa.text("false")),
    )
    op.create_table(
        "iscm_profiles", *_core(),
        sa.Column("strategy_id", sa.Uuid, sa.ForeignKey("iscm_strategies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("match_type", sa.String(20), nullable=False),
        sa.Column("match_value", sa.String(2000), nullable=False),
        sa.Column("values", JSONB, nullable=False, server_default="{}"),
        sa.Column("sort_order", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column("emass_control_fields", sa.Column("slcm_inherit", JSONB))


def downgrade() -> None:
    op.drop_column("emass_control_fields", "slcm_inherit")
    op.drop_table("iscm_profiles")
    op.drop_table("iscm_strategies")
