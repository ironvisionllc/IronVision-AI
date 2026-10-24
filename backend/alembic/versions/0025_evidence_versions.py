"""Evidence versions (immutable, hash per version), logical removal, review/expiry metadata and revalidation flags on mappings.
Additive; every existing evidence record gets its current file as version history row 1..n (version = current version number).

Revision ID: 0025
Revises: 0024
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("evidence_versions",
                    sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
                    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
                    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
                    sa.Column("evidence_id", UUID(as_uuid=True), sa.ForeignKey("evidence.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("version", sa.Integer, nullable=False), sa.Column("file_name", sa.String(500)), sa.Column("storage_key", sa.String(500), nullable=False),
                    sa.Column("sha256", sa.String(64), nullable=False), sa.Column("size_bytes", sa.BigInteger, nullable=False), sa.Column("content_type", sa.String(100)),
                    sa.Column("uploaded_by", sa.String(255)), sa.Column("reason", sa.Text), sa.Column("scan_result", sa.String(50)),
                    sa.UniqueConstraint("evidence_id", "version", name="uq_evidence_version"))
    for name, col in (("status", sa.Column("status", sa.String(20), nullable=False, server_default="active")),
                      ("removed_reason", sa.Column("removed_reason", sa.Text)), ("removed_by", sa.Column("removed_by", sa.String(255))),
                      ("removed_at", sa.Column("removed_at", sa.DateTime(timezone=True))), ("uploaded_by", sa.Column("uploaded_by", sa.String(255))),
                      ("replacement_reason", sa.Column("replacement_reason", sa.Text)),
                      ("review_status", sa.Column("review_status", sa.String(30), nullable=False, server_default="unreviewed")),
                      ("expires_at", sa.Column("expires_at", sa.DateTime(timezone=True)))):
        op.add_column("evidence", col)
    op.add_column("evidence_controls", sa.Column("needs_revalidation", sa.Boolean, nullable=False, server_default=sa.false()))
    op.add_column("evidence_controls", sa.Column("revalidation_reason", sa.Text))
    op.add_column("evidence_controls", sa.Column("removed_at", sa.DateTime(timezone=True)))
    op.execute("""INSERT INTO evidence_versions (evidence_id, version, file_name, storage_key, sha256, size_bytes, content_type, uploaded_by, reason, created_at)
                  SELECT id, version, file_name, storage_key, sha256, size_bytes, content_type, provenance->>'received_by', 'Recorded before version history (migration 0025)', collected_at
                  FROM evidence""")


def downgrade() -> None:
    for c in ("removed_at", "revalidation_reason", "needs_revalidation"):
        op.drop_column("evidence_controls", c)
    for c in ("expires_at", "review_status", "replacement_reason", "uploaded_by", "removed_at", "removed_by", "removed_reason", "status"):
        op.drop_column("evidence", c)
    op.drop_table("evidence_versions")
