import os
import time
from threading import Lock
from typing import Annotated, Literal
from uuid import UUID

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.order import OrderItemCreate

DbSession = Annotated[Session, Depends(get_db)]


class ItemsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tenant_id: UUID
    items: list[OrderItemCreate] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_items(self):
        if len({x.sku for x in self.items}) != len(self.items):
            raise ValueError("Duplicate SKUs are not allowed")
        return self


class ReservationCreate(ItemsRequest):
    idempotency_key: str = Field(min_length=1, max_length=150, pattern=r"^\S+$")


class Behavior(BaseModel):
    mode: Literal["normal", "unavailable", "delay_before", "delay_after"] = "normal"
    remaining: int = Field(default=1, ge=0, le=100)
    delay_seconds: float = Field(default=2, ge=0, le=10)


class Simulator:
    """Single-process, development-only controls. Never used for business state."""

    def __init__(self):
        self.behavior = Behavior(mode="normal", remaining=0)
        self.lock = Lock()

    def configure(self, value: Behavior):
        if os.getenv("ENABLE_DEMO_ADMIN") != "true":
            raise HTTPException(404, "Development controls are disabled")
        with self.lock:
            self.behavior = value
        return value

    def before(self) -> Behavior:
        with self.lock:
            value = self.behavior.model_copy()
            if self.behavior.remaining > 0:
                self.behavior.remaining -= 1
            else:
                value.mode = "normal"
        if value.mode == "unavailable":
            raise HTTPException(
                503, "Simulated provider unavailable before any side effect"
            )
        if value.mode == "delay_before":
            time.sleep(value.delay_seconds)
        return value

    @staticmethod
    def after(value: Behavior):
        if value.mode == "delay_after":
            time.sleep(value.delay_seconds)


def canonical_items(data: ItemsRequest):
    return sorted(
        [{"sku": x.sku, "quantity": x.quantity} for x in data.items],
        key=lambda x: x["sku"],
    )
