"""OIDC hardening: DB-backed single-use login state, one-time login codes, RP-logout hint (non-destructive: 2 tables + 1 nullable column).

Revision ID: 0012
Revises: 0011
"""
import sqlalchemy as sa
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "oidc_pending",
        sa.Column("state", sa.String(128), primary_key=True),
        sa.Column("verifier", sa.String(128), nullable=False),
        sa.Column("nonce", sa.String(128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )
    op.create_table(
        "oidc_login_codes",
        sa.Column("code_sha256", sa.String(64), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("id_token", sa.Text()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False, index=True),
    )
    op.add_column("auth_sessions", sa.Column("id_token_hint", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("auth_sessions", "id_token_hint")
    op.drop_table("oidc_login_codes")
    op.drop_table("oidc_pending")
