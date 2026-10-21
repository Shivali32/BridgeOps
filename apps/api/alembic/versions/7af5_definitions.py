"""Versioned workflows, tenant assignments and approval requests."""
from alembic import op
import sqlalchemy as sa

revision = "7af5_definitions"
down_revision = "7af4_integrations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("workflow_definitions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("id", "tenant_id", name="uq_definition_id_tenant"))
    op.create_index("ix_workflow_definitions_tenant_id", "workflow_definitions", ["tenant_id"])
    op.create_table("workflow_versions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("definition_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["definition_id", "tenant_id"], ["workflow_definitions.id", "workflow_definitions.tenant_id"], name="fk_version_definition_tenant", ondelete="RESTRICT"),
        sa.UniqueConstraint("definition_id", "version", name="uq_workflow_version"))
    op.add_column("integrations", sa.Column("workflow_id", sa.Uuid()))
    op.create_foreign_key("fk_integration_workflow_tenant", "integrations", "workflow_definitions", ["workflow_id", "tenant_id"], ["id", "tenant_id"], ondelete="RESTRICT")
    op.create_unique_constraint("uq_execution_id_tenant", "workflow_executions", ["id", "tenant_id"])
    op.create_table("approvals",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("execution_id", sa.Uuid(), nullable=False),
        sa.Column("step_name", sa.String(100), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("decision_note", sa.String(1000)),
        sa.Column("development_operator", sa.String(100)),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["execution_id", "tenant_id"], ["workflow_executions.id", "workflow_executions.tenant_id"], name="fk_approval_execution_tenant", ondelete="RESTRICT"),
        sa.UniqueConstraint("execution_id", "step_name", name="uq_execution_approval_step"),
        sa.CheckConstraint("status IN ('pending', 'approved', 'rejected')", name="ck_approval_status"))
    op.create_index("ix_approvals_tenant_id", "approvals", ["tenant_id"])


def downgrade():
    op.drop_table("approvals")
    op.drop_constraint("uq_execution_id_tenant", "workflow_executions", type_="unique")
    op.drop_constraint("fk_integration_workflow_tenant", "integrations", type_="foreignkey")
    op.drop_column("integrations", "workflow_id")
    op.drop_table("workflow_versions")
    op.drop_table("workflow_definitions")
