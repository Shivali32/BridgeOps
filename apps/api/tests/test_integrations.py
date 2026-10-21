from uuid import uuid4

import pytest


def tenant(client, name="a"):
    return client.post("/api/v1/tenants", json={"name": name, "slug": name}).json()[
        "id"
    ]


def test_configuration_ingestion_and_snapshot(api_client, monkeypatch):
    c = api_client
    a, b = tenant(c), tenant(c, "b")
    base = f"/api/v1/tenants/{a}"
    config = {"name": "Shop orders", "connector_type": "shopify_simulated"}
    response = c.post(base + "/integrations", json=config)
    assert response.status_code == 201
    integration = response.json()
    url = base + f"/integrations/{integration['id']}"
    payload = {
        "id": "SHOP-1",
        "line_items": [{"sku": "A", "quantity": 2, "price": "12.50"}],
        "password": "never_store_this",
    }
    assert c.post(url + "/ingest", json=payload).status_code == 403
    monkeypatch.setenv("INGEST_TOKEN", "test-token")
    auth = {"X-Development-Token": "test-token"}
    result = c.post(url + "/ingest", json=payload, headers=auth).json()
    assert result["status"] == "succeeded" and not result["duplicate"]
    assert "never_store_this" not in str(result)
    assert c.post(url + "/ingest", json=payload, headers=auth).json()["duplicate"]
    assert (
        c.post(
            f"/api/v1/tenants/{b}/integrations/{integration['id']}/ingest",
            json=payload,
            headers=auth,
        ).status_code
        == 404
    )
    changed = c.patch(url, json={**config, "enabled": False, "expected_version": 1})
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert c.patch(url, json={**config, "expected_version": 1}).status_code == 409
    assert c.post(url + "/ingest", json=payload, headers=auth).status_code == 409
    imports = c.get(base + "/imports").json()
    assert len(imports) == 2 and all(
        x["config_snapshot"]["version"] == 1 for x in imports
    )
    assert c.get(f"/api/v1/tenants/{b}/imports").json() == []
    assert c.get(f"/api/v1/tenants/{uuid4()}/integrations").status_code == 404
    assert (
        c.post(
            base + "/integrations", json={**config, "api_key": "forbidden"}
        ).status_code
        == 422
    )
    assert (
        c.post(
            base + "/integrations", json={**config, "connector_type": "unsupported"}
        ).status_code
        == 422
    )


def test_csv_partial_failures_and_idempotency(api_client, monkeypatch):
    c = api_client
    a = tenant(c)
    monkeypatch.setenv("INGEST_TOKEN", "token")
    auth = {"X-Development-Token": "token"}
    base = f"/api/v1/tenants/{a}"
    config = c.post(
        base + "/integrations", json={"name": "CSV orders", "connector_type": "csv"}
    ).json()
    url = base + f"/integrations/{config['id']}/csv"
    text = "order_reference,product_code,qty,unit_price\nCSV-1,A,2,12.50\nCSV-1,B,1,3.25\nCSV-2,A,0,1.00\nCSV-3,C,1,\n"
    results = c.post(url, json={"csv_text": text}, headers=auth)
    assert results.status_code == 200
    items = results.json()
    assert [x["status"] for x in items] == ["succeeded", "failed", "succeeded"]
    assert items[0]["row_numbers"] == [2, 3] and items[1]["row_numbers"] == [4]
    assert items[1]["source_reference"] == "CSV-2"
    orders = c.get(base + "/orders").json()
    assert len(orders) == 2
    assert (
        next(x for x in orders if x["external_order_id"] == "CSV-1")["items"].__len__()
        == 2
    )
    repeated = c.post(url, json={"csv_text": text}, headers=auth).json()
    assert [x["duplicate"] for x in repeated] == [True, False, True]
    assert len(c.get(base + "/orders").json()) == 2
    assert (
        c.post(url, json={"csv_text": "bad,headers\nA,B"}, headers=auth).status_code
        == 422
    )
    assert (
        c.post(
            url,
            json={"csv_text": "order_reference,product_code,qty\n" + "A,B,1\n" * 501},
            headers=auth,
        ).status_code
        == 422
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"products": []},
        {"reference": "X", "products": [{"product_code": "A", "count": -1}]},
    ],
)
def test_failed_imports_are_recorded(api_client, monkeypatch, payload):
    c = api_client
    a = tenant(c)
    monkeypatch.setenv("INGEST_TOKEN", "token")
    base = f"/api/v1/tenants/{a}"
    config = c.post(
        base + "/integrations", json={"name": "Custom", "connector_type": "custom_rest"}
    ).json()
    result = c.post(
        base + f"/integrations/{config['id']}/ingest",
        json=payload,
        headers={"X-Development-Token": "token"},
    ).json()
    assert result["status"] == "failed" and result["error_message"]
    assert c.get(base + "/orders").json() == []
    assert len(c.get(base + "/imports").json()) == 1
    corrected = {
        "reference": "CORRECTED-1",
        "products": [{"product_code": "A", "count": 2, "price_cents": 1250}],
    }
    fixed = c.post(
        base + f"/integrations/{config['id']}/ingest",
        json=corrected,
        headers={"X-Development-Token": "token"},
    ).json()
    assert fixed["status"] == "succeeded"
    assert len(c.get(base + "/imports").json()) == 2
