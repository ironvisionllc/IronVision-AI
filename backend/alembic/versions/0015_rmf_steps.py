"""RMF 7-step restructure: eMASS-aligned system fields, key-role contacts, PTA, categorization mode; structure-only overlays. Additive.

Revision ID: 0015
Revises: 0014
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

COLS = [("system_type", sa.String(80)), ("acquisition_category", sa.String(40)), ("categorization_mode", sa.String(20)),
        ("environment_detail", postgresql.JSONB()), ("key_roles", postgresql.JSONB()), ("pta", postgresql.JSONB()),
        ("processes_pii", sa.Boolean()), ("categorization_detail", postgresql.JSONB())]


def upgrade() -> None:
    for name, typ in COLS:
        op.add_column("systems", sa.Column(name, typ, nullable=True))
    op.add_column("overlays", sa.Column("structure_only", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    op.drop_column("overlays", "structure_only")
    for name, _ in reversed(COLS):
        op.drop_column("systems", name)
