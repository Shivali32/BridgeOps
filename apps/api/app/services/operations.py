from datetime import UTC

from sqlalchemy import exists, func, select

from app.models import Order, WorkflowExecution
from app.models.definition import Approval
from app.models.integration import ImportRecord
from app.models.operations import AuditEvent
from app.services.order import require_tenant


def time_range(start, end):
    start = (
        start.replace(tzinfo=UTC)
        if start is not None and start.tzinfo is None
        else start
    )
    end = end.replace(tzinfo=UTC) if end is not None and end.tzinfo is None else end
    if start and end and start > end:
        raise ValueError("Start time must be before end time.")
    return start, end


def dates(query, column, start, end):
    if start:
        query = query.where(column >= start)
    if end:
        query = query.where(column <= end)
    return query


def list_operations(
    db,
    tenant_id,
    *,
    status=None,
    integration_id=None,
    approval_status=None,
    error_category=None,
    start=None,
    end=None,
    limit=50,
    offset=0,
):
    require_tenant(db, tenant_id)
    start, end = time_range(start, end)
    query = (
        select(WorkflowExecution, Order.external_order_id)
        .join(
            Order,
            (Order.id == WorkflowExecution.order_id)
            & (Order.tenant_id == WorkflowExecution.tenant_id),
        )
        .where(WorkflowExecution.tenant_id == tenant_id)
    )
    if status:
        query = query.where(WorkflowExecution.status == status)
    if integration_id:
        from app.services.integration import get_integration

        get_integration(db, tenant_id, integration_id)
        query = query.where(
            WorkflowExecution.definition_snapshot["source"][
                "integration_id"
            ].as_string()
            == str(integration_id)
        )
    if error_category:
        query = query.where(WorkflowExecution.error_category == error_category)
    if approval_status:
        query = query.where(
            exists().where(
                Approval.execution_id == WorkflowExecution.id,
                Approval.tenant_id == tenant_id,
                Approval.status == approval_status,
            )
        )
    query = (
        dates(query, WorkflowExecution.started_at, start, end)
        .order_by(WorkflowExecution.started_at.desc(), WorkflowExecution.id)
        .limit(limit)
        .offset(offset)
    )
    return [
        {
            "id": value.id,
            "order_id": value.order_id,
            "tenant_id": tenant_id,
            "external_order_id": external_id,
            "status": value.status,
            "source": value.definition_snapshot.get("source", {}),
            "workflow_name": value.definition_snapshot.get("name"),
            "workflow_version": value.definition_snapshot.get("version"),
            "started_at": value.started_at,
            "completed_at": value.completed_at,
            "error_category": value.error_category,
            "error_message": value.error_message,
        }
        for value, external_id in db.execute(query)
    ]


def summary(db, tenant_id, start=None, end=None):
    require_tenant(db, tenant_id)
    start, end = time_range(start, end)

    def counts(model, column):
        return dict(
            db.execute(
                dates(
                    select(model.status, func.count())
                    .where(model.tenant_id == tenant_id)
                    .group_by(model.status),
                    column,
                    start,
                    end,
                )
            ).all()
        )

    def count(model, column, *conditions):
        return db.scalar(
            dates(
                select(func.count())
                .select_from(model)
                .where(model.tenant_id == tenant_id, *conditions),
                column,
                start,
                end,
            )
        )

    if db.bind.dialect.name == "postgresql":
        elapsed = func.extract(
            "epoch", WorkflowExecution.completed_at - WorkflowExecution.started_at
        )
    else:
        elapsed = (
            func.julianday(WorkflowExecution.completed_at)
            - func.julianday(WorkflowExecution.started_at)
        ) * 86400
    duration = db.scalar(
        dates(
            select(func.avg(elapsed)).where(
                WorkflowExecution.tenant_id == tenant_id,
                WorkflowExecution.status == "completed",
            ),
            WorkflowExecution.started_at,
            start,
            end,
        )
    )
    return {
        "orders": counts(Order, Order.created_at),
        "executions": counts(WorkflowExecution, WorkflowExecution.started_at),
        "pending_approvals": count(
            Approval, Approval.created_at, Approval.status == "pending"
        ),
        "import_failures": count(
            ImportRecord, ImportRecord.created_at, ImportRecord.status == "failed"
        ),
        "retry_requests": count(
            AuditEvent, AuditEvent.created_at, AuditEvent.action == "retry_requested"
        ),
        "average_completed_duration_seconds": float(duration)
        if duration is not None
        else None,
    }
