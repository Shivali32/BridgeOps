from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.base import Base


class Integration(Base):
    __tablename__ = "integrations"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_integration_id_tenant"),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(50), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    mapping: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ImportRecord(Base):
    __tablename__ = "import_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["integration_id", "tenant_id"],
            ["integrations.id", "integrations.tenant_id"],
            name="fk_import_integration_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["order_id", "tenant_id"],
            ["orders.id", "orders.tenant_id"],
            name="fk_import_order_tenant",
            ondelete="RESTRICT",
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False, index=True)
    integration_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    order_id: Mapped[UUID | None] = mapped_column(Uuid)
    source_reference: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    config_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    payload_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    row_numbers: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    error_message: Mapped[str | None] = mapped_column(String(1000))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
