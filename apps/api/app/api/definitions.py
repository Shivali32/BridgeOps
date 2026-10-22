from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.api.workflows import DbSession, ProviderDependency
from app.models.definition import Approval, WorkflowDefinition, WorkflowVersion
from app.schemas.definition import (
    ApprovalDecision,
    ApprovalResponse,
    DefinitionCreate,
    DefinitionResponse,
    DefinitionUpdate,
)
from app.schemas.execution import ExecutionResponse
from app.services.definition import get_definition, save_definition
from app.services.order import require_tenant
from app.services.workflow import decide_approval

router = APIRouter(
    prefix="/api/v1/tenants/{tenant_id}", tags=["Workflow definitions and approvals"]
)


@router.get("/workflow-definitions", response_model=list[DefinitionResponse])
def definitions(
    tenant_id: UUID,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    require_tenant(db, tenant_id)
    return list(
        db.scalars(
            select(WorkflowDefinition)
            .where(WorkflowDefinition.tenant_id == tenant_id)
            .order_by(WorkflowDefinition.created_at, WorkflowDefinition.id)
            .limit(limit)
            .offset(offset)
        )
    )


@router.post(
    "/workflow-definitions", response_model=DefinitionResponse, status_code=201
)
def create(tenant_id: UUID, data: DefinitionCreate, db: DbSession):
    return save_definition(db, tenant_id, data)


@router.patch(
    "/workflow-definitions/{definition_id}", response_model=DefinitionResponse
)
def update(tenant_id: UUID, definition_id: UUID, data: DefinitionUpdate, db: DbSession):
    return save_definition(db, tenant_id, data, definition_id)


@router.get("/workflow-definitions/{definition_id}/versions")
def versions(
    tenant_id: UUID,
    definition_id: UUID,
    db: DbSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    get_definition(db, tenant_id, definition_id)
    return [
        {"version": v.version, "snapshot": v.snapshot, "created_at": v.created_at}
        for v in db.scalars(
            select(WorkflowVersion)
            .where(
                WorkflowVersion.tenant_id == tenant_id,
                WorkflowVersion.definition_id == definition_id,
            )
            .order_by(WorkflowVersion.version.desc())
            .limit(limit)
            .offset(offset)
        )
    ]


@router.get("/approvals", response_model=list[ApprovalResponse])
def approvals(
    tenant_id: UUID,
    db: DbSession,
    status: Literal["pending", "approved", "rejected"] | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    require_tenant(db, tenant_id)
    query = select(Approval).where(Approval.tenant_id == tenant_id)
    if status:
        query = query.where(Approval.status == status)
    return list(
        db.scalars(
            query.order_by(Approval.created_at.desc(), Approval.id)
            .limit(limit)
            .offset(offset)
        )
    )


@router.post("/approvals/{approval_id}/decision", response_model=ExecutionResponse)
def decision(
    tenant_id: UUID,
    approval_id: UUID,
    data: ApprovalDecision,
    db: DbSession,
    providers: ProviderDependency,
):
    return decide_approval(db, tenant_id, approval_id, data, providers)
