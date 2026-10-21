from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.providers.common import Behavior
from app.providers.fulfillment import app, simulator
from app.providers.models import FulfillmentRequest


def provider_client(engine):
    def db():
        with Session(engine, expire_on_commit=False) as session:
            yield session

    app.dependency_overrides[get_db] = db
    return TestClient(app)


def payload():
    return {
        "tenant_id": str(uuid4()),
        "order_id": str(uuid4()),
        "reservation_id": str(uuid4()),
        "idempotency_key": "key",
        "items": [{"sku": "A", "quantity": 2}],
    }


@pytest.fixture
def fulfillment(engine, monkeypatch):
    monkeypatch.setenv("ENABLE_DEMO_ADMIN", "true")
    simulator.configure(Behavior(mode="normal", remaining=0))
    with provider_client(engine) as client:
        yield client
    app.dependency_overrides.clear()


def test_fulfillment_contract(fulfillment):
    c = fulfillment
    data = payload()
    url = "/fulfillment/requests"
    result = c.post(url, json=data)
    assert result.status_code == 201 and result.json()["status"] == "accepted"
    assert c.post(url, json=data).json()["id"] == result.json()["id"]
    assert c.post(url, json={**data, "order_id": str(uuid4())}).status_code == 409
    assert (
        c.get(f"{url}/{result.json()['id']}?tenant_id={data['tenant_id']}").status_code
        == 200
    )
    assert c.get(f"{url}/{result.json()['id']}?tenant_id={uuid4()}").status_code == 404
    assert c.post(url, json={}).status_code == 422
    c.put("/demo/behavior", json={"mode": "unavailable"})
    assert c.post(url, json=payload()).status_code == 503


@pytest.mark.parametrize("conflict", [False, True])
def test_postgres_fulfillment_concurrency(pg_engine, conflict):
    c = provider_client(pg_engine)
    data = payload()
    barrier = Barrier(2)

    def submit(n):
        barrier.wait(timeout=10)
        return c.post(
            "/fulfillment/requests",
            json={**data, "order_id": str(uuid4())} if conflict and n else data,
        ).status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = sorted(pool.map(submit, range(2)))
        assert result == ([201, 409] if conflict else [200, 201])
        with Session(pg_engine) as db:
            assert db.scalar(select(func.count()).select_from(FulfillmentRequest)) == 1
    finally:
        c.close()
        app.dependency_overrides.clear()
