"""HW/SW inventory + STIG→asset correlation: asset identifiers, software, imports/exports, discrepancies, correlations. Additive.

Revision ID: 0021
Revises: 0020
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def _core():
    return [sa.Column("id", sa.Uuid, primary_key=True), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())]


def _sys():
    return sa.Column("system_id", sa.Uuid, sa.ForeignKey("systems.id", ondelete="CASCADE"), nullable=False, index=True)


ASSET_COLS = ("fqdn", "mac_address", "serial_number", "ip_addresses", "inventory", "correlated_asset_id")


def upgrade() -> None:
    op.add_column("assets", sa.Column("fqdn", sa.String(255), index=True))
    op.add_column("assets", sa.Column("mac_address", sa.String(64), index=True))
    op.add_column("assets", sa.Column("serial_number", sa.String(255)))
    op.add_column("assets", sa.Column("ip_addresses", JSONB))
    op.add_column("assets", sa.Column("inventory", JSONB))
    op.add_column("assets", sa.Column("correlated_asset_id", sa.Uuid, sa.ForeignKey("assets.id", ondelete="SET NULL")))
    op.create_table("asset_identifiers", *_core(), _sys(),
                    sa.Column("asset_id", sa.Uuid, sa.ForeignKey("assets.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("kind", sa.String(20), nullable=False), sa.Column("value", sa.String(500), nullable=False),
                    sa.Column("source", sa.String(100), nullable=False), sa.Column("source_ref", sa.String(100)),
                    sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False), sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
                    sa.UniqueConstraint("asset_id", "kind", "value", "source", name="uq_asset_identifiers"))
    op.create_table("inventory_imports", *_core(), _sys(),
                    sa.Column("org_id", sa.Uuid, sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True),
                    sa.Column("file_name", sa.String(500), nullable=False), sa.Column("sha256", sa.String(64), nullable=False),
                    sa.Column("storage_key", sa.String(1000), nullable=False), sa.Column("version", sa.Integer, nullable=False),
                    sa.Column("status", sa.String(30), nullable=False), sa.Column("error", sa.Text), sa.Column("detection", JSONB),
                    sa.Column("counts", JSONB), sa.Column("uploaded_by", sa.String(255)))
    op.create_table("software_items", *_core(), _sys(),
                    sa.Column("asset_id", sa.Uuid, sa.ForeignKey("assets.id", ondelete="SET NULL")),
                    sa.Column("vendor", sa.String(255), nullable=False), sa.Column("name", sa.String(500), nullable=False),
                    sa.Column("version", sa.String(255)), sa.Column("sw_type", sa.String(100)), sa.Column("attributes", JSONB),
                    sa.Column("source", sa.String(100), nullable=False), sa.Column("import_id", sa.Uuid, sa.ForeignKey("inventory_imports.id", ondelete="SET NULL")))
    op.create_table("inventory_exports", *_core(), _sys(),
                    sa.Column("import_id", sa.Uuid, sa.ForeignKey("inventory_imports.id", ondelete="SET NULL")),
                    sa.Column("version", sa.Integer, nullable=False), sa.Column("file_name", sa.String(500), nullable=False),
                    sa.Column("sha256", sa.String(64), nullable=False), sa.Column("storage_key", sa.String(1000), nullable=False),
                    sa.Column("exported_by", sa.String(255), nullable=False), sa.Column("counts", JSONB), sa.Column("verification", JSONB))
    op.create_table("inventory_discrepancies", *_core(), _sys(),
                    sa.Column("kind", sa.String(50), nullable=False), sa.Column("key", sa.String(500), nullable=False),
                    sa.Column("status", sa.String(30), nullable=False), sa.Column("title", sa.Text, nullable=False),
                    sa.Column("records", JSONB, nullable=False), sa.Column("details", JSONB), sa.Column("recommendation", sa.Text),
                    sa.Column("proposed_change", JSONB), sa.Column("ai", JSONB), sa.Column("decided_by", sa.String(255)),
                    sa.Column("decided_at", sa.DateTime(timezone=True)), sa.Column("reason", sa.Text), sa.Column("applied_by", sa.String(255)),
                    sa.Column("applied_at", sa.DateTime(timezone=True)), sa.Column("last_detected_at", sa.DateTime(timezone=True)),
                    sa.UniqueConstraint("system_id", "key", name="uq_inventory_discrepancies_key"))
    op.create_table("asset_correlations", *_core(), _sys(),
                    sa.Column("key", sa.String(64), nullable=False), sa.Column("facts", JSONB, nullable=False), sa.Column("candidates", JSONB, nullable=False),
                    sa.Column("status", sa.String(20), nullable=False), sa.Column("method", sa.String(100)), sa.Column("reason", sa.Text),
                    sa.Column("observed_asset_id", sa.Uuid, sa.ForeignKey("assets.id", ondelete="CASCADE")),
                    sa.Column("chosen_asset_id", sa.Uuid, sa.ForeignKey("assets.id", ondelete="SET NULL")),
                    sa.Column("source_format", sa.String(30)), sa.Column("evidence_ids", JSONB), sa.Column("ai", JSONB),
                    sa.Column("decided_by", sa.String(255)), sa.Column("decided_at", sa.DateTime(timezone=True)), sa.Column("justification", sa.Text),
                    sa.Column("last_seen_at", sa.DateTime(timezone=True)),
                    sa.UniqueConstraint("system_id", "key", name="uq_asset_correlations_key"))


def downgrade() -> None:
    for t in ("asset_correlations", "inventory_discrepancies", "inventory_exports", "software_items", "inventory_imports", "asset_identifiers"):
        op.drop_table(t)
    for c in reversed(ASSET_COLS):
        op.drop_column("assets", c)
