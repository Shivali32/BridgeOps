"""Audited recovery requests and workflow ownership fencing."""
from alembic import op
import sqlalchemy as sa

revision = "7af6_operations"
down_revision = "7af5_definitions"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workflow_executions", sa.Column("run_token", sa.Uuid()))
    op.add_column("workflow_executions", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    op.create_unique_constraint("uq_step_attempt", "step_executions", ["execution_id", "step_name", "attempt_number"])
    op.create_table("audit_events",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("tenant_id", sa.Uuid(), nullable=False), sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(50), nullable=False), sa.Column("previous_state", sa.JSON(), nullable=False), sa.Column("new_state", sa.JSON(), nullable=False),
        sa.Column("note", sa.String(1000), nullable=False), sa.Column("development_operator", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["execution_id", "tenant_id"], ["workflow_executions.id", "workflow_executions.tenant_id"], name="fk_audit_execution_tenant", ondelete="RESTRICT"))
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])
    op.create_table("recovery_requests",
        sa.Column("id", sa.Uuid(), primary_key=True), sa.Column("tenant_id", sa.Uuid(), nullable=False), sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.String(100), nullable=False), sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["execution_id", "tenant_id"], ["workflow_executions.id", "workflow_executions.tenant_id"], name="fk_recovery_execution_tenant", ondelete="RESTRICT"),
        sa.UniqueConstraint("execution_id", "request_key", name="uq_recovery_request_key"))


def downgrade():
    op.drop_table("recovery_requests")
    op.drop_table("audit_events")
    op.drop_constraint("uq_step_attempt", "step_executions", type_="unique")
    op.drop_column("workflow_executions", "heartbeat_at")
    op.drop_column("workflow_executions", "run_token")
