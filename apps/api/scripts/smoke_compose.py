"""Smoke test the actual Compose images, isolated from pytest dependency overrides."""

import json
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


for _ in range(40):
    try:
        assert call(8000, "/health/db")[0] == 200
        break
    except (URLError, ConnectionError, TimeoutError):
        time.sleep(1)
else:
    raise RuntimeError("Compose API did not become ready")

status, tenant = call(
    8000,
    "/api/v1/tenants",
    {"name": "Compose smoke retailer", "slug": "compose-" + uuid4().hex[:12]},
)
assert status == 201
call(
    8001,
    "/inventory/stock",
    {"tenant_id": tenant["id"], "sku": "COMPOSE-A", "available": 5},
    "PUT",
)
base = f"/api/v1/tenants/{tenant['id']}/orders"
payload = {
    "external_order_id": "COMPOSE-1",
    "items": [{"sku": "COMPOSE-A", "quantity": 2, "unit_price": "12.50"}],
}
status, order = call(8000, base, payload)
assert status == 201
_, execution = call(8000, base + f"/{order['id']}/process", method="POST")
deadline = time.monotonic() + 90
while execution["status"] in ("pending", "running"):
    if time.monotonic() > deadline:
        raise RuntimeError("Queued workflow did not finish")
    time.sleep(0.25)
    _, execution = call(
        8000, f"/api/v1/tenants/{tenant['id']}/executions/{execution['id']}"
    )
assert execution["status"] == "completed"
assert execution["steps"][-1]["output_summary"]["status"] == "accepted"
assert call(8000, base, payload)[0] == 200
assert (
    call(8000, base + f"/{order['id']}/process", method="POST")[1]["id"]
    == execution["id"]
)
check = call(
    8001,
    "/inventory/check",
    {"tenant_id": tenant["id"], "items": [{"sku": "COMPOSE-A", "quantity": 3}]},
)[1]
assert check["items"][0]["available"] == 3
print(
    "Compose images: persistent order, reservation, fulfillment and duplicate handling passed."
)
