"""Manage imported data: import_trash (snapshots of deleted imported rows, 30-day undo) and review_flags ("needs re-review" on decisions
whose underlying imported data was deleted – the decision itself is never removed).

Revision ID: 0039
Revises: 0038
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def _core():
    return [sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def upgrade() -> None:
    op.create_table("import_trash", *_core(),
                    sa.Column("org_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("system_id", sa.Uuid, nullable=True, index=True),
                    sa.Column("import_kind", sa.String(20), nullable=False),
                    sa.Column("import_id", sa.Uuid, nullable=False, index=True),
                    sa.Column("op_id", sa.String(20), nullable=False, index=True),
                    sa.Column("action", sa.String(20), nullable=False),
                    sa.Column("entry_id", sa.String(200), nullable=False),
                    sa.Column("label", sa.Text),
                    sa.Column("snapshot", JSONB, nullable=False),
                    sa.Column("deleted_by", sa.String(255), nullable=False),
                    sa.Column("restored_at", sa.DateTime(timezone=True)),
                    sa.Column("restored_by", sa.String(255)))
    op.create_table("review_flags", *_core(),
                    sa.Column("org_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("system_id", sa.Uuid, nullable=True, index=True),
                    sa.Column("entity_type", sa.String(40), nullable=False),
                    sa.Column("entity_id", sa.String(100), nullable=False),
                    sa.Column("label", sa.Text, nullable=False),
                    sa.Column("reason", sa.Text, nullable=False),
                    sa.Column("import_kind", sa.String(20)),
                    sa.Column("import_id", sa.Uuid),
                    sa.Column("op_id", sa.String(20), index=True),
                    sa.Column("status", sa.String(20), nullable=False, server_default="open"),
                    sa.Column("resolved_by", sa.String(255)),
                    sa.Column("resolved_at", sa.DateTime(timezone=True)),
                    sa.Column("resolution", sa.Text))


def downgrade() -> None:
    op.drop_table("review_flags")
    op.drop_table("import_trash")
