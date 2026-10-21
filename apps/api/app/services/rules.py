from decimal import Decimal

from app.schemas.definition import Rules
from app.services.providers import ProviderError


def evaluate(rules: Rules, items: list[dict], source: dict) -> bool:
    results = []
    for rule in rules.rules:
        if rule.field == "order_total":
            if any(item.get("unit_price") is None for item in items):
                raise ProviderError(
                    "validation_error",
                    "Order total is unavailable because one or more item prices are missing.",
                )
            left = sum(
                (Decimal(item["unit_price"]) * item["quantity"] for item in items),
                Decimal(0),
            )
            right = Decimal(rule.value)
        elif rule.field == "total_quantity":
            left, right = sum(i["quantity"] for i in items), Decimal(rule.value)
        elif rule.field == "sku":
            left, right = [i["sku"] for i in items], rule.value
        else:
            left, right = source.get(rule.field), rule.value
            if left is None:
                raise ProviderError(
                    "validation_error", f"Rule input {rule.field} is unavailable."
                )
        if rule.field == "sku":
            matched = right in left
            if rule.operator == "not_equals":
                matched = not matched
        else:
            if rule.operator == "equals":
                matched = left == right
            elif rule.operator == "not_equals":
                matched = left != right
            elif rule.operator == "greater_than":
                matched = left > right
            elif rule.operator == "less_than":
                matched = left < right
            else:
                matched = right in left
        results.append(matched)
    return all(results) if rules.match == "all" else any(results)
