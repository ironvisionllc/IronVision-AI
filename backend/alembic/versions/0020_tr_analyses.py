"""TR evidence analyses (AI or deterministic), stored per run for audit. Additive.

Revision ID: 0020
Revises: 0019
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("tr_analyses",
                    sa.Column("id", sa.Uuid, primary_key=True),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
                    sa.Column("row_id", sa.Uuid, sa.ForeignKey("tr_rows.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("workbook_id", sa.Uuid, sa.ForeignKey("tr_workbooks.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("mode", sa.String(20), nullable=False), sa.Column("provider", sa.String(50)), sa.Column("model", sa.String(200)),
                    sa.Column("prompt_version", sa.String(100), nullable=False), sa.Column("input_ids", JSONB, nullable=False),
                    sa.Column("input_bundle", JSONB, nullable=False), sa.Column("output", JSONB, nullable=False), sa.Column("dropped", JSONB),
                    sa.Column("error", sa.Text), sa.Column("requested_by", sa.Uuid))


def downgrade() -> None:
    op.drop_table("tr_analyses")
