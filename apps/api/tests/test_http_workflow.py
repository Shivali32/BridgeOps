import os
import socket
import subprocess
import sys
import threading
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
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


@pytest.mark.parametrize("resolution", ["reconcile", "verify_reference"])
def test_actual_http_timeout_after_provider_commit(live, monkeypatch, resolution):
    c, inv, ful = live
    tenant_id, url, order, _ = submit(c, inv)
    monkeypatch.setenv("PROVIDER_TIMEOUT_SECONDS", "0.2")
    with httpx.Client(trust_env=False) as p:
        p.put(
            ful + "/demo/behavior", json={"mode": "delay_after", "delay_seconds": 0.6}
        )
    result = c.post(f"{url}/{order['id']}/process").json()
    assert result["status"] == "needs_attention"
    assert result["steps"][-1]["status"] == "unknown"
    key = result["steps"][-1]["idempotency_key"]
    # The low timeout only induces the lost-response scenario. Reconciliation
    # uses the normal production timeout so CI scheduling does not cause noise.
    monkeypatch.setenv("PROVIDER_TIMEOUT_SECONDS", "3")
    with httpx.Client(trust_env=False) as p:
        provider_record = p.get(
            ful + f"/fulfillment/requests/by-key/{key}", params={"tenant_id": tenant_id}
        ).json()
        assert provider_record["status"] == "accepted"
    assert c.post(f"{url}/{order['id']}/process").json()["id"] == result["id"]
    resolved = c.post(
        f"/api/v1/tenants/{tenant_id}/executions/{result['id']}/recovery",
        json={
            "request_key": "reconcile-http",
            "action": resolution,
            "external_reference": provider_record["id"]
            if resolution == "verify_reference"
            else None,
            "note": "Check the response lost after acceptance",
        },
    ).json()
    assert resolved["status"] == "completed", resolved
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


