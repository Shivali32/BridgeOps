from datetime import UTC
from uuid import uuid4

from sqlalchemy import select

from app.models import Order, StepExecution, WorkflowExecution
from app.models.operations import AuditEvent, RecoveryRequest
from app.services.definition import WorkflowConflictError
from app.services.order import OrderNotFoundError, require_tenant
from app.services.providers import ProviderError
from app.services.workflow import get_execution, now, owns_execution, run_execution

MAX_ATTEMPTS = 3
STALE_SECONDS = 60


def audit(db, execution, action, previous, note, operator):
    db.add(
        AuditEvent(
            tenant_id=execution.tenant_id,
            execution_id=execution.id,
            action=action,
            previous_state=previous,
            new_state={
                "status": execution.status,
                "error_category": execution.error_category,
            },
            note=note,
            development_operator=operator,
        )
    )


def recover(db, tenant_id, execution_id, data, providers):
    require_tenant(db, tenant_id, active=True)
    execution = db.scalar(
        select(WorkflowExecution)
        .where(
            WorkflowExecution.id == execution_id,
            WorkflowExecution.tenant_id == tenant_id,
        )
        .with_for_update()
    )
    if execution is None:
        raise OrderNotFoundError("Execution not found.")
    payload = data.model_dump(mode="json")
    old = db.scalar(
        select(RecoveryRequest).where(
            RecoveryRequest.execution_id == execution_id,
            RecoveryRequest.tenant_id == tenant_id,
            RecoveryRequest.request_key == data.request_key,
        )
    )
    if old is not None:
        if old.payload != payload:
            raise WorkflowConflictError("Recovery key has different action data.")
        db.commit()
        return get_execution(db, tenant_id, execution_id)
    previous_state = {
        "status": execution.status,
        "error_category": execution.error_category,
    }
    if data.action == "investigated":
        db.add(
            RecoveryRequest(
                tenant_id=tenant_id,
                execution_id=execution_id,
                request_key=data.request_key,
                payload=payload,
            )
        )
        audit(
            db,
            execution,
            "investigated",
            previous_state,
            data.note,
            data.development_operator,
        )
        db.commit()
        return get_execution(db, tenant_id, execution_id)
    stale = (
        execution.status == "running"
        and (now() - execution.heartbeat_at.replace(tzinfo=UTC)).total_seconds()
        >= STALE_SECONDS
    )
    if execution.status == "running" and not (
        stale and data.action in ("reconcile", "verify_reference")
    ):
        raise WorkflowConflictError(
            "Execution is already running. Stale runs require reconciliation after 60 seconds."
        )
    if execution.status not in (
        "failed",
        "needs_attention",
        "running",
    ) or execution.error_category in ("approval_pending", "approval_rejected"):
        raise WorkflowConflictError(
            "Execution is not eligible for recovery. Use approval decisions when waiting for approval."
        )
    steps = list(
        db.scalars(
            select(StepExecution)
            .where(StepExecution.execution_id == execution_id)
            .order_by(StepExecution.started_at, StepExecution.attempt_number)
        )
    )
    latest = {s.step_name: s for s in sorted(steps, key=lambda s: s.attempt_number)}
    candidates = [
        s for s in latest.values() if s.status in ("failed", "unknown", "running")
    ]
    if not candidates:
        raise WorkflowConflictError("No unresolved step is available for recovery.")
    step = candidates[-1]
    specs = execution.definition_snapshot["steps"]
    kind = next(
        (
            s["type"] if isinstance(s, dict) else s
            for s in specs
            if (s["id"] if isinstance(s, dict) else s) == step.step_name
        ),
        None,
    )
    if kind not in ("inventory_check", "inventory_reservation", "fulfillment_request"):
        raise WorkflowConflictError(
            "Correct or reimport invalid input; this step cannot be retried."
        )
    if data.action == "verify_reference" and data.external_reference is None:
        raise WorkflowConflictError("An external reference is required.")
    if data.action == "retry" and (
        not step.retryable or step.attempt_number >= MAX_ATTEMPTS
    ):
        raise WorkflowConflictError(
            "Step is not retryable or its three-attempt limit was reached."
        )
    if kind == "inventory_check" and data.action != "retry":
        raise WorkflowConflictError(
            "Inventory checks have no external reservation to reconcile."
        )
    db.add(
        RecoveryRequest(
            tenant_id=tenant_id,
            execution_id=execution_id,
            request_key=data.request_key,
            payload=payload,
        )
    )
    execution.status, execution.error_message, execution.error_category = (
        "running",
        None,
        None,
    )
    execution.run_token, execution.heartbeat_at, execution.completed_at = (
        uuid4(),
        now(),
        None,
    )
    claim_token = execution.run_token
    order = db.get(Order, execution.order_id)
    order.status = "processing"
    audit(
        db,
        execution,
        "retry_requested" if data.action == "retry" else "reconciliation_requested",
        previous_state,
        data.note,
        data.development_operator,
    )
    operation_payload = dict(step.input_summary)
    db.commit()
    result = None
    if kind != "inventory_check":
        try:
            result = providers.lookup(
                kind,
                operation_payload,
                data.external_reference if data.action == "verify_reference" else None,
            )
        except ProviderError as exc:
            if not owns_execution(db, tenant_id, execution_id, claim_token):
                return get_execution(db, tenant_id, execution_id)
            execution.status = order.status = "needs_attention"
            execution.error_category, execution.error_message = exc.category, str(exc)
            execution.completed_at = now()
            audit(
                db,
                execution,
                "reconciliation_failed",
                {"status": "running"},
                str(exc),
                data.development_operator,
            )
            db.commit()
            return get_execution(db, tenant_id, execution_id)
        if not owns_execution(db, tenant_id, execution_id, claim_token):
            return get_execution(db, tenant_id, execution_id)
        if result is not None:
            db.add(
                StepExecution(
                    execution_id=execution_id,
                    step_name=step.step_name,
                    attempt_number=step.attempt_number + 1,
                    status="completed",
                    started_at=now(),
                    completed_at=now(),
                    input_summary=operation_payload,
                    output_summary={**result, "reconciled": True},
                    external_reference=result["id"],
                    idempotency_key=step.idempotency_key,
                )
            )
            audit(
                db,
                execution,
                "provider_result_verified",
                {"step_status": step.status},
                data.note,
                data.development_operator,
            )
            db.commit()
        elif data.action != "retry":
            execution.status = order.status = "needs_attention"
            execution.error_category, execution.error_message = (
                "timeout_unknown",
                "No matching provider operation was found. An explicit eligible retry is required.",
            )
            if step.status == "running":
                step.status, step.retryable, step.error_category = (
                    "unknown",
                    True,
                    "timeout_unknown",
                )
                step.completed_at = now()
            audit(
                db,
                execution,
                "provider_result_absent",
                {"status": "running"},
                data.note,
                data.development_operator,
            )
            db.commit()
            return get_execution(db, tenant_id, execution_id)
    return run_execution(db, tenant_id, execution_id, providers, claim_token)
