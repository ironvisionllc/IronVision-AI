"""Policy AI result cache (tenant-scoped, keyed by section content hashes + analyzer/prompt/model/catalog revision) for the v2 Policy Auditor.
Additive; downgrade drops the table.

Revision ID: 0035
Revises: 0034
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0035"
down_revision = "0034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "policy_ai_cache",
        sa.Column("id", sa.Uuid(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cache_key", sa.String(64), nullable=False),
        sa.Column("analyzer_version", sa.String(20), nullable=False),
        sa.Column("model", sa.String(120)),
        sa.Column("result", JSONB, nullable=False),
        sa.Column("provenance", JSONB),
        sa.Column("hits", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("org_id", "cache_key", name="uq_policy_ai_cache_org_key"),
    )


def downgrade() -> None:
    op.drop_table("policy_ai_cache")
