"""RMF accuracy release: categorization revisions/approvals, PTA question sets + responses, agency overlays, NSS determination and
applicability flags on systems. Additive; existing categorizations are copied into revision 1 (status legacy_unreviewed) without loss.

Revision ID: 0024
Revises: 0023
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def _core():
    return [sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()"))]


def upgrade() -> None:
    op.add_column("systems", sa.Column("nss_determination", sa.String(10)))
    op.add_column("systems", sa.Column("applicability_flags", JSONB))
    op.create_table("categorization_records", *_core(),
                    sa.Column("system_id", UUID(as_uuid=True), sa.ForeignKey("systems.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("revision", sa.Integer, nullable=False), sa.Column("framework", sa.String(20), nullable=False),
                    sa.Column("nss_determination", sa.String(10)), sa.Column("information_types", JSONB), sa.Column("impacts", JSONB),
                    sa.Column("overall", sa.String(20)), sa.Column("baseline", sa.String(20)), sa.Column("detail", JSONB), sa.Column("rationale", sa.Text),
                    sa.Column("status", sa.String(30), nullable=False), sa.Column("inputs_hash", sa.String(64)),
                    sa.Column("submitted_by", sa.String(255)), sa.Column("approved_by", sa.String(255)), sa.Column("approved_by_real", sa.String(255)),
                    sa.Column("approved_at", sa.DateTime(timezone=True)), sa.Column("approval_rationale", sa.Text),
                    sa.UniqueConstraint("system_id", "revision", name="uq_categorization_revision"))
    op.create_table("pta_question_sets", *_core(),
                    sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), index=True),
                    sa.Column("key", sa.String(100), nullable=False), sa.Column("version", sa.Integer, nullable=False), sa.Column("title", sa.String(255), nullable=False),
                    sa.Column("label", sa.String(255)), sa.Column("questions", JSONB, nullable=False), sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
                    sa.Column("created_by", sa.String(255)))
    op.create_table("pta_responses", *_core(),
                    sa.Column("system_id", UUID(as_uuid=True), sa.ForeignKey("systems.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("question_set_id", UUID(as_uuid=True), sa.ForeignKey("pta_question_sets.id"), nullable=True),
                    sa.Column("question_set_key", sa.String(100)), sa.Column("question_set_version", sa.Integer), sa.Column("revision", sa.Integer, nullable=False),
                    sa.Column("answers", JSONB, nullable=False), sa.Column("flags", JSONB), sa.Column("recommendation", sa.Text),
                    sa.Column("status", sa.String(20), nullable=False), sa.Column("submitted_by", sa.String(255)), sa.Column("reviewer", sa.String(255)),
                    sa.Column("reviewed_at", sa.DateTime(timezone=True)), sa.Column("review_rationale", sa.Text), sa.Column("determination", sa.String(40)))
    op.create_table("agency_overlays", *_core(),
                    sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("name", sa.String(255), nullable=False), sa.Column("issuing_authority", sa.String(255), nullable=False),
                    sa.Column("source_document", sa.String(500), nullable=False), sa.Column("framework", sa.String(20), nullable=False),
                    sa.Column("version", sa.String(50), nullable=False), sa.Column("applicability", sa.Text, nullable=False),
                    sa.Column("status", sa.String(30), nullable=False), sa.Column("effective_date", sa.Date), sa.Column("created_by", sa.String(255)))
    op.execute("""
        INSERT INTO categorization_records (system_id, revision, framework, information_types, impacts, overall, baseline, detail, status, submitted_by, rationale)
        SELECT id, 1, COALESCE(categorization_mode, 'fips199'), information_types,
               jsonb_build_object('c', confidentiality_impact, 'i', integrity_impact, 'a', availability_impact),
               categorization, categorization_detail->>'baseline', categorization_detail, 'legacy_unreviewed', 'migration 0024',
               'Migrated from the categorization recorded before revision tracking; review and approve.'
        FROM systems WHERE information_types IS NOT NULL OR confidentiality_impact IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_table("agency_overlays")
    op.drop_table("pta_responses")
    op.drop_table("pta_question_sets")
    op.drop_table("categorization_records")
    op.drop_column("systems", "applicability_flags")
    op.drop_column("systems", "nss_determination")
