"""eMASS Control Information import sessions (upload → review → apply / discard).

Revision ID: 0030
Revises: 0029
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0030"
down_revision = "0029"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "emass_imports",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("org_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("system_id", sa.Uuid, sa.ForeignKey("systems.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("storage_key", sa.String(1000), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="review"),
        sa.Column("uploaded_by", sa.Uuid),
        sa.Column("uploaded_by_email", sa.String(320)),
        sa.Column("detection", JSONB),
        sa.Column("report", JSONB),
        sa.Column("items", JSONB),
        sa.Column("counts", JSONB),
        sa.Column("applied_by_email", sa.String(320)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
    )


def downgrade() -> None:
    op.drop_table("emass_imports")
