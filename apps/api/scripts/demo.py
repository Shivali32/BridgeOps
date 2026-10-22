"""Create repeatable three-retailer demo data without resetting existing records."""

import json
import os
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, Request, build_opener

from dotenv import load_dotenv

project_root = next(
    (
        parent
        for parent in Path(__file__).resolve().parents
        if (parent / ".env.example").is_file()
    ),
    None,
)
if project_root is not None:
    load_dotenv(project_root / ".env")
api = os.getenv("DEMO_API_URL", "http://127.0.0.1:8000")
inventory = os.getenv("INVENTORY_URL", "http://127.0.0.1:8001")
token = os.getenv("INGEST_TOKEN")
if not token:
    raise RuntimeError(
        "Set INGEST_TOKEN in the repository .env before seeding the demo."
    )
opener = build_opener(ProxyHandler({}))


def call(base, path, data=None, method=None, *, authenticated=False):
    headers = {"Content-Type": "application/json"}
    if authenticated:
        headers["X-Development-Token"] = token
    request = Request(
        base + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers=headers,
        method=method,
    )
    try:
        with opener.open(request, timeout=30) as response:
            return json.load(response)
    except HTTPError as exc:
        raise RuntimeError(
            f"Demo request {path} returned HTTP {exc.code}. Check service configuration."
        ) from None


def retailer(letter):
    values = call(api, "/api/v1/tenants?limit=100")
    slug = "demo-retailer-" + letter.lower()
    existing = next((v for v in values if v["slug"] == slug), None)
    value = existing or call(
        api, "/api/v1/tenants", {"name": "Demo Retailer " + letter, "slug": slug}
    )
    if not value["is_active"]:
        raise RuntimeError(
            f"Demo retailer {letter} is inactive. Review it before seeding."
        )
    sku = "DEMO-" + letter
    stock = call(
        inventory,
        "/inventory/check",
        {"tenant_id": value["id"], "items": [{"sku": sku, "quantity": 1}]},
    )
    if stock["items"][0]["available"] is None:
        call(
            inventory,
            "/inventory/stock",
            {"tenant_id": value["id"], "sku": sku, "available": 20},
            "PUT",
        )
    return value["id"], sku


for letter, connector_type in (
    ("A", "shopify_simulated"),
    ("B", "custom_rest"),
    ("C", "csv"),
):
    tenant_id, sku = retailer(letter)
    base = f"/api/v1/tenants/{tenant_id}"
    workflow_id = None
    if letter == "B":
        workflows = call(api, base + "/workflow-definitions?limit=100")
        workflow = next(
            (v for v in workflows if v["name"] == "Demo high-value approval"), None
        )
        if workflow is None:
            workflow = call(
                api,
                base + "/workflow-definitions",
                {
                    "name": "Demo high-value approval",
                    "steps": [
                        {
                            "id": "value_check",
                            "type": "condition",
                            "rules": {
                                "rules": [
                                    {
                                        "field": "order_total",
                                        "operator": "greater_than",
                                        "value": "500.00",
                                    }
                                ]
                            },
                        },
                        {
                            "id": "approve",
                            "type": "approval",
                            "when": {"condition_step": "value_check"},
                            "reason": "Demo order exceeds $500",
                        },
                        *[
                            {"id": k, "type": k}
                            for k in (
                                "inventory_check",
                                "inventory_reservation",
                                "fulfillment_request",
                            )
                        ],
                    ],
                },
            )
        workflow_id = workflow["id"]
    values = call(api, base + "/integrations?limit=100")
    integration = next(
        (v for v in values if v["name"] == "Demo " + connector_type), None
    )
    if integration is None:
        integration = call(
            api,
            base + "/integrations",
            {
                "name": "Demo " + connector_type,
                "connector_type": connector_type,
                "workflow_id": workflow_id,
            },
        )
    path = base + f"/integrations/{integration['id']}"
    if letter == "A":
        records = [
            call(
                api,
                path + "/ingest",
                {
                    "id": "DEMO-A-1001",
                    "line_items": [{"sku": sku, "quantity": 2, "price": "12.50"}],
                },
                authenticated=True,
            )
        ]
    elif letter == "B":
        records = [
            call(
                api,
                path + "/ingest",
                {
                    "reference": "DEMO-B-1001",
                    "products": [
                        {"product_code": sku, "count": 2, "price_cents": 30000}
                    ],
                },
                authenticated=True,
            )
        ]
    else:
        records = call(
            api,
            path + "/csv",
            {
                "csv_text": f"order_reference,product_code,qty,unit_price\nDEMO-C-1001,{sku},1,12.50\nDEMO-C-BAD,{sku},0,2.00\nDEMO-C-1002,{sku},2,4.00"
            },
            authenticated=True,
        )
    statuses = []
    for record in records:
        if record["status"] == "failed":
            statuses.append("invalid row recorded")
            continue
        execution = call(
            api, base + f"/orders/{record['order_id']}/process", method="POST"
        )
        deadline = time.monotonic() + 90
        while execution["status"] in ("pending", "running"):
            if time.monotonic() > deadline:
                raise RuntimeError(
                    "Workflow did not finish. Check the Kafka publisher and worker."
                )
            time.sleep(0.25)
            execution = call(api, base + f"/executions/{execution['id']}")
        statuses.append(execution["status"])
    if letter == "B":
        assert statuses[0] in ("needs_attention", "completed"), (
            "Review the existing approval demo state"
        )
    else:
        assert all(s in ("completed", "invalid row recorded") for s in statuses)
    if letter == "C":
        assert statuses.count("invalid row recorded") == 1
    print(f"Retailer {letter}: {tenant_id}; " + ", ".join(statuses))
print("Open React, refresh retailer choices, and inspect Demo Retailer A, B and C.")
