"""Shared fixture builders for service tests."""

from uuid import uuid4

from app.models import Tenant
from app.schemas.order import OrderCreate
from app.services.order import create_order


def make_order(db, price="12.50", quantity=2):
    tenant = Tenant(name="Demo retailer", slug="demo-" + uuid4().hex[:12])
    db.add(tenant)
    db.commit()
    order, _ = create_order(
        db,
        tenant.id,
        OrderCreate(
            external_order_id="WEB-1",
            items=[{"sku": "A", "quantity": quantity, "unit_price": price}],
        ),
    )
    return tenant, order
