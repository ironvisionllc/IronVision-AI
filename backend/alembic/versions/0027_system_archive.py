"""Logical system archive: hidden from active lists, audited, restorable.

Revision ID: 0027
Revises: 0026
"""
import sqlalchemy as sa
from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("systems", sa.Column("archived_at", sa.DateTime(timezone=True)))
    op.add_column("systems", sa.Column("archived_by", sa.String(255)))
    op.add_column("systems", sa.Column("archive_reason", sa.Text))


def downgrade() -> None:
    for c in ("archive_reason", "archived_by", "archived_at"):
        op.drop_column("systems", c)
