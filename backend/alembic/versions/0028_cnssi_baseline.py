"""CNSSI 1253 applied-baseline marker on systems (which trigraph's Appendix D baseline is applied; proposals are derived from it).

Revision ID: 0028
Revises: 0027
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0028"
down_revision = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("systems", sa.Column("cnssi_baseline", JSONB))


def downgrade() -> None:
    op.drop_column("systems", "cnssi_baseline")
