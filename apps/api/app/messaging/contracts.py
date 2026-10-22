import os
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict


class WorkEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1] = 1
    event_id: UUID
    tenant_id: UUID
    order_id: UUID
    execution_id: UUID
    created_at: datetime
    kind: Literal["run", "recover"]
    recovery_request_id: UUID | None = None
    step_id: UUID | None = None
    step_kind: str | None = None


def queued_mode():
    value = os.getenv("WORKFLOW_MODE", "kafka")
    if value not in ("kafka", "inline"):
        raise RuntimeError("WORKFLOW_MODE must be kafka or inline")
    return value == "kafka"


def topic():
    return os.getenv("KAFKA_WORK_TOPIC", "bridgops.workflow.commands.v1")


def enqueue(
    db, execution, *, kind="run", recovery_request_id=None, step_id=None, step_kind=None
):
    from app.models.messaging import OutboxEvent
    from app.services.workflow import now

    event = WorkEvent(
        event_id=uuid4(),
        tenant_id=execution.tenant_id,
        order_id=execution.order_id,
        execution_id=execution.id,
        created_at=now(),
        kind=kind,
        recovery_request_id=recovery_request_id,
        step_id=step_id,
        step_kind=step_kind,
    )
    execution.status = "pending"
    execution.active_event_id = event.event_id
    execution.run_token = None
    from app.models import Order

    db.get(Order, execution.order_id).status = "queued"
    db.add(
        OutboxEvent(
            id=event.event_id,
            tenant_id=event.tenant_id,
            execution_id=event.execution_id,
            payload=event.model_dump(mode="json"),
        )
    )
    return event
