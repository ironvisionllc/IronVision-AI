"""Policy requirement coverage: one row per policy × control × requirement (DISA CCI or SP 800-53A objective). Additive.

Revision ID: 0018
Revises: 0017
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_requirement_coverage",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("org_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("policy_id", sa.Uuid, sa.ForeignKey("policies.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("policy_version", sa.Integer, nullable=False),
        sa.Column("control_id", sa.String(30), nullable=False, index=True),
        sa.Column("requirement_type", sa.String(12), nullable=False),
        sa.Column("requirement_id", sa.String(100), nullable=False, index=True),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("concept", sa.String(40), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("confidence", sa.String(10), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("snippets", JSONB),
        sa.Column("parameter", sa.String(120)),
        sa.Column("parameter_value", sa.String(255)),
        sa.Column("needs", sa.Text),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("override", JSONB),
        sa.Column("linked", JSONB),
    )


def downgrade() -> None:
    op.drop_table("policy_requirement_coverage")
