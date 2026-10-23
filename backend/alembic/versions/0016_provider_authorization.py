"""Provider authorization type (inheritance provider record). Additive.

Revision ID: 0016
Revises: 0015
"""
import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("common_control_providers", sa.Column("authorization_type", sa.String(60), nullable=True))


def downgrade() -> None:
    op.drop_column("common_control_providers", "authorization_type")