def run_grocery_seed(client, inventory, fulfillment, *args):
    environment = {
        **os.environ,
        "DEMO_API_URL": str(client.base_url),
        "INVENTORY_URL": inventory,
        "FULFILLMENT_URL": fulfillment,
    }
    result = subprocess.run(
        [sys.executable, "scripts/grocery_demo.py", *args],
        check=False,
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_actual_http_five_grocery_stores_repeat_and_present(live, monkeypatch):
    """Run the delivered CLI, present its live actions, then seed again safely."""
    c, inv, ful = live
    monkeypatch.setenv("INGEST_TOKEN", "grocery-local-token")
    output = run_grocery_seed(c, inv, ful)
    assert "5 grocery stores, 15 valid orders and 1 invalid import" in output
    tenants = c.get("/api/v1/tenants").json()
    assert len(tenants) == 5
    stores = {t["slug"]: f"/api/v1/tenants/{t['id']}" for t in tenants}

    def snapshot():
        result = {}
        for tenant in tenants:
            base = stores[tenant["slug"]]
            orders = c.get(base + "/orders").json()
            assert len(orders) == 3
            assert len(c.get(base + "/integrations").json()) == 1
            assert len(c.get(base + "/workflow-definitions").json()) == 1
            for order in orders:
                executions = c.get(base + f"/orders/{order['id']}/executions").json()
                assert len(executions) <= 1
                result[order["external_order_id"]] = (
                    order["id"],
                    order["status"],
                    [e["id"] for e in executions],
                )
            result[tenant["slug"] + "-imports"] = [
                r["id"] for r in c.get(base + "/imports").json()
            ]
            skus = sorted({item["sku"] for order in orders for item in order["items"]})
            with httpx.Client(trust_env=False) as provider:
                result[tenant["slug"] + "-stock"] = provider.post(
                    inv + "/inventory/check",
                    json={
                        "tenant_id": tenant["id"],
                        "items": [{"sku": s, "quantity": 1} for s in skus],
                    },
                ).json()
        return result

    before = snapshot()
    statuses = Counter(
        before[ref][1]
        for ref in before
        if ref[:3] in ("MW-", "CG-", "OL-", "HF-", "SN-")
    )
    assert statuses == {
        "completed": 12,
        "needs_attention": 1,
        "failed": 1,
        "received": 1,
    }
    run_grocery_seed(c, inv, ful)
    assert snapshot() == before  # No duplicate orders/imports/runs or stock resets.

    # Invalid CSV stays visible, with a real grocery SKU and its source row.
    orchard = stores["orchard-lane-produce"]
    records = c.get(orchard + "/imports").json()
    invalid = next(r for r in records if r["source_reference"] == "OL-3004")
    assert invalid["status"] == "failed" and invalid["order_id"] is None
    assert invalid["row_numbers"] == [8]

    cedar = stores["cedar-grove-grocers"]
    approval = c.get(cedar + "/approvals?status=pending").json()[0]
    pending = c.get(cedar + f"/executions/{approval['execution_id']}").json()
    assert [s["step_name"] for s in pending["steps"]] == [
        "large_basket",
        "manager_approval",
    ]
    assert (
        c.post(
            cedar + f"/approvals/{approval['id']}/decision",
            json={"decision": "approve", "note": "Bulk grocery basket reviewed"},
        ).json()["status"]
        == "completed"
    )

    harbor = stores["harbor-fresh-foods"]
    run_grocery_seed(c, inv, ful, "--restock-harbor")
    recovered = c.post(
        harbor + f"/executions/{before['HF-4003'][2][0]}/recovery",
        json={
            "request_key": "salmon-restocked",
            "action": "retry",
            "note": "Received fresh salmon stock",
        },
    ).json()
    assert recovered["status"] == "completed"
    assert (
        sum(s["step_name"] == "inventory_reservation" for s in recovered["steps"]) == 1
    )

    sunrise = stores["sunrise-neighborhood-pantry"]
    assert (
        c.post(sunrise + f"/orders/{before['SN-5003'][0]}/process").json()["status"]
        == "completed"
    )
    after_presenting = snapshot()
    run_grocery_seed(c, inv, ful)
    assert snapshot() == after_presenting  # Presenter decisions are not undone.


def test_grocery_seed_preserves_edited_integration(live, monkeypatch):
    from scripts.grocery_demo import STORES, GroceryDemo

    c, inv, ful = live
    monkeypatch.setenv("INGEST_TOKEN", "grocery-local-token")
    demo = GroceryDemo(str(c.base_url), inv, ful, "grocery-local-token")
    tenant = demo.seed_store(STORES[0])
    base = f"/api/v1/tenants/{tenant['id']}"
    integration = c.get(base + "/integrations").json()[0]
    data = {
        key: integration[key]
        for key in ("name", "connector_type", "workflow_id", "mapping")
    }
    data.update(enabled=False, expected_version=integration["version"])
    assert (
        c.patch(base + f"/integrations/{integration['id']}", json=data).status_code
        == 200
    )
    with pytest.raises(RuntimeError, match="was edited"):
        demo.seed_store(STORES[0])
    assert c.get(base + "/integrations").json()[0]["enabled"] is False


def test_queued_http_worker_and_recovery_preserve_stock(live, monkeypatch):
    import json

    from sqlalchemy import select

    from app.messaging.worker import handle_message
    from app.models.messaging import EventReceipt, OutboxEvent

    c, inv, ful = live
    monkeypatch.setenv("WORKFLOW_MODE", "kafka")
    tenant_id, url, order, _ = submit(c, inv)
    with httpx.Client(trust_env=False) as provider:
        provider.put(
            ful + "/demo/behavior", json={"mode": "unavailable", "remaining": 1}
        )
    response = c.post(url + f"/{order['id']}/process")
    assert response.status_code == 202 and response.json()["status"] == "pending"
    with contextmanager(api.dependency_overrides[get_db])() as db:
        event = db.scalar(select(OutboxEvent))
        raw = json.dumps(event.payload).encode()
        assert handle_message(db, raw, ("work", 0, 0))
        assert db.get(EventReceipt, event.id)
    execution_id = response.json()["id"]
    base = f"/api/v1/tenants/{tenant_id}"
    assert c.get(base + f"/executions/{execution_id}").json()["status"] == "failed"
    recovered = c.post(
        base + f"/executions/{execution_id}/recovery",
        json={
            "request_key": "queued-retry",
            "action": "retry",
            "note": "Fulfillment restored",
        },
    )
    assert recovered.status_code == 202
    with contextmanager(api.dependency_overrides[get_db])() as db:
        event = db.scalar(
            select(OutboxEvent).where(
                ~OutboxEvent.id.in_(select(EventReceipt.event_id))
            )
        )
        raw = json.dumps(event.payload).encode()
        assert handle_message(db, raw, ("work", 0, 1))
        assert handle_message(db, raw, ("work", 0, 2))
    result = c.get(base + f"/executions/{execution_id}").json()
    assert result["status"] == "completed"
    assert (
        len([s for s in result["steps"] if s["step_name"] == "inventory_reservation"])
        == 1
    )
    with httpx.Client(trust_env=False) as provider:
        available = provider.post(
            inv + "/inventory/check",
            json={"tenant_id": tenant_id, "items": [{"sku": "A", "quantity": 1}]},
        ).json()
        assert available["items"][0]["available"] == 3


def test_worker_crash_after_real_fulfillment_acceptance_is_reconciled(
    live, monkeypatch
):
    import json
    from datetime import timedelta

    from sqlalchemy import select

    from app.messaging.worker import handle_message
    from app.models import WorkflowExecution
    from app.models.messaging import OutboxEvent
    from app.services.providers import Providers
    from app.services.workflow import now

    c, inv, _ = live
    monkeypatch.setenv("WORKFLOW_MODE", "kafka")
    tenant_id, url, order, _ = submit(c, inv)
    response = c.post(url + f"/{order['id']}/process").json()

    class InterruptedWorker(Providers):
        def call(self, step, payload):
            result = super().call(step, payload)
            if step == "fulfillment_request":
                raise SystemExit("Worker stopped after provider accepted the request")
            return result

    with contextmanager(api.dependency_overrides[get_db])() as db:
        event = db.scalar(select(OutboxEvent))
        raw = json.dumps(event.payload).encode()
        with pytest.raises(SystemExit):
            handle_message(db, raw, ("work", 0, 0), InterruptedWorker())
        db.rollback()
        execution = db.scalar(select(WorkflowExecution))
        assert execution.status == "running"
        execution.heartbeat_at = now() - timedelta(seconds=61)
        db.commit()
    with contextmanager(api.dependency_overrides[get_db])() as db:
        assert handle_message(db, raw, ("work", 0, 0))
    result = c.get(f"/api/v1/tenants/{tenant_id}/executions/{response['id']}").json()
    assert result["status"] == "completed"
    assert len(result["steps"]) == 3
    assert result["steps"][-1]["output_summary"]["reconciled"] is True
    with httpx.Client(trust_env=False) as provider:
        available = provider.post(
            inv + "/inventory/check",
            json={"tenant_id": tenant_id, "items": [{"sku": "A", "quantity": 1}]},
        ).json()
        assert available["items"][0]["available"] == 3
