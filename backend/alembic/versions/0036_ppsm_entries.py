"""PPSM boundary entries (ports, protocols, services) per system – populated by the eMASS PPSM import or by hand.
Additive; downgrade drops the table.

Revision ID: 0036
Revises: 0035
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0036"
down_revision = "0035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ppsm_entries",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("system_id", sa.Uuid(), sa.ForeignKey("systems.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("record_key", sa.String(200), nullable=False),
        sa.Column("asset_id", sa.String(50)),
        sa.Column("port", sa.String(20), nullable=False),
        sa.Column("protocol", sa.String(20), nullable=False),
        sa.Column("data_service", sa.String(100), nullable=False),
        sa.Column("boundaries", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("fqdn", sa.String(100)),
        sa.Column("purpose", sa.Text()),
        sa.Column("source", sa.String(30), nullable=False, server_default="manual"),
        sa.Column("import_id", sa.Uuid()),
        sa.Column("source_row", sa.Integer()),
        sa.Column("updated_by", sa.Uuid()),
        sa.UniqueConstraint("system_id", "record_key", name="uq_ppsm_entries_system_key"),
    )


def downgrade() -> None:
    op.drop_table("ppsm_entries")
