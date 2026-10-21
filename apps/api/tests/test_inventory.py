from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.providers.common import Behavior
from app.providers.inventory import app, simulator
from app.providers.models import Reservation, Stock


def provider_client(engine):
    def db():
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = db
    return TestClient(app)


@pytest.fixture
def inventory(engine, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_ADMIN", "true")
    simulator.configure(Behavior(mode="normal", remaining=0))
    with provider_client(engine) as client:
        yield client
    app.dependency_overrides.clear()


def test_inventory_contract(inventory):
    c = inventory
    tenant_id = str(uuid4())
    data = {"tenant_id": tenant_id, "items": [{"sku": "A", "quantity": 4}]}
    assert (
        c.put(
            "/inventory/stock",
            json={"tenant_id": tenant_id, "sku": "A", "available": 5},
        ).status_code
        == 200
    )
    assert c.post("/inventory/check", json=data).json()["available"]
    reservation = {**data, "idempotency_key": "key-1"}
    first = c.post("/inventory/reservations", json=reservation)
    assert first.status_code == 201
    assert (
        c.post("/inventory/reservations", json=reservation).json()["id"]
        == first.json()["id"]
    )
    assert (
        c.post(
            "/inventory/reservations", json={**data, "idempotency_key": "key-2"}
        ).status_code
        == 409
    )
    assert not c.post("/inventory/check", json=data).json()["available"]
    wrong = {**reservation, "items": [{"sku": "A", "quantity": 1}]}
    assert c.post("/inventory/reservations", json=wrong).status_code == 409
    assert (
        c.get(
            f"/inventory/reservations/{first.json()['id']}?tenant_id={uuid4()}"
        ).status_code
        == 404
    )
    assert (
        c.get(f"/inventory/reservations/by-key/key-1?tenant_id={tenant_id}").status_code
        == 200
    )
    assert (
        c.post(
            "/inventory/reservations",
            json={
                **data,
                "idempotency_key": "missing",
                "items": [{"sku": "B", "quantity": 1}],
            },
        ).status_code
        == 422
    )
    assert (
        c.post(
            "/inventory/check", json={**data, "items": [{"sku": "A", "quantity": 0}]}
        ).status_code
        == 422
    )
    c.put("/demo/behavior", json={"mode": "unavailable"})
    assert (
        c.post(
            "/inventory/reservations", json={**data, "idempotency_key": "error"}
        ).status_code
        == 503
    )


def test_demo_controls_disabled(inventory, monkeypatch):
    monkeypatch.delenv("ENABLE_DEMO_ADMIN")
    assert inventory.put("/demo/behavior", json={"mode": "normal"}).status_code == 404


@pytest.mark.parametrize("duplicate", [False, True])
def test_postgres_reservation_concurrency(pg_engine, duplicate):
    tenant_id = uuid4()
    with Session(pg_engine) as db:
        db.add(Stock(tenant_id=tenant_id, sku="A", available=5))
        db.commit()
    barrier = Barrier(2)
    client = provider_client(pg_engine)

    def submit(n):
        barrier.wait(timeout=10)
        return client.post(
            "/inventory/reservations",
            json={
                "tenant_id": str(tenant_id),
                "idempotency_key": "same" if duplicate else f"key-{n}",
                "items": [{"sku": "A", "quantity": 4}],
            },
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = sorted(pool.map(submit, range(2)))
        assert statuses == ([200, 201] if duplicate else [201, 409])
        with Session(pg_engine) as db:
            assert db.get(Stock, (tenant_id, "A")).available == 1
            assert db.scalar(select(func.count()).select_from(Reservation)) == 1
    finally:
        client.close()
        app.dependency_overrides.clear()
