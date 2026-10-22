"""Exercise the isolated Compose stack, including worker and broker interruptions.

Run from the repository root, never during another operator's demonstration.
"""

import json
import subprocess
import time
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener
from uuid import uuid4

opener = build_opener(ProxyHandler({}))


def call(port, path, data=None, method=None):
    request = Request(
        f"http://127.0.0.1:{port}{path}",
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with opener.open(request, timeout=10) as response:
        return response.status, json.load(response)


def compose(*args):
    return subprocess.run(
        ["docker", "compose", "--profile", "app", *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    ).stdout.strip()


def wait_for(check, description, timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if value := check():
                return value
        except (URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.5)
    raise RuntimeError("Timed out: " + description)


def main():
    wait_for(lambda: call(8000, "/health/db")[0] == 200, "API startup")
    _, tenant = call(
        8000,
        "/api/v1/tenants",
        {"name": "Kafka interruption checks", "slug": "kafka-" + uuid4().hex[:12]},
    )
    tenant_id = tenant["id"]
    base = f"/api/v1/tenants/{tenant_id}"
    call(
        8001,
        "/inventory/stock",
        {"tenant_id": tenant_id, "sku": "FROZEN-PEAS-16OZ", "available": 20},
        "PUT",
    )

    def submit(reference):
        _, order = call(
            8000,
            base + "/orders",
            {
                "external_order_id": reference,
                "items": [
                    {"sku": "FROZEN-PEAS-16OZ", "quantity": 2, "unit_price": "2.49"}
                ],
            },
        )
        status, execution = call(
            8000, base + f"/orders/{order['id']}/process", method="POST"
        )
        assert status == 202 and execution["status"] == "pending"
        assert (
            call(8000, base + f"/orders/{order['id']}/process", method="POST")[1]["id"]
            == execution["id"]
        )
        return execution

    def finished(execution):
        current = call(8000, base + f"/executions/{execution['id']}")[1]
        return current if current["status"] == "completed" else None

    try:
        compose("stop", "worker")
        orders = [submit(f"KAFKA-{i}") for i in range(3)]
        wait_for(
            lambda: call(8000, base + "/queue")[1]["awaiting_worker"] == 3,
            "events published while worker is stopped",
        )
        assert all(
            call(8000, base + f"/executions/{e['id']}")[1]["status"] == "pending"
            for e in orders
        )
        compose("start", "worker")
        for execution in orders:
            wait_for(
                lambda e=execution: finished(e), "worker restart drains queued orders"
            )

        # Duplicate and malformed records share a partition. Seeing the quarantine
        # proves the preceding duplicate was consumed, not merely published.
        marker = "malformed-" + uuid4().hex
        code = f"""
import hashlib, json
from uuid import UUID
from sqlalchemy import select
from app.db import SessionLocal
from app.messaging.publisher import make_producer
from app.messaging.contracts import topic
from app.models.messaging import OutboxEvent
with SessionLocal() as db:
    event = db.scalar(select(OutboxEvent).where(OutboxEvent.execution_id == UUID({orders[0]["id"]!r})))
    producer = make_producer()
    delivered = []
    def confirmed(error, message):
        delivered.append(error)
    producer.produce(topic(), partition=0, value=json.dumps(event.payload).encode(), on_delivery=confirmed)
    producer.produce(topic(), partition=0, value={marker!r}.encode(), on_delivery=confirmed)
    assert producer.flush(10) == 0
    assert len(delivered) == 2 and all(error is None for error in delivered), delivered
"""
        compose("exec", "-T", "publisher", "python", "-c", code)
        check = f"""
import hashlib
from sqlalchemy import select, func
from app.db import SessionLocal
from app.models.messaging import QuarantinedMessage
with SessionLocal() as db:
    print(db.scalar(select(func.count()).select_from(QuarantinedMessage).where(QuarantinedMessage.payload_digest == hashlib.sha256({marker!r}.encode()).hexdigest())))
"""
        wait_for(
            lambda: compose("exec", "-T", "api", "python", "-c", check) == "1",
            "malformed event saved after consuming duplicate",
        )

        compose("stop", "kafka")
        queued = submit("KAFKA-BROKER-OFFLINE")
        assert call(8000, base + "/queue")[1]["pending_publication"] >= 1
        compose("start", "kafka")
        wait_for(lambda: finished(queued), "outbox delivers after broker restart")

        available = call(
            8001,
            "/inventory/check",
            {
                "tenant_id": tenant_id,
                "items": [{"sku": "FROZEN-PEAS-16OZ", "quantity": 1}],
            },
        )[1]
        assert available["items"][0]["available"] == 12, available
        assert all(
            len(
                [
                    s
                    for s in finished(e)["steps"]
                    if s["step_name"] == "inventory_reservation"
                ]
            )
            == 1
            for e in [*orders, queued]
        )
        print(
            "Kafka verified: queued work, worker restart, broker outage, duplicate safety, malformed-message quarantine, stock reserved once."
        )
    finally:
        compose("start", "kafka", "worker")


if __name__ == "__main__":
    main()
