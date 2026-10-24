"""Policy mapping review: reanalysis proposals kept beside approved mappings, manual-review flag, reviewer comments, coverage overrides.

Revision ID: 0026
Revises: 0025
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("policy_control_maps", sa.Column("reanalysis", JSONB))
    op.add_column("policy_control_maps", sa.Column("review_flag", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("policy_control_maps", sa.Column("comments", JSONB))
    op.add_column("policy_control_maps", sa.Column("coverage_override", JSONB))


def downgrade() -> None:
    for c in ("coverage_override", "comments", "review_flag", "reanalysis"):
        op.drop_column("policy_control_maps", c)
