from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.orders import translate_error
from app.db import get_db
from app.messaging.contracts import queued_mode
from app.schemas.execution import ExecutionResponse
from app.services import order, workflow
from app.services.providers import Providers, get_providers

DbSession = Annotated[Session, Depends(get_db)]
ProviderDependency = Annotated[Providers, Depends(get_providers)]
router = APIRouter(prefix="/api/v1/tenants/{tenant_id}", tags=["Workflows"])


@router.post("/orders/{order_id}/process", response_model=ExecutionResponse)
def process(
    tenant_id: UUID,
    order_id: UUID,
    db: DbSession,
    providers: ProviderDependency,
    response: Response,
):
    try:
        result = workflow.process_order(
            db, tenant_id, order_id, providers, queued=queued_mode()
        )
        response.status_code = 202 if result.status == "pending" else 200
        return result
    except (
        order.TenantNotFoundError,
        order.OrderNotFoundError,
        order.InactiveTenantError,
    ) as exc:
        raise translate_error(exc) from None


@router.get("/orders/{order_id}/executions", response_model=list[ExecutionResponse])
def executions(tenant_id: UUID, order_id: UUID, db: DbSession):
    try:
        return workflow.list_executions(db, tenant_id, order_id)
    except (order.TenantNotFoundError, order.OrderNotFoundError) as exc:
        raise translate_error(exc) from None


@router.get("/executions/{execution_id}", response_model=ExecutionResponse)
def execution(tenant_id: UUID, execution_id: UUID, db: DbSession):
    try:
        return workflow.get_execution(db, tenant_id, execution_id)
    except order.OrderNotFoundError as exc:
        raise translate_error(exc) from None
