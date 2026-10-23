"""Official CNSSI 1253 overlay data: per-variant overlays, removal provenance. Additive.

Revision ID: 0017
Revises: 0016
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("overlays", sa.Column("group_key", sa.String(60), nullable=True))
    op.add_column("overlays", sa.Column("variant", sa.String(40), nullable=True))
    op.add_column("overlays", sa.Column("details", JSONB, nullable=True))
    op.add_column("tailoring_decisions", sa.Column("overlay_key", sa.String(100), nullable=True))
    op.add_column("tailoring_decisions", sa.Column("prior_origin", sa.String(30), nullable=True))
    op.add_column("tailoring_decisions", sa.Column("prior_origin_detail", sa.String(255), nullable=True))


def downgrade() -> None:
    for c in ("prior_origin_detail", "prior_origin", "overlay_key"):
        op.drop_column("tailoring_decisions", c)
    for c in ("details", "variant", "group_key"):
        op.drop_column("overlays", c)
