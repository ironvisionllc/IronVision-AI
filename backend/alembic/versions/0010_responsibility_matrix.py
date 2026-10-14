"""responsibility matrix text per provider control (CRM-style)

Revision ID: 0010
Revises: 0009
"""
import sqlalchemy as sa
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("provider_controls", sa.Column("provider_responsibility", sa.Text(), nullable=True))
    op.add_column("provider_controls", sa.Column("system_responsibility", sa.Text(), nullable=True))
    op.add_column("provider_controls", sa.Column("matrix_source", sa.String(255), nullable=True))


def downgrade() -> None:
    for c in ("matrix_source", "system_responsibility", "provider_responsibility"):
        op.drop_column("provider_controls", c)
