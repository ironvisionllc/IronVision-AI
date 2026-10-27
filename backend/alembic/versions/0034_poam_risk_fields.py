"""POA&M eMASS risk fields (Raw Severity, Relevance of Threat, Likelihood, Impact, Residual Risk Level, Mitigations, Comments) kept
separate from the technical severity/CAT; existing rows are preserved unchanged (no automatic conversion).

Revision ID: 0034
Revises: 0033
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None

COLS = ["raw_severity", "relevance_of_threat", "likelihood", "impact", "residual_risk_level"]


def upgrade() -> None:
    for c in COLS:
        op.add_column("poams", sa.Column(c, sa.String(20)))
    op.add_column("poams", sa.Column("mitigations", sa.Text()))
    op.add_column("poams", sa.Column("comments", sa.Text()))
    op.add_column("poams", sa.Column("risk_source", JSONB))


def downgrade() -> None:
    for c in ["risk_source", "comments", "mitigations", *reversed(COLS)]:
        op.drop_column("poams", c)
