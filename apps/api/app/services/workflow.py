from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Order, StepExecution, WorkflowExecution
from app.models.definition import Approval, WorkflowDefinition
from app.models.integration import ImportRecord, Integration
from app.schemas.definition import DefinitionCreate
from app.services.definition import WorkflowConflictError
from app.services.order import OrderNotFoundError, require_tenant
from app.services.providers import ProviderError, Providers
from app.services.rules import evaluate

STANDARD_STEPS = ["inventory_check", "inventory_reservation", "fulfillment_request"]


def now():
    return datetime.now(UTC)


def get_execution(db: Session, tenant_id: UUID, execution_id: UUID):
    value = db.scalar(
        select(WorkflowExecution)
        .options(selectinload(WorkflowExecution.steps))
        .execution_options(populate_existing=True)
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


def resolve_snapshot(db, tenant_id, order):
    imported = db.scalar(
        select(ImportRecord)
        .where(
            ImportRecord.tenant_id == tenant_id,
            ImportRecord.order_id == order.id,
            ImportRecord.status == "succeeded",
        )
        .order_by(ImportRecord.created_at, ImportRecord.id)
        .limit(1)
    )
    integration = db.get(Integration, imported.integration_id) if imported else None
    source = {
        "source_connector": integration.connector_type if integration else "direct",
        "source": integration.name if integration else "Order API",
        "integration_id": str(integration.id) if integration else None,
    }
    if integration and integration.workflow_id:
        definition = db.scalar(
            select(WorkflowDefinition).where(
                WorkflowDefinition.id == integration.workflow_id,
                WorkflowDefinition.tenant_id == tenant_id,
            )
        )
        if definition is None or not definition.enabled:
            raise WorkflowConflictError("Assigned workflow is missing or disabled.")
    else:
        definition = db.scalar(
            select(WorkflowDefinition).where(
                WorkflowDefinition.tenant_id == tenant_id,
                WorkflowDefinition.enabled.is_(True),
                WorkflowDefinition.is_default.is_(True),
            )
        )
    if definition:
        snapshot = {
            "id": str(definition.id),
            "version": definition.version,
            **definition.configuration,
        }
    else:
        snapshot = {
            "name": "Standard fulfillment",
            "version": 1,
            "trigger": "order_processing",
            "steps": [{"id": kind, "type": kind} for kind in STANDARD_STEPS],
        }
    snapshot["source"] = source
    snapshot["order_items"] = [
        {
            "sku": i.sku,
            "quantity": i.quantity,
            "unit_price": str(i.unit_price) if i.unit_price is not None else None,
        }
        for i in order.items
    ]
    return snapshot


def process_order(db: Session, tenant_id: UUID, order_id: UUID, providers: Providers):
    require_tenant(db, tenant_id, active=True)
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
    snapshot = resolve_snapshot(db, tenant_id, order)
    execution = WorkflowExecution(
        tenant_id=tenant_id,
        order_id=order_id,
        status="running",
        run_token=uuid4(),
        heartbeat_at=now(),
        started_at=now(),
        definition_snapshot=snapshot,
    )
    order.status = "processing"
    db.add(execution)
    db.flush()
    execution_id, claim_token = execution.id, execution.run_token
    db.commit()
    return run_execution(db, tenant_id, execution_id, providers, claim_token)


def fail_step(db, execution, order, step, exc, reserved):
    step.status = "unknown" if exc.unknown else "failed"
    step.error_message, step.error_category = str(exc), exc.category
    step.retryable, step.completed_at = exc.retryable, now()
    execution.status = (
        "needs_attention"
        if exc.unknown or exc.category == "validation_error"
        else "failed"
    )
    execution.error_message, execution.error_category = str(exc), exc.category
    execution.completed_at = now()
    order.status = (
        "needs_attention"
        if exc.unknown or reserved or exc.category == "validation_error"
        else "failed"
    )
    db.commit()


def run_execution(db, tenant_id, execution_id, providers, claim_token):
    """Only called after a committed exclusive claim by process/decision/retry."""
    execution = get_execution(db, tenant_id, execution_id)
    order = db.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == execution.order_id, Order.tenant_id == tenant_id)
    )
    snapshot = execution.definition_snapshot
    raw_steps = snapshot["steps"]
    if raw_steps and isinstance(raw_steps[0], str):  # Stage 2 historical snapshots
        raw_steps = [{"id": x, "type": x} for x in raw_steps]
    specs = DefinitionCreate(name=snapshot["name"], steps=raw_steps).steps
    priced_items = snapshot.get("order_items") or [
        {
            "sku": i.sku,
            "quantity": i.quantity,
            "unit_price": str(i.unit_price) if i.unit_price is not None else None,
        }
        for i in order.items
    ]
    items = [{"sku": i["sku"], "quantity": i["quantity"]} for i in priced_items]
    latest = {
        s.step_name: s for s in sorted(execution.steps, key=lambda s: s.attempt_number)
    }
    results = {
        name: step.output_summary
        for name, step in latest.items()
        if step.status == "completed"
    }
    reservation_id = next(
        (
            results[s.id]["id"]
            for s in specs
            if s.type == "inventory_reservation" and s.id in results
        ),
        None,
    )
    for spec in specs:
        if not owns_execution(db, tenant_id, execution_id, claim_token):
            return get_execution(db, tenant_id, execution_id)
        execution.heartbeat_at = now()
        previous = latest.get(spec.id)
        if previous and previous.status in ("completed", "skipped"):
            continue
        if previous and previous.status == "pending":
            db.commit()
            return get_execution(db, tenant_id, execution_id)
        key = f"order-{order.id}-{spec.type}"
        payload = {"tenant_id": str(tenant_id), "items": items}
        if spec.type in ("inventory_reservation", "fulfillment_request"):
            payload["idempotency_key"] = key
        if spec.type == "fulfillment_request":
            payload.update(order_id=str(order.id), reservation_id=reservation_id)
        step = StepExecution(
            execution_id=execution_id,
            step_name=spec.id,
            status="running",
            started_at=now(),
            attempt_number=(previous.attempt_number + 1 if previous else 1),
            input_summary=payload,
            idempotency_key=key
            if spec.type in ("inventory_reservation", "fulfillment_request")
            else None,
        )
        db.add(step)
        if (
            spec.when
            and results[spec.when.condition_step]["matched"] != spec.when.matches
        ):
            step.status, step.completed_at = "skipped", now()
            step.output_summary = {"reason": "Condition branch did not match"}
            db.commit()
            continue
        if spec.type == "approval":
            approval = Approval(
                tenant_id=tenant_id,
                execution_id=execution_id,
                step_name=spec.id,
                reason=spec.reason,
            )
            db.add(approval)
            db.flush()
            step.status = "pending"
            step.output_summary = {
                "approval_id": str(approval.id),
                "reason": spec.reason,
            }
            execution.status = order.status = "needs_attention"
            execution.error_category = "approval_pending"
            execution.error_message = spec.reason
            db.commit()
            return get_execution(db, tenant_id, execution_id)
        db.commit()
        try:
            result = (
                {
                    "matched": evaluate(
                        spec.rules, priced_items, snapshot.get("source", {})
                    )
                }
                if spec.type == "condition"
                else providers.call(spec.type, payload)
            )
        except ProviderError as exc:
            if not owns_execution(db, tenant_id, execution_id, claim_token):
                return get_execution(db, tenant_id, execution_id)
            fail_step(db, execution, order, step, exc, reservation_id)
            return get_execution(db, tenant_id, execution_id)
        if not owns_execution(db, tenant_id, execution_id, claim_token):
            return get_execution(db, tenant_id, execution_id)
        execution.heartbeat_at = now()
        step.status, step.completed_at = "completed", now()
        step.output_summary = result
        results[spec.id] = result
        if spec.type in ("inventory_reservation", "fulfillment_request"):
            step.external_reference = result["id"]
        if spec.type == "inventory_reservation":
            reservation_id = result["id"]
        db.commit()
    order.status = execution.status = "completed"
    execution.completed_at = now()
    execution.error_message = execution.error_category = None
    db.commit()
    return get_execution(db, tenant_id, execution_id)


