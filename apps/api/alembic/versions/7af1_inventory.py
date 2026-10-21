"""Persistent simulated inventory, independent of retailer foreign keys."""
from alembic import op
import sqlalchemy as sa

revision = "7af1_inventory"
down_revision = "26595d54a56e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("provider_stock",
        sa.Column("tenant_id", sa.Uuid(), primary_key=True),
        sa.Column("sku", sa.String(100), primary_key=True),
        sa.Column("available", sa.Integer(), nullable=False),
        sa.CheckConstraint("available >= 0", name="ck_provider_stock_available"))
    op.create_table("provider_reservations",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(150), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_provider_reservation_key"))


def downgrade():
    op.drop_table("provider_reservations")
    op.drop_table("provider_stock")
