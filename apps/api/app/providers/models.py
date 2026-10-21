from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.models.base import Base


class Stock(Base):
    __tablename__ = "provider_stock"
    __table_args__ = (
        CheckConstraint("available >= 0", name="ck_provider_stock_available"),
    )
    tenant_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    sku: Mapped[str] = mapped_column(String(100), primary_key=True)
    available: Mapped[int] = mapped_column(Integer, nullable=False)


class Reservation(Base):
    __tablename__ = "provider_reservations"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_provider_reservation_key"
        ),
    )
    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(150), nullable=False)
    items: Mapped[list] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="reserved", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
