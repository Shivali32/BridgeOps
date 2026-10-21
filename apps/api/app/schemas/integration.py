from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.connectors import Mapping


class IntegrationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    connector_type: Literal["shopify_simulated", "custom_rest", "csv"]
    enabled: bool = True
    mapping: Mapping | None = None


class IntegrationUpdate(IntegrationCreate):
    expected_version: int = Field(ge=1)


class IntegrationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    tenant_id: UUID
    name: str
    connector_type: str
    enabled: bool
    version: int
    mapping: dict
    created_at: datetime


class ImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    integration_id: UUID
    order_id: UUID | None
    source_reference: str | None
    status: str
    duplicate: bool
    config_snapshot: dict
    payload_digest: str
    row_numbers: list[int]
    error_message: str | None
    created_at: datetime


class CsvInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv_text: str = Field(max_length=262144)
