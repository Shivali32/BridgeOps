from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.definition import DefinitionCreate, Rules
from app.services.providers import ProviderError
from app.services.rules import evaluate


def rules(field="order_total", operator="greater_than", value="25.00"):
    return Rules(rules=[{"field": field, "operator": operator, "value": value}])


@pytest.mark.parametrize(
    "operator,value,expected",
    [
        ("equals", "25.00", True),
        ("greater_than", "24.99", True),
        ("less_than", "25.01", True),
        ("not_equals", "25.00", False),
    ],
)
def test_money_comparisons(operator, value, expected):
    assert (
        evaluate(
            rules(operator=operator, value=value),
            [{"sku": "A", "quantity": 2, "unit_price": Decimal("12.50")}],
            {},
        )
        is expected
    )


def test_missing_prices_do_not_become_zero():
    with pytest.raises(ProviderError, match="prices are missing"):
        evaluate(rules(), [{"sku": "A", "quantity": 1, "unit_price": None}], {})


def test_sku_source_and_combined_rules():
    rule = Rules(
        match="all",
        rules=[
            {"field": "sku", "operator": "contains", "value": "A"},
            {"field": "source_connector", "operator": "equals", "value": "csv"},
        ],
    )
    assert evaluate(rule, [{"sku": "A", "quantity": 2}], {"source_connector": "csv"})
    assert not evaluate(
        rule, [{"sku": "B", "quantity": 2}], {"source_connector": "csv"}
    )
    rule.match = "any"
    assert evaluate(rule, [{"sku": "B", "quantity": 2}], {"source_connector": "csv"})


@pytest.mark.parametrize(
    "field,operator,value",
    [
        ("order_total", "contains", "2"),
        ("order_total", "equals", "NaN"),
        ("sku", "greater_than", "A"),
        ("arbitrary", "equals", "1"),
    ],
)
def test_invalid_rule_config(field, operator, value):
    with pytest.raises(ValidationError):
        rules(field, operator, value)


def test_rejects_unsafe_workflow_order_and_circular_branch():
    base = [
        {"id": "check", "type": "inventory_check"},
        {"id": "reserve", "type": "inventory_reservation"},
        {"id": "fulfill", "type": "fulfillment_request"},
    ]
    assert DefinitionCreate(name="Standard", steps=base)
    with pytest.raises(ValidationError):
        DefinitionCreate(name="Wrong order", steps=list(reversed(base)))
    with pytest.raises(ValidationError):
        DefinitionCreate(
            name="Forward reference",
            steps=[
                {
                    "id": "approve",
                    "type": "approval",
                    "when": {"condition_step": "future"},
                },
                *base,
            ],
        )


def test_version_history_and_tenant_ownership(session):
    from uuid import uuid4

    from sqlalchemy import select

    from app.models import Tenant
    from app.models.definition import WorkflowVersion
    from app.schemas.definition import DefinitionUpdate
    from app.services.definition import (
        WorkflowConflictError,
        get_definition,
        save_definition,
    )
    from app.services.order import OrderNotFoundError

    t = Tenant(name="A", slug="a")
    session.add(t)
    session.commit()
    data = {
        "name": "Standard",
        "is_default": True,
        "steps": [
            {"id": kind, "type": kind}
            for kind in (
                "inventory_check",
                "inventory_reservation",
                "fulfillment_request",
            )
        ],
    }
    value = save_definition(session, t.id, DefinitionCreate(**data))
    assert value.version == 1 and value.is_default
    value = save_definition(
        session,
        t.id,
        DefinitionUpdate(**{**data, "name": "Updated", "expected_version": 1}),
        value.id,
    )
    versions = list(
        session.scalars(select(WorkflowVersion).order_by(WorkflowVersion.version))
    )
    assert value.version == 2 and [v.snapshot["name"] for v in versions] == [
        "Standard",
        "Updated",
    ]
    with pytest.raises(WorkflowConflictError):
        save_definition(
            session, t.id, DefinitionUpdate(**data, expected_version=1), value.id
        )
    with pytest.raises(OrderNotFoundError):
        get_definition(session, uuid4(), value.id)
