from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.order import OrderCreate


def test_valid_order():
    order = OrderCreate(
        external_order_id="WEB-1001",
        items=[
            {
                "sku": "RICE-5KG",
                "quantity": 2,
                "unit_price": "12.50",
            }
        ],
    )

    assert order.external_order_id == "WEB-1001"
    assert order.items[0].quantity == 2
    assert order.items[0].unit_price == Decimal("12.50")


def test_empty_order_items():
    with pytest.raises(ValidationError):
        OrderCreate(
            external_order_id="WEB-1001",
            items=[],
        )


def test_invalid_quantity():
    with pytest.raises(ValidationError):
        OrderCreate(
            external_order_id="WEB-1001",
            items=[{"sku": "MILK-1L", "quantity": 0}],
        )


def test_duplicate_skus():
    with pytest.raises(ValidationError):
        OrderCreate(
            external_order_id="WEB-1001",
            items=[
                {"sku": "MILK-1L", "quantity": 2},
                {"sku": "MILK-1L", "quantity": 3},
            ],
        )


def test_blank_external_order_id():
    with pytest.raises(ValidationError):
        OrderCreate(
            external_order_id="   ",
            items=[{"sku": "MILK-1L", "quantity": 1}],
        )


def test_blank_sku():
    with pytest.raises(ValidationError):
        OrderCreate(
            external_order_id="WEB-1001",
            items=[{"sku": "   ", "quantity": 1}],
        )


def test_negative_price():
    with pytest.raises(ValidationError):
        OrderCreate(
            external_order_id="WEB-1001",
            items=[
                {
                    "sku": "MILK-1L",
                    "quantity": 1,
                    "unit_price": "-1.00",
                }
            ],
        )
