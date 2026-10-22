from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RecoveryAction(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    request_key: str = Field(min_length=1, max_length=100, pattern=r"^\S+$")
    action: Literal["retry", "reconcile", "verify_reference", "investigated"]
    note: str = Field(min_length=1, max_length=1000)
    development_operator: str = Field(
        default="Local demo operator (unverified)", min_length=1, max_length=100
    )
    external_reference: UUID | None = None
