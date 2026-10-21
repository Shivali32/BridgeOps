import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.tenant import Tenant
from app.schemas.tenant import (
    TenantCreate,
    TenantResponse,
    TenantUpdate,
)
from app.services import tenant as tenant_service
from app.services.tenant import DuplicateTenantSlugError

DbSession = Annotated[Session, Depends(get_db)]

router = APIRouter(
    prefix="/api/v1/tenants",
    tags=["Tenants"],
)


def find_tenant_or_404(
    tenant_id: uuid.UUID,
    db: Session,
) -> Tenant:
    tenant = tenant_service.get_tenant(db, tenant_id)

    if tenant is None:
        raise HTTPException(
            status_code=404,
            detail="Tenant not found",
        )

    return tenant


@router.post(
    "",
    response_model=TenantResponse,
    status_code=201,
)
def create_tenant(
    data: TenantCreate,
    db: DbSession,
):
    try:
        return tenant_service.create_tenant(db, data)
    except DuplicateTenantSlugError:
        raise HTTPException(
            status_code=409,
            detail="Tenant slug already exists",
        ) from None


@router.get("", response_model=list[TenantResponse])
def list_tenants(
    db: DbSession,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return tenant_service.list_tenants(db, offset, limit)


@router.get("/{tenant_id}", response_model=TenantResponse)
def get_tenant(
    tenant_id: uuid.UUID,
    db: DbSession,
):
    return find_tenant_or_404(tenant_id, db)


@router.patch("/{tenant_id}", response_model=TenantResponse)
def update_tenant(
    tenant_id: uuid.UUID,
    data: TenantUpdate,
    db: DbSession,
):
    tenant = find_tenant_or_404(tenant_id, db)
    return tenant_service.update_tenant(db, tenant, data)


@router.delete("/{tenant_id}", status_code=204)
def delete_tenant(
    tenant_id: uuid.UUID,
    db: DbSession,
):
    tenant = find_tenant_or_404(tenant_id, db)
    tenant_service.deactivate_tenant(db, tenant)
    return Response(status_code=204)
