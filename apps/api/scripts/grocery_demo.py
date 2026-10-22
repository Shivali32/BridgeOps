"""Seed five grocery stores through the running APIs without resetting their data."""

import argparse
import csv
import io
import json
import os
from decimal import Decimal
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from dotenv import load_dotenv


def order(reference, *items, process=True):
    return {"reference": reference, "items": items, "process": process}


# Items are (readable product code, number of packs, USD price per pack).
STORES = [
    {
        "name": "Maplewood Fresh Market",
        "slug": "maplewood-fresh-market",
        "connector": "shopify_simulated",
        "integration": "Online grocery orders",
        "orders": [
            order(
                "MW-1001",
                ("FRESH-STRAWBERRIES-1LB", 2, "4.99"),
                ("WHOLE-MILK-1GAL", 1, "4.29"),
                ("SOURDOUGH-LOAF", 1, "5.49"),
            ),
            order(
                "MW-1002",
                ("AVOCADOS-4PACK", 1, "3.99"),
                ("CAGE-FREE-EGGS-12CT", 2, "4.79"),
            ),
            order(
                "MW-1003",
                ("FROZEN-PEAS-16OZ", 2, "2.49"),
                ("GREEK-YOGURT-32OZ", 1, "5.99"),
            ),
        ],
    },
    {
        "name": "Cedar Grove Grocers",
        "slug": "cedar-grove-grocers",
        "connector": "custom_rest",
        "integration": "Store checkout orders",
        "approval": "150.00",
        "orders": [
            order(
                "CG-2001",
                ("BASMATI-RICE-10LB", 1, "18.99"),
                ("RED-LENTILS-2LB", 2, "4.49"),
            ),
            order(
                "CG-2002",
                ("OLIVE-OIL-1L", 1, "12.99"),
                ("CANNED-TOMATOES-28OZ", 3, "2.79"),
            ),
            order(
                "CG-2003",
                ("BASMATI-RICE-10LB", 8, "18.99"),
                ("SUNFLOWER-OIL-1GAL", 4, "13.99"),
            ),
        ],
    },
    {
        "name": "Orchard Lane Produce",
        "slug": "orchard-lane-produce",
        "connector": "csv",
        "integration": "Daily produce spreadsheet",
        "invalid_reference": "OL-3004",
        "orders": [
            order(
                "OL-3001", ("GALA-APPLES-3LB", 2, "4.49"), ("BANANAS-2LB", 1, "1.49")
            ),
            order(
                "OL-3002",
                ("ROMA-TOMATOES-1LB", 3, "1.99"),
                ("BABY-SPINACH-5OZ", 2, "2.99"),
            ),
            order(
                "OL-3003", ("CARROTS-2LB", 2, "2.49"), ("YELLOW-ONIONS-3LB", 1, "2.99")
            ),
        ],
    },
    {
        "name": "Harbor Fresh Foods",
        "slug": "harbor-fresh-foods",
        "connector": "shopify_simulated",
        "integration": "Fresh and frozen online orders",
        "shortage_sku": "FRESH-SALMON-1LB",
        "orders": [
            order(
                "HF-4001",
                ("FROZEN-SHRIMP-1LB", 2, "9.99"),
                ("FROZEN-BROCCOLI-16OZ", 2, "2.79"),
            ),
            order(
                "HF-4002",
                ("FROZEN-TILAPIA-2LB", 1, "11.99"),
                ("FROZEN-MANGO-16OZ", 2, "3.49"),
            ),
            order(
                "HF-4003",
                ("FRESH-SALMON-1LB", 4, "12.99"),
                ("FROZEN-GREEN-BEANS-16OZ", 1, "2.49"),
            ),
        ],
    },
    {
        "name": "Sunrise Neighborhood Pantry",
        "slug": "sunrise-neighborhood-pantry",
        "connector": "custom_rest",
        "integration": "Neighborhood pickup orders",
        "orders": [
            order(
                "SN-5001",
                ("WHOLE-WHEAT-BREAD-LOAF", 1, "3.49"),
                ("PEANUT-BUTTER-16OZ", 1, "2.99"),
            ),
            order(
                "SN-5002",
                ("ROLLED-OATS-42OZ", 1, "4.49"),
                ("WHOLE-MILK-1GAL", 1, "4.29"),
            ),
            order(
                "SN-5003",
                ("CAGE-FREE-EGGS-12CT", 1, "4.79"),
                ("CHEDDAR-CHEESE-8OZ", 2, "2.99"),
                process=False,
            ),
        ],
    },
]


