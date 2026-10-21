
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.execution import WorkflowExecution
    from app.models.tenant import Tenant


class Order(Base):
    __tablename__ = "orders"

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "external_order_id",
            name="uq_orders_tenant_external_id",
        ),
        UniqueConstraint(
            "id",
            "tenant_id",
            name="uq_orders_id_tenant",
        ),
        CheckConstraint(
            "status IN ('received', 'processing', "
            "'completed', 'failed', 'needs_attention')",
            name="ck_orders_status",
        ),
        Index("ix_orders_tenant_created", "tenant_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False,
    )

    external_order_id: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        server_default="received",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    tenant: Mapped["Tenant"] = relationship()

    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
    )

    executions: Mapped[list["WorkflowExecution"]] = relationship(
        back_populates="order",
        foreign_keys="[WorkflowExecution.order_id, "
        "WorkflowExecution.tenant_id]",
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    __table_args__ = (
        UniqueConstraint(
            "order_id",
            "sku",
            name="uq_order_items_order_sku",
        ),
        CheckConstraint(
            "quantity > 0",
            name="ck_order_items_quantity",
        ),
        CheckConstraint(
            "unit_price IS NULL OR unit_price >= 0",
            name="ck_order_items_unit_price",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
    )

    sku: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    quantity: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    unit_price: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2),
        nullable=True,
    )

    order: Mapped["Order"] = relationship(
        back_populates="items",
    )
