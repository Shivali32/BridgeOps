from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Order, StepExecution, WorkflowExecution
from app.services.order import OrderNotFoundError, require_tenant
from app.services.providers import ProviderError, Providers

STANDARD_STEPS = ["inventory_check", "inventory_reservation", "fulfillment_request"]


def now():
    return datetime.now(UTC)


def get_execution(db: Session, tenant_id: UUID, execution_id: UUID):
    value = db.scalar(
        select(WorkflowExecution)
        .options(selectinload(WorkflowExecution.steps))
        .where(
            WorkflowExecution.id == execution_id,
            WorkflowExecution.tenant_id == tenant_id,
        )
    )
    if value is None:
        raise OrderNotFoundError("Execution not found.")
    value.steps.sort(
        key=lambda s: (
            (s.started_at or now()).replace(tzinfo=UTC).timestamp(),
            s.attempt_number,
        )
    )
    return value


def list_executions(db: Session, tenant_id: UUID, order_id: UUID):
    from app.services.order import get_order

    get_order(db, tenant_id, order_id)
    return list(
        db.scalars(
            select(WorkflowExecution)
            .options(selectinload(WorkflowExecution.steps))
            .where(
                WorkflowExecution.tenant_id == tenant_id,
                WorkflowExecution.order_id == order_id,
            )
            .order_by(WorkflowExecution.started_at.desc())
        )
    )


def process_order(db: Session, tenant_id: UUID, order_id: UUID, providers: Providers):
    require_tenant(db, tenant_id, active=True)
    # Serialize claims for an order. Commit before making any external request.
    order = db.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id, Order.tenant_id == tenant_id)
        .with_for_update()
    )
    if order is None:
        raise OrderNotFoundError("Order not found.")
    existing = db.scalar(
        select(WorkflowExecution).where(
            WorkflowExecution.order_id == order_id,
            WorkflowExecution.tenant_id == tenant_id,
        )
    )
    if existing is not None:
        db.commit()
        return get_execution(db, tenant_id, existing.id)
    execution = WorkflowExecution(
        tenant_id=tenant_id,
        order_id=order_id,
        status="running",
        started_at=now(),
        definition_snapshot={
            "name": "Standard fulfillment",
            "version": 1,
            "steps": STANDARD_STEPS,
        },
    )
    order.status = "processing"
    db.add(execution)
    items = [{"sku": x.sku, "quantity": x.quantity} for x in order.items]
    db.commit()
    execution_id = execution.id
    reservation_id = None
    for name in STANDARD_STEPS:
        payload = {"tenant_id": str(tenant_id), "items": items}
        key = f"order-{order_id}-{name}"
        if name != "inventory_check":
            payload["idempotency_key"] = key
        if name == "fulfillment_request":
            payload.update(order_id=str(order_id), reservation_id=reservation_id)
        step = StepExecution(
            execution_id=execution_id,
            step_name=name,
            status="running",
            started_at=now(),
            input_summary=payload,
            idempotency_key=key if name != "inventory_check" else None,
        )
        db.add(step)
        db.commit()
        # No active transaction while this synchronous HTTP call runs.
        try:
            result = providers.call(name, payload)
        except ProviderError as exc:
            step.status = "unknown" if exc.unknown else "failed"
            step.error_message = str(exc)
            step.error_category = exc.category
            step.retryable = exc.retryable
            step.completed_at = now()
            execution.status = "needs_attention" if exc.unknown else "failed"
            execution.error_message = str(exc)
            execution.error_category = exc.category
            execution.completed_at = now()
            order.status = (
                "needs_attention" if exc.unknown or reservation_id else "failed"
            )
            db.commit()
            break
        step.status = "completed"
        step.completed_at = now()
        step.output_summary = result
        if name != "inventory_check":
            step.external_reference = result["id"]
        if name == "inventory_reservation":
            reservation_id = result["id"]
        db.commit()
    else:
        order.status = execution.status = "completed"
        execution.completed_at = now()
        db.commit()
    return get_execution(db, tenant_id, execution_id)
