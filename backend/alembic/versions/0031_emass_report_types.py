"""eMASS import sessions become multi-type: report_type, nullable system (unassigned imports), detection.

Revision ID: 0031
Revises: 0030
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("emass_imports", sa.Column("report_type", sa.String(30), nullable=False, server_default="control_information"))
    op.add_column("emass_imports", sa.Column("detected", JSONB))
    op.alter_column("emass_imports", "system_id", nullable=True)


def downgrade() -> None:
    op.execute("DELETE FROM emass_imports WHERE system_id IS NULL")
    op.alter_column("emass_imports", "system_id", nullable=False)
    op.drop_column("emass_imports", "detected")
    op.drop_column("emass_imports", "report_type")
