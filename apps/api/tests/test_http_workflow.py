import os
import socket
import threading
import time
from contextlib import contextmanager
from uuid import uuid4

import httpx
import pytest
import uvicorn
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app as api
from app.providers.common import Behavior
from app.providers.fulfillment import app as fulfillment
from app.providers.fulfillment import simulator as fulfillment_simulator
from app.providers.inventory import app as inventory
from app.providers.inventory import simulator as inventory_simulator


@contextmanager
def serve(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    sock.listen(64)
    server = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    thread = threading.Thread(
        target=server.run, kwargs={"sockets": [sock]}, daemon=True
    )
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert server.started, "HTTP server failed to start"
    try:
        yield f"http://127.0.0.1:{sock.getsockname()[1]}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        assert not thread.is_alive()


@pytest.fixture
def live(request, engine, monkeypatch):
    # CI uses real PostgreSQL. SQLite here verifies HTTP behavior only.
    test_engine = (
        request.getfixturevalue("pg_engine")
        if os.getenv("TEST_DATABASE_URL")
        else engine
    )

    def db():
        with Session(test_engine, expire_on_commit=False) as session:
            yield session

    monkeypatch.setenv("ENABLE_DEMO_ADMIN", "true")
    fulfillment_simulator.configure(Behavior(mode="normal", remaining=0))
    inventory_simulator.configure(Behavior(mode="normal", remaining=0))
    for app in (api, inventory, fulfillment):
        app.dependency_overrides[get_db] = db
    try:
        with serve(inventory) as inv, serve(fulfillment) as ful:
            monkeypatch.setenv("INVENTORY_URL", inv)
            monkeypatch.setenv("FULFILLMENT_URL", ful)
            with (
                serve(api) as base,
                httpx.Client(base_url=base, trust_env=False, timeout=10) as client,
            ):
                yield client, inv, ful
    finally:
        for app in (api, inventory, fulfillment):
            app.dependency_overrides.clear()


def submit(client, inv, external="HTTP-1"):
    tenant_id = client.post(
        "/api/v1/tenants",
        json={"name": "HTTP retailer", "slug": "http-" + uuid4().hex[:12]},
    ).json()["id"]
    with httpx.Client(trust_env=False) as provider:
        assert provider.put(
            inv + "/inventory/stock",
            json={"tenant_id": tenant_id, "sku": "A", "available": 5},
        ).is_success
    url = f"/api/v1/tenants/{tenant_id}/orders"
    data = {"external_order_id": external, "items": [{"sku": "A", "quantity": 2}]}
    response = client.post(url, json=data)
    assert response.status_code == 201
    return tenant_id, url, response.json(), data


def test_actual_http_order_workflow(live):
    c, inv, ful = live
    tenant_id, url, order, data = submit(c, inv)
    process_url = f"{url}/{order['id']}/process"
    result = c.post(process_url).json()
    assert result["status"] == "completed"
    assert len(result["steps"]) == 3
    assert result["steps"][-1]["output_summary"]["status"] == "accepted"
    assert c.post(process_url).json()["id"] == result["id"]
    assert c.post(url, json=data).status_code == 200
    with httpx.Client(trust_env=False) as p:
        assert (
            p.post(
                inv + "/inventory/check",
                json={"tenant_id": tenant_id, "items": [{"sku": "A", "quantity": 4}]},
            ).json()["available"]
            is False
        )
        ref = result["steps"][-1]["external_reference"]
        assert (
            p.get(
                ful + f"/fulfillment/requests/{ref}", params={"tenant_id": tenant_id}
            ).json()["status"]
            == "accepted"
        )
    assert (
        c.get(f"/api/v1/tenants/{uuid4()}/executions/{result['id']}").status_code == 404
    )


def test_actual_http_timeout_after_provider_commit(live, monkeypatch):
    c, inv, ful = live
    tenant_id, url, order, _ = submit(c, inv)
    monkeypatch.setenv("PROVIDER_TIMEOUT_SECONDS", "0.1")
    with httpx.Client(trust_env=False) as p:
        p.put(
            ful + "/demo/behavior", json={"mode": "delay_after", "delay_seconds": 0.3}
        )
    result = c.post(f"{url}/{order['id']}/process").json()
    assert result["status"] == "needs_attention"
    assert result["steps"][-1]["status"] == "unknown"
    key = result["steps"][-1]["idempotency_key"]
    with httpx.Client(trust_env=False) as p:
        assert (
            p.get(
                ful + f"/fulfillment/requests/by-key/{key}",
                params={"tenant_id": tenant_id},
            ).json()["status"]
            == "accepted"
        )
    assert c.post(f"{url}/{order['id']}/process").json()["id"] == result["id"]