def decide_approval(db, tenant_id, approval_id, data, providers):
    require_tenant(db, tenant_id, active=True)
    approval = db.scalar(
        select(Approval).where(
            Approval.id == approval_id, Approval.tenant_id == tenant_id
        )
    )
    if approval is None:
        raise OrderNotFoundError("Approval not found.")
    execution = db.scalar(
        select(WorkflowExecution)
        .where(
            WorkflowExecution.id == approval.execution_id,
            WorkflowExecution.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    # Reload under the execution lock so a competing decision observes the winner.
    db.refresh(approval)
    decision = "approved" if data.decision == "approve" else "rejected"
    if approval.status != "pending":
        if approval.status != decision:
            raise WorkflowConflictError(
                "This approval already has a different decision."
            )
        db.commit()
        return get_execution(db, tenant_id, execution.id)
    if (
        execution.status != "needs_attention"
        or execution.error_category != "approval_pending"
    ):
        raise WorkflowConflictError("Execution is not waiting for this approval.")
    step = db.scalar(
        select(StepExecution)
        .where(
            StepExecution.execution_id == execution.id,
            StepExecution.step_name == approval.step_name,
        )
        .order_by(StepExecution.attempt_number.desc())
        .limit(1)
    )
    order = db.get(Order, execution.order_id)
    previous_approval_state = {
        "status": execution.status,
        "approval_status": approval.status,
    }
    approval.status, approval.decided_at = decision, now()
    approval.decision_note, approval.development_operator = (
        data.note,
        data.development_operator,
    )
    step.status, step.completed_at = (
        ("completed" if decision == "approved" else "failed"),
        now(),
    )
    step.output_summary = {
        **step.output_summary,
        "decision": decision,
        "note": data.note,
        "development_operator": data.development_operator,
    }
    execution.error_message = execution.error_category = None
    execution_id = execution.id
    execution.run_token, execution.heartbeat_at = uuid4(), now()
    claim_token = execution.run_token
    if decision == "rejected":
        execution.status = order.status = "failed"
        execution.completed_at = now()
        execution.error_category = step.error_category = "approval_rejected"
        execution.error_message = step.error_message = "Operator rejected the order."
    else:
        execution.status, order.status = "running", "processing"
    from app.models.operations import AuditEvent

    db.add(
        AuditEvent(
            tenant_id=tenant_id,
            execution_id=execution_id,
            action="approval_decision",
            previous_state=previous_approval_state,
            new_state={"status": execution.status, "approval_status": decision},
            note=data.note,
            development_operator=data.development_operator,
        )
    )
    db.commit()
    return (
        run_execution(db, tenant_id, execution_id, providers, claim_token)
        if decision == "approved"
        else get_execution(db, tenant_id, execution_id)
    )


def owns_execution(db, tenant_id, execution_id, claim_token):
    token = db.scalar(
        select(WorkflowExecution.run_token)
        .where(
            WorkflowExecution.id == execution_id,
            WorkflowExecution.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if token != claim_token:
        db.rollback()
        return False
    return True
