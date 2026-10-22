import hmac
import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors import REGISTRY
from app.db import get_db
from app.models.integration import ImportRecord, Integration
from app.schemas.integration import (
    CsvInput,
    ImportResponse,
    IntegrationCreate,
    IntegrationResponse,
    IntegrationUpdate,
)
from app.services import integration as service
from app.services.order import require_tenant

DbSession = Annotated[Session, Depends(get_db)]
router = APIRouter(prefix="/api/v1/tenants/{tenant_id}", tags=["Integrations"])


def ingestion_auth(
    token: Annotated[str | None, Header(alias="X-Development-Token")] = None,
):
    expected = os.getenv("INGEST_TOKEN")
    if not expected or not token or not hmac.compare_digest(token, expected):
        raise HTTPException(403, "Valid development ingestion token required.")


@router.get("/connectors")
def connectors(tenant_id: UUID, db: DbSession):
    require_tenant(db, tenant_id)
    return [
        {
            "type": name,
            "operations": ["csv_import" if name == "csv" else "receive_order"],
            "authentication": "environment development token",
            "default_mapping": value.default_mapping.model_dump(mode="json"),
        }
        for name, value in REGISTRY.items()
    ]


@router.get("/integrations", response_model=list[IntegrationResponse])
def integrations(
    tenant_id: UUID,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    require_tenant(db, tenant_id)
    return list(
        db.scalars(
            select(Integration)
            .where(Integration.tenant_id == tenant_id)
            .order_by(Integration.created_at, Integration.id)
            .limit(limit)
            .offset(offset)
        )
    )


@router.post("/integrations", response_model=IntegrationResponse, status_code=201)
def create(tenant_id: UUID, data: IntegrationCreate, db: DbSession):
    return service.save_integration(db, tenant_id, data)


@router.patch("/integrations/{integration_id}", response_model=IntegrationResponse)
def update(
    tenant_id: UUID, integration_id: UUID, data: IntegrationUpdate, db: DbSession
):
    return service.save_integration(db, tenant_id, data, integration_id)


@router.post(
    "/integrations/{integration_id}/ingest",
    response_model=ImportResponse,
    dependencies=[Depends(ingestion_auth)],
)
def ingest(tenant_id: UUID, integration_id: UUID, data: dict, db: DbSession):
    # Request model stays provider-specific; transformation supplies canonical validation.
    import json

    if len(json.dumps(data).encode()) > 262144:
        raise HTTPException(413, "Provider payload is limited to 256 KiB.")
    return service.ingest(db, tenant_id, integration_id, data)


@router.post(
    "/integrations/{integration_id}/csv",
    response_model=list[ImportResponse],
    dependencies=[Depends(ingestion_auth)],
)
def csv_import(tenant_id: UUID, integration_id: UUID, data: CsvInput, db: DbSession):
    try:
        return service.ingest_csv(db, tenant_id, integration_id, data.csv_text)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None


@router.get("/imports", response_model=list[ImportResponse])
def imports(
    tenant_id: UUID,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    require_tenant(db, tenant_id)
    return list(
        db.scalars(
            select(ImportRecord)
            .where(ImportRecord.tenant_id == tenant_id)
            .order_by(ImportRecord.created_at.desc(), ImportRecord.id)
            .limit(limit)
            .offset(offset)
        )
    )
