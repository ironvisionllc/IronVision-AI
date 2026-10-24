"""Shared separation of duties: TR row preparer identity; inventory accept identity + SoD outcome. Additive.

Revision ID: 0023
Revises: 0022
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tr_rows", sa.Column("prepared_by", JSONB))
    op.add_column("inventory_discrepancies", sa.Column("accepted_identity", JSONB))
    op.add_column("inventory_discrepancies", sa.Column("sod", JSONB))


def downgrade() -> None:
    op.drop_column("inventory_discrepancies", "sod")
    op.drop_column("inventory_discrepancies", "accepted_identity")
    op.drop_column("tr_rows", "prepared_by")
