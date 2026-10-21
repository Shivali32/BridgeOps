import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class OrderItemCreate(BaseModel):
    sku: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0)
    unit_price: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
    )

    @field_validator("sku")
    @classmethod
    def validate_sku(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("SKU cannot be empty")

        return value


class OrderCreate(BaseModel):
    external_order_id: str = Field(
        min_length=1,
        max_length=100,
    )

    items: list[OrderItemCreate] = Field(
        min_length=1,
        max_length=100,
    )

    @field_validator("external_order_id")
    @classmethod
    def validate_external_id(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("External order ID cannot be empty")

        return value

    @model_validator(mode="after")
    def validate_unique_skus(self):
        skus = [item.sku for item in self.items]

        if len(skus) != len(set(skus)):
            raise ValueError("Duplicate SKUs are not allowed")

        return self


class OrderItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    quantity: int
    unit_price: Decimal | None


class OrderResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    external_order_id: str
    status: str
    items: list[OrderItemResponse]
    created_at: datetime
    updated_at: datetime
