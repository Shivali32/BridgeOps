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


def execution_response(response, tenant_id, result):
    response.status_code = (
        202 if queued_mode() and result.status in ("pending", "running") else 200
    )
    if response.status_code == 202:
        response.headers["Location"] = (
            f"/api/v1/tenants/{tenant_id}/executions/{result.id}"
        )
    return result


@router.post(
    "/orders/{order_id}/process",
    response_model=ExecutionResponse,
    responses={
        202: {
            "model": ExecutionResponse,
            "description": "Workflow accepted for background processing",
        }
    },
)
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
        return execution_response(response, tenant_id, result)
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
