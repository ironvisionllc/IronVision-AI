"""Tailoring decisions record applicability and an optional compensating control (Select step 4).

Revision ID: 0033
Revises: 0032
"""
import sqlalchemy as sa
from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tailoring_decisions", sa.Column("applicability", sa.String(30)))
    op.add_column("tailoring_decisions", sa.Column("compensating_control_id", sa.String(50)))


def downgrade() -> None:
    op.drop_column("tailoring_decisions", "compensating_control_id")
    op.drop_column("tailoring_decisions", "applicability")
