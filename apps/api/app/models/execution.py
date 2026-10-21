import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.order import Order


class WorkflowExecution(Base):
    __tablename__ = "workflow_executions"

    __table_args__ = (
        ForeignKeyConstraint(
            ["order_id", "tenant_id"],
            ["orders.id", "orders.tenant_id"],
            name="fk_workflow_order_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', "
            "'completed', 'failed', 'needs_attention')",
            name="ck_workflow_executions_status",
        ),
        Index(
            "ix_workflow_executions_tenant_order",
            "tenant_id",
            "order_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="pending",
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    definition_snapshot: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    error_category: Mapped[str | None] = mapped_column(String(50))

    order: Mapped["Order"] = relationship(
        back_populates="executions",
        foreign_keys=[order_id, tenant_id],
    )

    steps: Mapped[list["StepExecution"]] = relationship(
        back_populates="execution",
        cascade="all, delete-orphan",
    )


class StepExecution(Base):
    __tablename__ = "step_executions"

    __table_args__ = (
        CheckConstraint(
            "attempt_number > 0",
            name="ck_step_executions_attempt",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', "
            "'completed', 'failed', 'skipped', 'unknown')",
            name="ck_step_executions_status",
        ),
        Index(
            "ix_step_executions_execution",
            "execution_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    execution_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey(
            "workflow_executions.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
    )

    step_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="pending",
    )

    attempt_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default="1",
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    input_summary: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    output_summary: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(150))
    external_reference: Mapped[str | None] = mapped_column(String(150))
    error_category: Mapped[str | None] = mapped_column(String(50))
    retryable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    execution: Mapped["WorkflowExecution"] = relationship(
        back_populates="steps",
    )
