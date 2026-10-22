from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class StepResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    step_name: str
    status: str
    attempt_number: int
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    error_category: str | None
    retryable: bool
    idempotency_key: str | None
    external_reference: str | None
    input_summary: dict
    output_summary: dict


class ExecutionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    order_id: UUID
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    error_message: str | None
    error_category: str | None
    definition_snapshot: dict
    steps: list[StepResponse]
