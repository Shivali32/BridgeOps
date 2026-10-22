from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.connectors import REGISTRY, Mapping, connector, transform


def test_distinct_sources_normalize_to_same_order():
    shop = {
        "id": " W-1 ",
        "line_items": [{"sku": " A ", "quantity": 2, "price": "12.50"}],
    }
    rest = {
        "reference": "W-1",
        "products": [{"product_code": "A", "count": "2", "price_cents": "1250"}],
    }
    csv = {
        "order_reference": "W-1",
        "rows": [{"product_code": "A", "qty": "2", "unit_price": "12.50"}],
    }
    models = [
        connector(name).convert(payload)
        for name, payload in zip(REGISTRY, [shop, rest, csv], strict=True)
    ]
    assert models[0] == models[1] == models[2]
    assert models[0].items[0].unit_price == Decimal("12.50")
    with pytest.raises(ValueError, match="Unsupported"):
        connector("unknown")


@pytest.mark.parametrize(
    "changes",
    [
        {"external_id": "__import__('os')"},
        {"quantity": "a[0]"},
        {"extra": "secret"},
        {"default_quantity": 0},
    ],
)
def test_invalid_mapping_config(changes):
    with pytest.raises(ValidationError):
        Mapping(**changes)


@pytest.mark.parametrize(
    "items",
    [
        [],
        [{"product_code": "A", "count": 0}],
        [{"product_code": "A", "count": True}],
        [{"product_code": "A", "count": 1, "price_cents": "NaN"}],
        [{"product_code": "A", "count": 1, "price_cents": "12.345"}],
        [{"count": 1}],
        [{"product_code": "A", "count": 1}, {"product_code": " A ", "count": 2}],
    ],
)
def test_invalid_transformations(items):
    with pytest.raises(ValueError):
        connector("custom_rest").convert({"reference": "W-1", "products": items})


def test_nested_mapping_and_defaults():
    config = Mapping(
        external_id="order.number",
        items="entries",
        sku="code",
        quantity="amount",
        unit_price=None,
        default_quantity=3,
        default_price="1.20",
    )
    result = transform({"order": {"number": 123}, "entries": [{"code": "A"}]}, config)
    assert result.external_order_id == "123"
    assert result.items[0].quantity == 3 and result.items[0].unit_price == Decimal(
        "1.20"
    )
