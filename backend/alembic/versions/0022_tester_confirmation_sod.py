"""TR: rows approved before tester/date entry became mandatory need confirmation; inventory SoD (accepting real user). Additive.

Revision ID: 0022
Revises: 0021
"""
import sqlalchemy as sa
from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory_discrepancies", sa.Column("accepted_by_user_id", sa.Uuid))
    op.execute("UPDATE tr_rows SET state = 'needs_confirmation' WHERE state = 'approved' AND NOT (coalesce(final, '{}'::jsonb) ? 'tester_confirmed')")


def downgrade() -> None:
    op.execute("UPDATE tr_rows SET state = 'approved' WHERE state = 'needs_confirmation'")
    op.drop_column("inventory_discrepancies", "accepted_by_user_id")
