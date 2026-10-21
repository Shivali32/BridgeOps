import os
import socket
import threading
import time
from contextlib import contextmanager
from uuid import uuid4

import httpx
import pytest
import uvicorn
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db import get_db
from app.main import app as api
from app.models.base import Base
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
def live(request, tmp_path, monkeypatch):
    # CI uses real PostgreSQL. SQLite here verifies HTTP behavior only.
    if os.getenv("TEST_DATABASE_URL"):
        test_engine = request.getfixturevalue("pg_engine")
    else:
        test_engine = create_engine(
            f"sqlite+pysqlite:///{tmp_path / 'http.db'}",
            connect_args={"check_same_thread": False},
        )

        @event.listens_for(test_engine, "connect")
        def foreign_keys(connection, _):
            connection.execute("PRAGMA foreign_keys=ON")

        Base.metadata.create_all(test_engine)

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
        if not os.getenv("TEST_DATABASE_URL"):
            test_engine.dispose()


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
    resolved = c.post(
        f"/api/v1/tenants/{tenant_id}/executions/{result['id']}/recovery",
        json={
            "request_key": "reconcile-http",
            "action": "reconcile",
            "note": "Check the response lost after acceptance",
        },
    ).json()
    assert resolved["status"] == "completed"
    assert resolved["steps"][-1]["output_summary"]["reconciled"] is True


def test_actual_http_three_retailer_imports(live, monkeypatch):
    c, inv, _ = live
    monkeypatch.setenv("INGEST_TOKEN", "http-test-token")
    auth = {"X-Development-Token": "http-test-token"}
    cases = [
        (
            "shopify_simulated",
            {
                "id": "SOURCE-1",
                "line_items": [{"sku": "A", "quantity": 2, "price": "12.50"}],
            },
        ),
        (
            "custom_rest",
            {
                "reference": "SOURCE-1",
                "products": [{"product_code": "A", "count": "2", "price_cents": 1250}],
            },
        ),
        (
            "csv",
            "order_reference,product_code,qty,unit_price\nSOURCE-1,A,2,12.50\nBAD-1,A,0,2.00",
        ),
    ]
    for kind, data in cases:
        tenant_id = c.post(
            "/api/v1/tenants", json={"name": kind, "slug": kind.replace("_", "-")}
        ).json()["id"]
        base = f"/api/v1/tenants/{tenant_id}"
        config = c.post(
            base + "/integrations", json={"name": "Source", "connector_type": kind}
        ).json()
        with httpx.Client(trust_env=False) as p:
            p.put(
                inv + "/inventory/stock",
                json={"tenant_id": tenant_id, "sku": "A", "available": 5},
            )
        endpoint = (
            base
            + f"/integrations/{config['id']}/"
            + ("csv" if kind == "csv" else "ingest")
        )
        response = c.post(
            endpoint, json={"csv_text": data} if kind == "csv" else data, headers=auth
        )
        assert response.status_code == 200
        record = response.json()[0] if kind == "csv" else response.json()
        if kind == "csv":
            assert response.json()[1]["status"] == "failed"
        assert record["status"] == "succeeded"
        order = c.get(base + f"/orders/{record['order_id']}").json()
        assert order["items"][0]["unit_price"] == "12.50"
        execution = c.post(base + f"/orders/{order['id']}/process").json()
        assert execution["status"] == "completed"


def test_actual_http_approval_pause_and_resume(live):
    from test_approvals import approval_definition

    c, inv, _ful = live
    tenant_id, url, _, _ = submit(c, inv)
    base = f"/api/v1/tenants/{tenant_id}"
    definition = approval_definition("500.00")
    assert c.post(base + "/workflow-definitions", json=definition).status_code == 201
    order = c.post(
        url,
        json={
            "external_order_id": "APPROVAL-1",
            "items": [{"sku": "A", "quantity": 2, "unit_price": "300.00"}],
        },
    ).json()
    result = c.post(url + f"/{order['id']}/process").json()
    assert result["status"] == "needs_attention"
    assert [s["status"] for s in result["steps"]] == ["completed", "pending"]
    with httpx.Client(trust_env=False) as p:
        assert p.post(
            inv + "/inventory/check",
            json={"tenant_id": tenant_id, "items": [{"sku": "A", "quantity": 5}]},
        ).json()["available"]
    approval = c.get(base + "/approvals?status=pending").json()[0]
    resumed = c.post(
        base + f"/approvals/{approval['id']}/decision",
        json={"decision": "approve", "note": "Reviewed locally"},
    ).json()
    assert resumed["status"] == "completed"
    assert resumed["steps"][-1]["output_summary"]["status"] == "accepted"
    again = c.post(
        base + f"/approvals/{approval['id']}/decision", json={"decision": "approve"}
    ).json()
    assert again["id"] == resumed["id"]


def test_actual_http_fulfillment_retry_preserves_reservation(live):
    c, inv, ful = live
    tenant_id, url, order, _ = submit(c, inv)
    with httpx.Client(trust_env=False) as p:
        p.put(ful + "/demo/behavior", json={"mode": "unavailable", "remaining": 1})
    failed = c.post(url + f"/{order['id']}/process").json()
    assert failed["status"] == "failed"
    reserved = failed["steps"][1]["external_reference"]
    base = f"/api/v1/tenants/{tenant_id}"
    payload = {
        "request_key": "retry-http-1",
        "action": "retry",
        "note": "Provider is available again",
    }
    recovered = c.post(base + f"/executions/{failed['id']}/recovery", json=payload)
    assert recovered.status_code == 200
    result = recovered.json()
    assert result["status"] == "completed"
    assert result["steps"][1]["external_reference"] == reserved
    assert (
        len([s for s in result["steps"] if s["step_name"] == "inventory_reservation"])
        == 1
    )
    assert (
        c.post(base + f"/executions/{failed['id']}/recovery", json=payload).json()["id"]
        == failed["id"]
    )
    with httpx.Client(trust_env=False) as p:
        check = p.post(
            inv + "/inventory/check",
            json={"tenant_id": tenant_id, "items": [{"sku": "A", "quantity": 3}]},
        ).json()
        assert check["items"][0]["available"] == 3
    assert c.get(base + "/operations/summary").json()["retry_requests"] == 1
    assert len(c.get(base + f"/executions/{failed['id']}/audit").json()) >= 1
