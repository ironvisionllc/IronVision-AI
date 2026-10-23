"""eMASS Test Result (TR) workbooks: template definitions, imported workbooks, rows and exports. Additive.

Revision ID: 0019
Revises: 0018
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def _core():
    return [sa.Column("id", sa.Uuid, primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]


def upgrade() -> None:
    op.create_table("tr_templates", *_core(),
                    sa.Column("org_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("name", sa.String(255), nullable=False), sa.Column("version", sa.Integer, nullable=False),
                    sa.Column("fingerprint", sa.String(64), nullable=False, index=True), sa.Column("definition", JSONB, nullable=False),
                    sa.Column("created_by", sa.String(255)))
    op.create_table("tr_workbooks", *_core(),
                    sa.Column("org_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("system_id", sa.Uuid, sa.ForeignKey("systems.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("template_id", sa.Uuid, sa.ForeignKey("tr_templates.id", ondelete="SET NULL")),
                    sa.Column("file_name", sa.String(500), nullable=False), sa.Column("sha256", sa.String(64), nullable=False),
                    sa.Column("storage_key", sa.String(1000), nullable=False), sa.Column("version", sa.Integer, nullable=False),
                    sa.Column("status", sa.String(30), nullable=False), sa.Column("error", sa.Text),
                    sa.Column("detection", JSONB), sa.Column("definition", JSONB), sa.Column("counts", JSONB),
                    sa.Column("uploaded_by", sa.String(255)), sa.Column("generated_at", sa.DateTime(timezone=True)))
    op.create_table("tr_rows", *_core(),
                    sa.Column("workbook_id", sa.Uuid, sa.ForeignKey("tr_workbooks.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("row_number", sa.Integer, nullable=False), sa.Column("added", sa.Boolean, nullable=False, server_default=sa.false()),
                    sa.Column("control_acronym", sa.String(50)), sa.Column("ap_acronym", sa.String(50)), sa.Column("cci_id", sa.String(20)),
                    sa.Column("control_id", sa.String(50), index=True), sa.Column("match_status", sa.String(20), nullable=False),
                    sa.Column("match_reason", sa.Text), sa.Column("proposed", JSONB), sa.Column("sources", JSONB), sa.Column("flags", JSONB),
                    sa.Column("state", sa.String(20), nullable=False, server_default="missing"), sa.Column("final", JSONB),
                    sa.Column("decided_by", sa.String(255)), sa.Column("decided_at", sa.DateTime(timezone=True)), sa.Column("justification", sa.Text),
                    sa.Column("last_exported_at", sa.DateTime(timezone=True)),
                    sa.UniqueConstraint("workbook_id", "row_number", name="uq_tr_rows_wb_row"))
    op.create_table("tr_exports", *_core(),
                    sa.Column("workbook_id", sa.Uuid, sa.ForeignKey("tr_workbooks.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("system_id", sa.Uuid, nullable=False, index=True), sa.Column("version", sa.Integer, nullable=False),
                    sa.Column("file_name", sa.String(500), nullable=False), sa.Column("sha256", sa.String(64), nullable=False),
                    sa.Column("storage_key", sa.String(1000), nullable=False), sa.Column("exported_by", sa.String(255), nullable=False),
                    sa.Column("counts", JSONB), sa.Column("evidence_ids", JSONB), sa.Column("verification", JSONB), sa.Column("template_version", sa.Integer))


def downgrade() -> None:
    for t in ("tr_exports", "tr_rows", "tr_workbooks", "tr_templates"):
        op.drop_table(t)
