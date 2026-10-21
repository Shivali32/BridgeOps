from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models.order import Order, OrderItem
from app.models.tenant import Tenant
from app.schemas.order import OrderCreate


class TenantNotFoundError(Exception):
    pass


class OrderNotFoundError(Exception):
    pass


class OrderConflictError(Exception):
    pass


class InactiveTenantError(Exception):
    pass


def require_tenant(db: Session, tenant_id: UUID, *, active: bool = False) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise TenantNotFoundError("Tenant not found.")
    if active and not tenant.is_active:
        raise InactiveTenantError("Tenant is inactive.")
    return tenant


def get_order(
    db: Session,
    tenant_id: UUID,
    order_id: UUID,
) -> Order:
    """Get an order belonging to the specified tenant."""
    require_tenant(db, tenant_id)
    stmt = (
        select(Order)
        .options(selectinload(Order.items))
        .where(
            Order.id == order_id,
            Order.tenant_id == tenant_id,
        )
    )

    order = db.scalar(stmt)

    if order is None:
        raise OrderNotFoundError("Order not found.")

    return order


def get_order_by_external_id(
    db: Session,
    tenant_id: UUID,
    external_order_id: str,
) -> Order | None:
    """Find an order using its tenant and external ID."""
    stmt = (
        select(Order)
        .options(selectinload(Order.items))
        .where(
            Order.tenant_id == tenant_id,
            Order.external_order_id == external_order_id,
        )
    )
    return db.scalar(stmt)


def list_orders(
    db: Session,
    tenant_id: UUID,
    limit: int = 50,
    offset: int = 0,
) -> list[Order]:
    """List orders for one tenant."""
    if not 1 <= limit <= 100:
        raise ValueError("Limit must be between 1 and 100.")

    if offset < 0:
        raise ValueError("Offset cannot be negative.")

    require_tenant(db, tenant_id)

    stmt = (
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.tenant_id == tenant_id)
        .order_by(Order.created_at.desc(), Order.id)
        .limit(limit)
        .offset(offset)
    )

    return list(db.scalars(stmt).all())


def _same_order(existing: Order, data: OrderCreate) -> bool:
    """Compare the submitted items with existing items."""
    current = sorted(
        (item.sku, item.quantity, item.unit_price) for item in existing.items
    )

    incoming = sorted((item.sku, item.quantity, item.unit_price) for item in data.items)

    return current == incoming


def _resolve_duplicate(
    db: Session,
    tenant_id: UUID,
    data: OrderCreate,
) -> Order | None:
    existing = get_order_by_external_id(db, tenant_id, data.external_order_id)

    if existing is None:
        return None

    if not _same_order(existing, data):
        raise OrderConflictError(
            "External order ID already exists with different items."
        )

    return existing


def create_order(
    db: Session,
    tenant_id: UUID,
    data: OrderCreate,
) -> tuple[Order, bool]:
    """Create an order or return an existing identical order."""

    require_tenant(db, tenant_id, active=True)

    # Return an identical order if it already exists.
    existing = _resolve_duplicate(db, tenant_id, data)

    if existing is not None:
        return existing, False

    order = Order(
        tenant_id=tenant_id,
        external_order_id=data.external_order_id,
        items=[
            OrderItem(
                sku=item.sku,
                quantity=item.quantity,
                unit_price=item.unit_price,
            )
            for item in data.items
        ],
    )

    try:
        # This service owns the transaction. Roll back before resolving a race.
        db.add(order)
        db.flush()

        db.commit()

    except IntegrityError as exc:
        db.rollback()
        code = getattr(exc.orig, "sqlstate", None) or getattr(exc.orig, "pgcode", None)
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)

        # PostgreSQL unique constraint violation.
        if code != "23505" or constraint != "uq_orders_tenant_external_id":
            raise

        existing = _resolve_duplicate(db, tenant_id, data)

        if existing is None:
            raise

        return existing, False

    except Exception:
        db.rollback()
        raise

    return get_order(db, tenant_id, order.id), True
