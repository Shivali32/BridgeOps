from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas.order import OrderCreate, OrderResponse
from app.services import order as service

DbSession = Annotated[Session, Depends(get_db)]
router = APIRouter(prefix="/api/v1/tenants/{tenant_id}/orders", tags=["Orders"])


def translate_error(exc: Exception) -> HTTPException:
    code = (
        404
        if isinstance(exc, (service.TenantNotFoundError, service.OrderNotFoundError))
        else 409
    )
    return HTTPException(status_code=code, detail=str(exc))


@router.post("", response_model=OrderResponse, status_code=201)
def create_order(tenant_id: UUID, data: OrderCreate, response: Response, db: DbSession):
    try:
        order, created = service.create_order(db, tenant_id, data)
        response.status_code = 201 if created else 200
        return order
    except (
        service.TenantNotFoundError,
        service.InactiveTenantError,
        service.OrderConflictError,
    ) as exc:
        raise translate_error(exc) from None


@router.get("", response_model=list[OrderResponse])
def list_orders(
    tenant_id: UUID,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    try:
        return service.list_orders(db, tenant_id, limit, offset)
    except service.TenantNotFoundError as exc:
        raise translate_error(exc) from None


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(tenant_id: UUID, order_id: UUID, db: DbSession):
    try:
        return service.get_order(db, tenant_id, order_id)
    except (service.TenantNotFoundError, service.OrderNotFoundError) as exc:
        raise translate_error(exc) from None
