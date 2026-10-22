from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.workflows import DbSession, ProviderDependency
from app.models.operations import AuditEvent
from app.schemas.execution import ExecutionResponse
from app.schemas.operations import RecoveryAction
from app.services import operations
from app.services.recovery import recover
from app.services.workflow import get_execution

router = APIRouter(
    prefix="/api/v1/tenants/{tenant_id}", tags=["Operations and recovery"]
)


@router.get("/operations")
def list_operations(
    tenant_id: UUID,
    db: DbSession,
    status: Literal["pending", "running", "completed", "failed", "needs_attention"]
    | None = None,
    integration_id: UUID | None = None,
    approval_status: Literal["pending", "approved", "rejected"] | None = None,
    error_category: Annotated[str | None, Query(max_length=50)] = None,
    start: datetime | None = None,
    end: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    try:
        return operations.list_operations(
            db,
            tenant_id,
            status=status,
            integration_id=integration_id,
            approval_status=approval_status,
            error_category=error_category,
            start=start,
            end=end,
            limit=limit,
            offset=offset,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/operations/summary")
def summary(
    tenant_id: UUID,
    db: DbSession,
    start: datetime | None = None,
    end: datetime | None = None,
):
    try:
        return operations.summary(db, tenant_id, start, end)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.post("/executions/{execution_id}/recovery", response_model=ExecutionResponse)
def recovery(
    tenant_id: UUID,
    execution_id: UUID,
    data: RecoveryAction,
    db: DbSession,
    providers: ProviderDependency,
):
    return recover(db, tenant_id, execution_id, data, providers)


@router.get("/executions/{execution_id}/audit")
def audit_history(
    tenant_id: UUID,
    execution_id: UUID,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    get_execution(db, tenant_id, execution_id)
    return [
        {
            "id": event.id,
            "action": event.action,
            "previous_state": event.previous_state,
            "new_state": event.new_state,
            "note": event.note,
            "development_operator": event.development_operator,
            "created_at": event.created_at,
        }
        for event in db.scalars(
            select(AuditEvent)
            .where(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.execution_id == execution_id,
            )
            .order_by(AuditEvent.created_at, AuditEvent.id)
            .limit(limit)
            .offset(offset)
        )
    ]
