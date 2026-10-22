"""Durable at-least-once workflow consumer. Run with python -m app.messaging.worker."""

import hashlib
import logging
import os
import signal
import threading
from datetime import UTC
from uuid import uuid4

from confluent_kafka import Consumer, KafkaException, TopicPartition
from pydantic import ValidationError
from sqlalchemy import select

from app.db import SessionLocal
from app.messaging.contracts import WorkEvent, topic
from app.models import Order, StepExecution, Tenant, WorkflowExecution
from app.models.messaging import EventReceipt, OutboxEvent, QuarantinedMessage
from app.models.operations import RecoveryRequest
from app.schemas.operations import RecoveryAction
from app.services.providers import ProviderError, Providers
from app.services.recovery import STALE_SECONDS, continue_recovery
from app.services.workflow import get_execution, now, owns_execution, run_execution

log = logging.getLogger(__name__)


def quarantine(db, raw, position, reason):
    name, partition, offset = position
    existing = db.scalar(
        select(QuarantinedMessage.id).where(
            QuarantinedMessage.topic == name,
            QuarantinedMessage.partition == partition,
            QuarantinedMessage.offset == offset,
        )
    )
    if not existing:
        db.add(
            QuarantinedMessage(
                topic=name,
                partition=partition,
                offset=offset,
                payload_digest=hashlib.sha256(raw or b"").hexdigest(),
                reason=reason,
            )
        )
    db.commit()
    log.warning("Quarantined message %s/%s/%s: %s", name, partition, offset, reason)
    return True


def receipt(db, event):
    if db.get(EventReceipt, event.event_id) is None:
        db.add(EventReceipt(event_id=event.event_id))
    db.commit()
    return True


def reconcile_interrupted(db, execution, providers, claim_token):
    """Only read a provider after a crash; an uncertain write needs operator recovery."""
    for step in list(execution.steps):
        if step.status != "running" or not step.idempotency_key:
            continue
        specs = execution.definition_snapshot["steps"]
        kind = next(
            (
                s["type"] if isinstance(s, dict) else s
                for s in specs
                if (s["id"] if isinstance(s, dict) else s) == step.step_name
            ),
            None,
        )
        payload = dict(step.input_summary)
        db.commit()
        try:
            result = providers.lookup(kind, payload)
        except ProviderError:
            result = None
        if not owns_execution(db, execution.tenant_id, execution.id, claim_token):
            return False
        if result is None:
            step.status, step.retryable = "unknown", True
            step.error_category, step.error_message = (
                "timeout_unknown",
                "Worker interrupted; provider outcome needs reconciliation.",
            )
            step.completed_at = now()
            execution.status = "needs_attention"
            execution.completed_at = now()
            execution.error_category, execution.error_message = (
                step.error_category,
                step.error_message,
            )
            db.get(Order, execution.order_id).status = "needs_attention"
            db.commit()
            return False
        step.status, step.completed_at = "completed", now()
        step.output_summary = {**result, "reconciled": True}
        step.external_reference = result["id"]
        db.commit()
    return True


def handle_message(db, raw, position, providers=None):
    """True means a durable outcome exists and this Kafka offset can be committed."""
    try:
        event = WorkEvent.model_validate_json(raw)
    except (ValidationError, ValueError, TypeError):
        return quarantine(
            db, raw, position, "Invalid event schema or unsupported version"
        )
    saved = db.get(OutboxEvent, event.event_id)
    if saved is None or saved.payload != event.model_dump(mode="json"):
        return quarantine(
            db, raw, position, "Event does not match a durable outbox command"
        )
    execution = db.scalar(
        select(WorkflowExecution)
        .where(
            WorkflowExecution.id == event.execution_id,
            WorkflowExecution.tenant_id == event.tenant_id,
        )
        .with_for_update()
    )
    if execution is None or execution.order_id != event.order_id:
        return quarantine(db, raw, position, "Execution ownership mismatch")
    if db.get(EventReceipt, event.event_id) is not None:
        db.commit()
        return True
    # Older deliveries must not undo a later approval/recovery command.
    if execution.active_event_id != event.event_id or execution.status not in (
        "pending",
        "running",
    ):
        return receipt(db, event)
    interrupted = execution.status == "running"
    if (
        interrupted
        and (now() - execution.heartbeat_at.replace(tzinfo=UTC)).total_seconds()
        < STALE_SECONDS
    ):
        db.rollback()
        return False
    tenant = db.get(Tenant, event.tenant_id)
    if not tenant or not tenant.is_active:
        execution.status, execution.error_category = (
            "needs_attention",
            "tenant_inactive",
        )
        execution.error_message = "Retailer was deactivated before processing."
        db.get(Order, event.order_id).status = "needs_attention"
        return receipt(db, event)
    execution.run_token, execution.heartbeat_at = uuid4(), now()
    token = execution.run_token
    execution.started_at = execution.started_at or now()
    execution.status = "running"
    db.get(Order, event.order_id).status = "processing"
    db.commit()
    providers = providers or Providers()
    execution = get_execution(db, event.tenant_id, event.execution_id)
    if interrupted and not reconcile_interrupted(db, execution, providers, token):
        execution = get_execution(db, event.tenant_id, event.execution_id)
        if execution.status in ("pending", "running"):
            db.rollback()
            return False
        return receipt(db, event)
    if event.kind == "recover":
        request = db.get(RecoveryRequest, event.recovery_request_id)
        step = db.get(StepExecution, event.step_id)
        if (
            request is None
            or step is None
            or request.tenant_id != event.tenant_id
            or request.execution_id != execution.id
            or step.execution_id != execution.id
        ):
            raise RuntimeError(
                "Durable recovery command refers to missing recovery data"
            )
        data = RecoveryAction.model_validate(request.payload)
        continue_recovery(db, execution, step, event.step_kind, data, providers, token)
    else:
        db.commit()  # Provider calls must not hold read transactions open.
        run_execution(db, event.tenant_id, event.execution_id, providers, token)
    # Results and pause/failure state are durable before acknowledging Kafka.
    execution = get_execution(db, event.tenant_id, event.execution_id)
    if execution.status == "running":
        db.rollback()
        return False
    return receipt(db, event)


def main():
    logging.basicConfig(level=logging.INFO)
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    consumer = Consumer(
        {
            "bootstrap.servers": os.getenv("KAFKA_BOOTSTRAP_SERVERS", "127.0.0.1:9092"),
            "group.id": os.getenv("KAFKA_WORKER_GROUP", "bridgops-workflows-v1"),
            "enable.auto.commit": False,
            "enable.auto.offset.store": False,
            "auto.offset.reset": "earliest",
            "max.poll.interval.ms": 180000,
            "allow.auto.create.topics": False,
        }
    )
    consumer.subscribe([topic()])
    try:
        while not stop.is_set():
            message = consumer.poll(1)
            if message is None:
                continue
            if message.error():
                raise KafkaException(message.error())
            position = (message.topic(), message.partition(), message.offset())
            with SessionLocal() as db:
                done = handle_message(db, message.value(), position)
            if done:
                consumer.commit(message=message, asynchronous=False)
            else:
                # Do not advance past an in-flight execution owned by another worker.
                consumer.seek(TopicPartition(*position))
                stop.wait(1)
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
