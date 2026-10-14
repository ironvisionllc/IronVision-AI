"""sandbox tenants + persona identities

Revision ID: 0011
Revises: 0010
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("is_sandbox", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("organizations", sa.Column("sandbox_personas", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("organizations", sa.Column("owner_user_id", sa.Uuid(), nullable=True))
    op.add_column("organizations", sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("organizations", sa.Column("sandbox_status", sa.String(30), nullable=True))
    op.add_column("organizations", sa.Column("sandbox_progress", JSONB(), nullable=True))
    op.add_column("users", sa.Column("persona_role", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("operator_id", sa.Uuid(), nullable=True))
    op.add_column("users", sa.Column("acting_role", sa.String(50), nullable=True))
    op.add_column("users", sa.Column("onboarding", JSONB(), nullable=True))


def downgrade() -> None:
    for c in ("onboarding", "acting_role", "operator_id", "persona_role"):
        op.drop_column("users", c)
    for c in ("sandbox_progress", "sandbox_status", "last_activity_at", "owner_user_id", "sandbox_personas", "is_sandbox"):
        op.drop_column("organizations", c)
