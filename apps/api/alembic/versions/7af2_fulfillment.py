"""Persistent simulated fulfillment requests."""
from alembic import op
import sqlalchemy as sa

revision = "7af2_fulfillment"
down_revision = "7af1_inventory"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("provider_fulfillments",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("idempotency_key", sa.String(150), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_provider_fulfillment_key"))


def downgrade():
    op.drop_table("provider_fulfillments")
