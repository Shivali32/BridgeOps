from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response
from sqlalchemy import func, select

from app.api.workflows import DbSession, ProviderDependency
from app.messaging.contracts import queued_mode
from app.models.messaging import EventReceipt, OutboxEvent
from app.models.operations import AuditEvent
from app.schemas.execution import ExecutionResponse
from app.schemas.operations import RecoveryAction
from app.services import operations
from app.services.recovery import recover
from app.services.workflow import get_execution

router = APIRouter(
    prefix="/api/v1/tenants/{tenant_id}", tags=["Operations and recovery"]
)


@router.get("/queue")
def queue_status(tenant_id: UUID, db: DbSession):
    from app.services.order import require_tenant

    require_tenant(db, tenant_id)

    def count(*conditions):
        return db.scalar(
            select(func.count())
            .select_from(OutboxEvent)
            .where(OutboxEvent.tenant_id == tenant_id, *conditions)
        )

    return {
        "pending_publication": count(OutboxEvent.published_at.is_(None)),
        "awaiting_worker": count(
            OutboxEvent.published_at.is_not(None),
            ~OutboxEvent.id.in_(select(EventReceipt.event_id)),
        ),
        "processed": count(OutboxEvent.id.in_(select(EventReceipt.event_id))),
        "recent_events": [
            {
                "id": e.id,
                "execution_id": e.execution_id,
                "published_at": e.published_at,
                "attempts": e.attempts,
                "last_error": e.last_error,
            }
            for e in db.scalars(
                select(OutboxEvent)
                .where(OutboxEvent.tenant_id == tenant_id)
                .order_by(OutboxEvent.created_at.desc())
                .limit(20)
            )
        ],
    }


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
    response: Response,
):
    result = recover(db, tenant_id, execution_id, data, providers, queued=queued_mode())
    response.status_code = 202 if result.status == "pending" else 200
    return result


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