class GroceryDemo:
    def __init__(self, api, inventory, fulfillment, token):
        if not token:
            raise RuntimeError("Set INGEST_TOKEN in your repository .env first.")
        self.api = api.rstrip("/")
        self.inventory = inventory.rstrip("/")
        self.fulfillment = fulfillment.rstrip("/")
        self.token = token
        self.opener = build_opener(ProxyHandler({}))

    def call(self, path, data=None, *, base=None, method=None, authenticated=False):
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["X-Development-Token"] = self.token
        request = Request(
            (base or self.api) + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers=headers,
            method=method,
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            raise RuntimeError(
                f"{path}: HTTP {exc.code}. Check INGEST_TOKEN, service settings, "
                "and ENABLE_DEMO_ADMIN=true on the inventory service."
            ) from None
        except (URLError, TimeoutError):
            raise RuntimeError(
                f"Cannot reach {(base or self.api)}{path}. "
                "Start the API, inventory and fulfillment services first."
            ) from None

    def listing(self, path):
        values = []
        while True:
            page = self.call(f"{path}?limit=100&offset={len(values)}")
            values.extend(page)
            if len(page) < 100:
                return values

    def tenant(self, store):
        found = next(
            (t for t in self.listing("/api/v1/tenants") if t["slug"] == store["slug"]),
            None,
        )
        tenant = found or self.call(
            "/api/v1/tenants", {"name": store["name"], "slug": store["slug"]}
        )
        if not tenant["is_active"] or tenant["name"] != store["name"]:
            raise RuntimeError(
                f"Review the existing retailer {store['slug']}; it was left unchanged."
            )
        return tenant

    def workflow(self, base, store):
        steps = [
            {"id": step, "type": step}
            for step in (
                "inventory_check",
                "inventory_reservation",
                "fulfillment_request",
            )
        ]
        if store.get("approval"):
            steps = [
                {
                    "id": "large_basket",
                    "type": "condition",
                    "rules": {
                        "rules": [
                            {
                                "field": "order_total",
                                "operator": "greater_than",
                                "value": store["approval"],
                            }
                        ]
                    },
                },
                {
                    "id": "manager_approval",
                    "type": "approval",
                    "when": {"condition_step": "large_basket"},
                    "reason": "Grocery order exceeds $150. Manager approval required.",
                },
                *steps,
            ]
        name = store["name"] + " order handling"
        expected = {"name": name, "steps": steps, "enabled": True, "is_default": False}
        found = next(
            (
                w
                for w in self.listing(base + "/workflow-definitions")
                if w["name"] == name
            ),
            None,
        )
        if found:
            # Compare using the server schema's defaults without importing the app/database.
            config = found["configuration"]
            expanded = [
                {
                    "rules": None,
                    "when": None,
                    "reason": "Operator approval required",
                    **s,
                }
                for s in steps
            ]
            for step in expanded:
                if step["rules"]:
                    step["rules"] = {"match": "all", **step["rules"]}
                if step["when"]:
                    step["when"] = {"matches": True, **step["when"]}
            if not found["enabled"] or config["steps"] != expanded:
                raise RuntimeError(
                    f"Workflow '{name}' was edited. Review it before reseeding; no settings were overwritten."
                )
            return found
        return self.call(base + "/workflow-definitions", expected)

    def integration(self, base, store, workflow):
        expected = {
            "name": store["integration"],
            "connector_type": store["connector"],
            "workflow_id": workflow["id"],
        }
        found = next(
            (
                i
                for i in self.listing(base + "/integrations")
                if i["name"] == expected["name"]
            ),
            None,
        )
        if found:
            defaults = next(
                c["default_mapping"]
                for c in self.call(base + "/connectors")
                if c["type"] == store["connector"]
            )
            if (
                any(found[k] != v for k, v in expected.items())
                or not found["enabled"]
                or found["mapping"] != defaults
            ):
                raise RuntimeError(
                    f"Integration '{expected['name']}' was edited. Review it before reseeding; no settings were overwritten."
                )
            return found
        return self.call(base + "/integrations", expected)

    def stock(self, tenant_id, sku):
        return self.call(
            "/inventory/check",
            {"tenant_id": tenant_id, "items": [{"sku": sku, "quantity": 1}]},
            base=self.inventory,
        )["items"][0]["available"]

    def set_stock(self, tenant_id, sku, available):
        self.call(
            "/inventory/stock",
            {"tenant_id": tenant_id, "sku": sku, "available": available},
            base=self.inventory,
            method="PUT",
        )

    def initialize_stock(self, tenant_id, store):
        skus = {sku for spec in store["orders"] for sku, _, _ in spec["items"]}
        for sku in sorted(skus):
            if self.stock(tenant_id, sku) is None:
                self.set_stock(
                    tenant_id, sku, 1 if sku == store.get("shortage_sku") else 60
                )

    def ingest(self, base, integration, specs, invalid_reference=None):
        path = base + f"/integrations/{integration['id']}"
        if integration["connector_type"] == "csv":
            output = io.StringIO(newline="")
            writer = csv.writer(output)
            writer.writerow(["order_reference", "product_code", "qty", "unit_price"])
            for spec in specs:
                for sku, quantity, price in spec["items"]:
                    writer.writerow([spec["reference"], sku, quantity, price])
            if invalid_reference:
                writer.writerow([invalid_reference, "BANANAS-2LB", 0, "1.49"])
            return self.call(
                path + "/csv", {"csv_text": output.getvalue()}, authenticated=True
            )
        results = []
        for spec in specs:
            if integration["connector_type"] == "shopify_simulated":
                payload = {
                    "id": spec["reference"],
                    "line_items": [
                        {"sku": s, "quantity": q, "price": p}
                        for s, q, p in spec["items"]
                    ],
                }
            else:
                payload = {
                    "reference": spec["reference"],
                    "products": [
                        {
                            "product_code": s,
                            "count": q,
                            "price_cents": int(Decimal(p) * 100),
                        }
                        for s, q, p in spec["items"]
                    ],
                }
            results.append(self.call(path + "/ingest", payload, authenticated=True))
        return results

    def seed_store(self, store):
        tenant = self.tenant(store)
        base = f"/api/v1/tenants/{tenant['id']}"
        workflow = self.workflow(base, store)
        integration = self.integration(base, store, workflow)
        self.initialize_stock(tenant["id"], store)
        records = [
            r
            for r in self.listing(base + "/imports")
            if r["integration_id"] == integration["id"]
        ]
        existing = {
            r["source_reference"]: r for r in records if r["status"] == "succeeded"
        }
        missing = [s for s in store["orders"] if s["reference"] not in existing]
        invalid = store.get("invalid_reference")
        if invalid and any(
            r["source_reference"] == invalid and r["status"] == "failed"
            for r in records
        ):
            invalid = None
        if missing or invalid:
            for record in self.ingest(base, integration, missing, invalid):
                if record["status"] == "failed":
                    if record["source_reference"] != invalid:
                        raise RuntimeError(
                            f"Unexpected import error: {record['source_reference']}: {record['error_message']}"
                        )
                else:
                    existing[record["source_reference"]] = record
        print(f"\n{store['name']} ({tenant['id']})")
        for spec in store["orders"]:
            record = existing.get(spec["reference"])
            if record is None:
                raise RuntimeError(f"Missing order {spec['reference']}")
            saved = self.call(base + f"/orders/{record['order_id']}")
            actual = sorted(
                (i["sku"], i["quantity"], Decimal(i["unit_price"]))
                for i in saved["items"]
            )
            expected = sorted((s, q, Decimal(p)) for s, q, p in spec["items"])
            if actual != expected:
                raise RuntimeError(
                    f"Order {spec['reference']} differs from the seed data; it was left unchanged."
                )
            status = saved["status"]
            if spec["process"]:
                execution = self.call(
                    base + f"/orders/{saved['id']}/process", method="POST"
                )
                status = execution["status"]
                if status not in ("completed", "needs_attention", "failed"):
                    raise RuntimeError(
                        f"Unexpected execution state for {spec['reference']}: {status}"
                    )
                category = execution.get("error_category")
                expected_shortage = (
                    store.get("shortage_sku")
                    and any(s == store["shortage_sku"] for s, _, _ in spec["items"])
                    and category == "insufficient_stock"
                )
                expected_approval = store.get("approval") and category in (
                    "approval_pending",
                    "approval_rejected",
                )
                if status != "completed" and not (
                    expected_shortage or expected_approval
                ):
                    raise RuntimeError(
                        f"Unexpected failure for {spec['reference']}: {category}. Check the provider services before presenting."
                    )
                if status != "completed":
                    print(
                        f"  Reason: {execution.get('error_message') or execution.get('error_category')}"
                    )
            total = sum(Decimal(p) * q for _, q, p in spec["items"])
            print(f"  {spec['reference']}: ${total:.2f}, {status}")
        if store.get("invalid_reference"):
            print(
                f"  {store['invalid_reference']}: invalid CSV quantity saved in import history"
            )
        return tenant

    def seed(self):
        for base in (self.api, self.inventory, self.fulfillment):
            self.call("/health", base=base)
        tenants = [self.seed_store(store) for store in STORES]
        print("\nReady: 5 grocery stores, 15 valid orders and 1 invalid import.")
        print(
            "Refresh the retailer list in React. Existing approvals, recoveries and stock are preserved."
        )
        return tenants

    def restock_harbor(self):
        store = next(s for s in STORES if s.get("shortage_sku"))
        tenant = next(
            (t for t in self.listing("/api/v1/tenants") if t["slug"] == store["slug"]),
            None,
        )
        if not tenant or not tenant["is_active"]:
            raise RuntimeError(
                "Seed the grocery stores first and ensure Harbor Fresh Foods is active."
            )
        current = self.stock(tenant["id"], store["shortage_sku"])
        if current is None or current < 8:
            self.set_stock(tenant["id"], store["shortage_sku"], 8)
        print("Harbor Fresh Foods now has at least 8 salmon packs available.")
        print(
            "Open Operations for HF-4003, add a note, and choose Retry eligible step."
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--restock-harbor",
        action="store_true",
        help="Set available salmon stock to at least 8 packs so HF-4003 can be retried.",
    )
    args = parser.parse_args()
    root = next(
        (p for p in Path(__file__).resolve().parents if (p / ".env.example").is_file()),
        None,
    )
    if root:
        load_dotenv(root / ".env")
    try:
        demo = GroceryDemo(
            os.getenv("DEMO_API_URL", "http://127.0.0.1:8000"),
            os.getenv("INVENTORY_URL", "http://127.0.0.1:8001"),
            os.getenv("FULFILLMENT_URL", "http://127.0.0.1:8002"),
            os.getenv("INGEST_TOKEN"),
        )
        if args.restock_harbor:
            demo.restock_harbor()
        else:
            demo.seed()
    except RuntimeError as exc:
        parser.exit(1, f"Grocery setup stopped: {exc}\n")


if __name__ == "__main__":
    main()
