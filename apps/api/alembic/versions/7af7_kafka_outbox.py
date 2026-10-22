"""Durable Kafka workflow commands and consumer receipts."""
from alembic import op
import sqlalchemy as sa

revision = "7af7_kafka_outbox"
down_revision = "7af6_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_orders_status", "orders", type_="check")
    op.create_check_constraint("ck_orders_status", "orders", "status IN ('received', 'queued', 'processing', 'completed', 'failed', 'needs_attention')")
    op.add_column("workflow_executions", sa.Column("active_event_id", sa.Uuid()))
    op.add_column("workflow_executions", sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.execute("UPDATE workflow_executions SET created_at=COALESCE(started_at, created_at)")
    op.create_table("outbox_events",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_error", sa.String(200)),
        sa.ForeignKeyConstraint(["execution_id", "tenant_id"], ["workflow_executions.id", "workflow_executions.tenant_id"], name="fk_outbox_execution_tenant", ondelete="RESTRICT"))
    op.create_index("ix_outbox_publish", "outbox_events", ["published_at", "next_attempt_at"])
    op.create_index("ix_outbox_events_tenant_id", "outbox_events", ["tenant_id"])
    op.create_table("event_receipts",
        sa.Column("event_id", sa.Uuid(), primary_key=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_table("quarantined_messages",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("topic", sa.String(250), nullable=False),
        sa.Column("partition", sa.Integer(), nullable=False),
        sa.Column("offset", sa.Integer(), nullable=False),
        sa.Column("payload_digest", sa.String(64), nullable=False),
        sa.Column("reason", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("topic", "partition", "offset", name="uq_quarantine_position"))


def downgrade():
    op.execute("UPDATE orders SET status='processing' WHERE status='queued'")
    op.drop_constraint("ck_orders_status", "orders", type_="check")
    op.create_check_constraint("ck_orders_status", "orders", "status IN ('received', 'processing', 'completed', 'failed', 'needs_attention')")
    op.drop_table("quarantined_messages")
    op.drop_table("event_receipts")
    op.drop_table("outbox_events")
    op.drop_column("workflow_executions", "active_event_id")
    op.drop_column("workflow_executions", "created_at")
