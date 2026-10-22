from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.base import Base


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["execution_id", "tenant_id"],
            ["workflow_executions.id", "workflow_executions.tenant_id"],
            name="fk_audit_execution_tenant",
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    execution_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    previous_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    new_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    note: Mapped[str] = mapped_column(String(1000), nullable=False)
    development_operator: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class RecoveryRequest(Base):
    __tablename__ = "recovery_requests"
    __table_args__ = (
        ForeignKeyConstraint(
            ["execution_id", "tenant_id"],
            ["workflow_executions.id", "workflow_executions.tenant_id"],
            name="fk_recovery_execution_tenant",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("execution_id", "request_key", name="uq_recovery_request_key"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    execution_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    request_key: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
