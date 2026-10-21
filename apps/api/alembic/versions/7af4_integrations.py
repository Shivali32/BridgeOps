"""Tenant integration configuration and persistent import outcomes."""
from alembic import op
import sqlalchemy as sa

revision = "7af4_integrations"
down_revision = "7af3_execution_results"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("integrations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("connector_type", sa.String(50), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("mapping", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("id", "tenant_id", name="uq_integration_id_tenant"))
    op.create_index("ix_integrations_tenant_id", "integrations", ["tenant_id"])
    op.create_table("import_records",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("integration_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid()),
        sa.Column("source_reference", sa.String(100)),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("duplicate", sa.Boolean(), nullable=False),
        sa.Column("config_snapshot", sa.JSON(), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("row_numbers", sa.JSON(), nullable=False),
        sa.Column("error_message", sa.String(1000)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["integration_id", "tenant_id"], ["integrations.id", "integrations.tenant_id"], name="fk_import_integration_tenant", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["order_id", "tenant_id"], ["orders.id", "orders.tenant_id"], name="fk_import_order_tenant", ondelete="RESTRICT"))
    op.create_index("ix_import_records_tenant_id", "import_records", ["tenant_id"])


def downgrade():
    op.drop_table("import_records")
    op.drop_table("integrations")
