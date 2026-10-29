"""Auto-save: autosave_sessions (one coalesced audit event per record per editing session) and user_drafts (registration draft).

Revision ID: 0040
Revises: 0039
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def _core():
    return [sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)]


def upgrade() -> None:
    op.create_table("autosave_sessions", *_core(),
                    sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("actor_email", sa.String(255)),
                    sa.Column("entity_type", sa.String(50)),
                    sa.Column("entity_id", sa.String(100)),
                    sa.Column("action", sa.String(100), nullable=False),
                    sa.Column("before", JSONB), sa.Column("after", JSONB), sa.Column("details", JSONB),
                    sa.Column("saves", sa.Integer, nullable=False, server_default="0"),
                    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("last_at", sa.DateTime(timezone=True), nullable=False),
                    sa.Column("closed_at", sa.DateTime(timezone=True), index=True))
    op.create_table("user_drafts", *_core(),
                    sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("org_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("kind", sa.String(50), nullable=False),
                    sa.Column("data", JSONB, nullable=False),
                    sa.UniqueConstraint("user_id", "kind", name="uq_user_drafts_user_kind"))


def downgrade() -> None:
    op.drop_table("user_drafts")
    op.drop_table("autosave_sessions")
