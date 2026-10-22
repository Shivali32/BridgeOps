"""Small adapter registry. No dynamic loading or user code execution."""

from decimal import Decimal, InvalidOperation
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.schemas.order import OrderCreate


class TransformationError(ValueError):
    pass


class Mapping(BaseModel):
    model_config = ConfigDict(extra="forbid")
    external_id: str = "reference"
    items: str = "products"
    sku: str = "product_code"
    quantity: str = "count"
    unit_price: str | None = "price_cents"
    price_in_cents: bool = True
    default_quantity: int | None = Field(default=None, gt=0)
    default_price: Decimal | None = Field(
        default=None, ge=0, max_digits=12, decimal_places=2
    )

    @field_validator("external_id", "items", "sku", "quantity", "unit_price")
    @classmethod
    def supported_path(cls, value):
        if value is not None and (
            len(value) > 100
            or not all(
                x.isidentifier() and not x.startswith("_") for x in value.split(".")
            )
        ):
            raise TransformationError("Use dotted field names only")
        return value


def field(data, path, default=None):
    if path is None:
        return default
    for part in path.split("."):
        if not isinstance(data, dict) or part not in data:
            return default
        data = data[part]
    return data


def transform(payload: dict, mapping: Mapping):
    order_id = field(payload, mapping.external_id)
    if isinstance(order_id, bool) or not isinstance(order_id, (str, int)):
        raise TransformationError(
            f"Missing or invalid source identifier: {mapping.external_id}"
        )
    items = field(payload, mapping.items)
    if not isinstance(items, list) or not 1 <= len(items) <= 100:
        raise TransformationError(f"{mapping.items} must contain 1 to 100 items")
    normalized = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise TransformationError(f"Item {index} must be an object")
        quantity = field(item, mapping.quantity, mapping.default_quantity)
        if isinstance(quantity, bool):
            raise TransformationError(f"Item {index}: quantity cannot be a boolean")
        raw_price = field(item, mapping.unit_price)
        price = mapping.default_price
        if raw_price not in (None, ""):
            try:
                price = Decimal(str(raw_price))
                if not price.is_finite():
                    raise TransformationError
                if mapping.price_in_cents:
                    price /= Decimal(100)
            except (InvalidOperation, ValueError):
                raise TransformationError(f"Item {index}: invalid price") from None
        normalized.append(
            {"sku": field(item, mapping.sku), "quantity": quantity, "unit_price": price}
        )
    try:
        return OrderCreate(external_order_id=str(order_id), items=normalized)
    except ValidationError as exc:
        # Pydantic's str(exc) includes raw input. Only expose field paths/messages.
        raise TransformationError(
            "; ".join(
                f"{'.'.join(map(str, e['loc']))}: {e['msg']}"
                for e in exc.errors(include_input=False)
            )
        ) from None


class Connector(Protocol):
    name: str
    default_mapping: Mapping

    def convert(self, payload: dict, mapping: Mapping | None = None) -> OrderCreate: ...


class JsonConnector:
    def __init__(self, name, mapping):
        self.name = name
        self.default_mapping = mapping

    def convert(self, payload, mapping=None):
        if not isinstance(payload, dict):
            raise TransformationError("Provider payload must be an object")
        return transform(payload, mapping or self.default_mapping)


REGISTRY: dict[str, Connector] = {
    "shopify_simulated": JsonConnector(
        "shopify_simulated",
        Mapping(
            external_id="id",
            items="line_items",
            sku="sku",
            quantity="quantity",
            unit_price="price",
            price_in_cents=False,
        ),
    ),
    "custom_rest": JsonConnector("custom_rest", Mapping()),
    "csv": JsonConnector(
        "csv",
        Mapping(
            external_id="order_reference",
            items="rows",
            sku="product_code",
            quantity="qty",
            unit_price="unit_price",
            price_in_cents=False,
        ),
    ),
}


def connector(name: str) -> Connector:
    if name not in REGISTRY:
        raise TransformationError("Unsupported connector type")
    return REGISTRY[name]
