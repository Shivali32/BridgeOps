from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Order, OrderItem, Tenant
from app.schemas.order import OrderCreate
from app.services.order import (
    InactiveTenantError,
    OrderConflictError,
    OrderNotFoundError,
    TenantNotFoundError,
    create_order,
    get_order,
    list_orders,
)


def payload(external_id="WEB-1", quantity=2):
    return OrderCreate.model_validate(
        {
            "external_order_id": external_id,
            "items": [
                {"sku": "RICE-5KG", "quantity": quantity, "unit_price": "12.50"},
                {"sku": "MILK-1L", "quantity": 1},
            ],
        }
    )


def tenant(db, slug="retailer-a", active=True):
    value = Tenant(name=slug, slug=slug, is_active=active)
    db.add(value)
    db.commit()
    return value


def test_creation_and_normalized_duplicate(session):
    t = tenant(session)
    order, created = create_order(session, t.id, payload())
    assert created and order.status == "received" and len(order.items) == 2
    normalized = payload(" WEB-1 ")
    normalized.items.reverse()
    again, created = create_order(session, t.id, normalized)
    assert not created and again.id == order.id
    with pytest.raises(OrderConflictError):
        create_order(session, t.id, payload(quantity=3))
    assert session.scalar(select(func.count()).select_from(Order)) == 1
    assert session.scalar(select(func.count()).select_from(OrderItem)) == 2


def test_missing_and_inactive_tenants(session):
    with pytest.raises(TenantNotFoundError):
        create_order(session, uuid4(), payload())
    t = tenant(session, active=False)
    with pytest.raises(InactiveTenantError):
        create_order(session, t.id, payload())


def test_tenant_scoping_and_pagination(session):
    a, b = tenant(session), tenant(session, "retailer-b")
    first, _ = create_order(session, a.id, payload())
    other, _ = create_order(session, b.id, payload())
    create_order(session, a.id, payload("WEB-2"))
    assert first.id != other.id
    assert get_order(session, a.id, first.id).id == first.id
    with pytest.raises(OrderNotFoundError):
        get_order(session, b.id, first.id)
    assert len(list_orders(session, a.id)) == 2
    assert len(list_orders(session, a.id, 1, 1)) == 1
    assert list_orders(session, a.id, 1, 100) == []
    with pytest.raises(TenantNotFoundError):
        list_orders(session, uuid4())


@pytest.mark.parametrize("limit,offset", [(0, 0), (101, 0), (5, -1)])
def test_invalid_pagination(session, limit, offset):
    t = tenant(session)
    with pytest.raises(ValueError):
        list_orders(session, t.id, limit, offset)


def test_transaction_failure_does_not_persist_partial_order(session):
    t = tenant(session)
    with (
        patch.object(session, "commit", side_effect=RuntimeError("disk unavailable")),
        pytest.raises(RuntimeError),
    ):
        create_order(session, t.id, payload())
    assert session.scalar(select(func.count()).select_from(Order)) == 0
    assert session.scalar(select(func.count()).select_from(OrderItem)) == 0
    assert create_order(session, t.id, payload())[1]


def test_api_contract(api_client):
    c = api_client
    a = c.post("/api/v1/tenants", json={"name": "A", "slug": "a"}).json()["id"]
    b = c.post("/api/v1/tenants", json={"name": "B", "slug": "b"}).json()["id"]
    url = f"/api/v1/tenants/{a}/orders"
    data = payload().model_dump(mode="json")
    response = c.post(url, json=data)
    assert response.status_code == 201
    order = response.json()
    assert len(order["items"]) == 2
    assert c.post(url, json=data).status_code == 200
    assert (
        c.post(url, json=payload(quantity=3).model_dump(mode="json")).status_code == 409
    )
    assert c.post(url, json={"items": []}).status_code == 422
    assert c.get(url + f"/{order['id']}").json()["id"] == order["id"]
    assert c.get(f"/api/v1/tenants/{b}/orders/{order['id']}").status_code == 404
    assert c.get(url + f"/{uuid4()}").status_code == 404
    assert len(c.get(url + "?limit=1&offset=0").json()) == 1
    assert c.get(url + "?offset=-1").status_code == 422
    assert c.get(f"/api/v1/tenants/{uuid4()}/orders").status_code == 404
    c.delete(f"/api/v1/tenants/{a}")
    assert c.post(url, json=data).status_code == 409


@pytest.mark.parametrize("conflicting", [False, True])
def test_postgres_concurrent_order_submission(pg_engine, conflicting):
    with Session(pg_engine) as db:
        t = tenant(db)
        tenant_id = t.id
    barrier = Barrier(2)

    def submit(n):
        with Session(pg_engine, expire_on_commit=False) as db:
            barrier.wait(timeout=10)
            try:
                order, created = create_order(
                    db, tenant_id, payload(quantity=2 + n if conflicting else 2)
                )
                return str(order.id), created
            except OrderConflictError:
                return "conflict", False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert sum(created for _, created in results) == 1
    if conflicting:
        assert sum(value == "conflict" for value, _ in results) == 1
    else:
        assert results[0][0] == results[1][0]
    with Session(pg_engine) as db:
        assert db.scalar(select(func.count()).select_from(Order)) == 1
        assert db.scalar(select(func.count()).select_from(OrderItem)) == 2
