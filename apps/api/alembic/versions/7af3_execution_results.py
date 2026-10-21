"""Durable workflow snapshots and provider outcomes."""
from alembic import op
import sqlalchemy as sa

revision = "7af3_execution_results"
down_revision = "7af2_fulfillment"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("workflow_executions", sa.Column("definition_snapshot", sa.JSON(), nullable=False, server_default="{}"))
    op.add_column("workflow_executions", sa.Column("error_category", sa.String(50)))
    for name in ("input_summary", "output_summary"):
        op.add_column("step_executions", sa.Column(name, sa.JSON(), nullable=False, server_default="{}"))
    for name, length in (("idempotency_key", 150), ("external_reference", 150), ("error_category", 50)):
        op.add_column("step_executions", sa.Column(name, sa.String(length)))
    op.add_column("step_executions", sa.Column("retryable", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade():
    for name in ("retryable", "error_category", "external_reference", "idempotency_key", "output_summary", "input_summary"):
        op.drop_column("step_executions", name)
    op.drop_column("workflow_executions", "error_category")
    op.drop_column("workflow_executions", "definition_snapshot")
