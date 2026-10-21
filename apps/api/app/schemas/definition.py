from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Rule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    field: Literal["order_total", "total_quantity", "sku", "source_connector", "source"]
    operator: Literal["equals", "not_equals", "greater_than", "less_than", "contains"]
    value: str = Field(max_length=150)

    @model_validator(mode="after")
    def validate_types(self):
        if self.field in ("order_total", "total_quantity"):
            try:
                number = Decimal(self.value)
                if not number.is_finite() or self.operator == "contains":
                    raise ValueError
            except (InvalidOperation, ValueError):
                raise ValueError(
                    "Numeric rules require a finite number and numeric operator"
                ) from None
        elif self.operator not in ("equals", "not_equals", "contains"):
            raise ValueError("Text rules support equals, not_equals or contains")
        return self


class Rules(BaseModel):
    model_config = ConfigDict(extra="forbid")
    match: Literal["all", "any"] = "all"
    rules: list[Rule] = Field(min_length=1, max_length=10)


class Branch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    condition_step: str
    matches: bool = True


class DefinitionStep(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_]{0,49}$")
    type: Literal[
        "inventory_check",
        "inventory_reservation",
        "fulfillment_request",
        "condition",
        "approval",
    ]
    rules: Rules | None = None
    when: Branch | None = None
    reason: str = Field(
        default="Operator approval required", min_length=1, max_length=300
    )


class DefinitionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=500)
    enabled: bool = True
    is_default: bool = False
    trigger: Literal["order_processing"] = "order_processing"
    steps: list[DefinitionStep] = Field(min_length=3, max_length=20)

    @model_validator(mode="after")
    def deterministic_steps(self):
        seen = {}
        for step in self.steps:
            if step.id in seen:
                raise ValueError("Step IDs must be unique")
            if step.type == "condition" and step.rules is None:
                raise ValueError("Condition steps require rules")
            if step.type != "condition" and step.rules is not None:
                raise ValueError("Rules belong to condition steps")
            if step.when and (
                step.type != "approval"
                or seen.get(step.when.condition_step) != "condition"
            ):
                raise ValueError(
                    "Approval branches must reference an earlier condition step"
                )
            seen[step.id] = step.type
        provider_types = [
            s.type for s in self.steps if s.type not in ("condition", "approval")
        ]
        if provider_types != [
            "inventory_check",
            "inventory_reservation",
            "fulfillment_request",
        ]:
            raise ValueError(
                "Include one check, reservation and fulfillment in that order"
            )
        reserve_at = next(
            i for i, s in enumerate(self.steps) if s.type == "inventory_reservation"
        )
        if any(s.type == "approval" for s in self.steps[reserve_at:]):
            raise ValueError("Approvals must happen before reserving stock")
        return self


class DefinitionUpdate(DefinitionCreate):
    expected_version: int = Field(ge=1)


class DefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    name: str
    enabled: bool
    is_default: bool
    version: int
    configuration: dict
    created_at: datetime
