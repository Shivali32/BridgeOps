import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from test_approvals import approval_definition
from test_workflow import FakeProviders

from app.messaging.publisher import publish_one
from app.messaging.worker import handle_message
from app.models import StepExecution, WorkflowExecution
from app.models.definition import Approval
from app.models.messaging import EventReceipt, OutboxEvent, QuarantinedMessage
from app.schemas.definition import ApprovalDecision, DefinitionCreate
from app.schemas.operations import RecoveryAction
from app.services.definition import WorkflowConflictError, save_definition
from app.services.providers import ProviderError
from app.services.recovery import recover
from app.services.workflow import decide_approval, now, process_order
from tests_helpers import make_order


def message(db, execution):
    return json.dumps(db.get(OutboxEvent, execution.active_event_id).payload).encode()


def deliver(db, raw, provider=None, offset=0):
    return handle_message(db, raw, ("work", 0, offset), provider or FakeProviders(db))


def queued(db, provider=None):
    tenant, order = make_order(db)
    execution = process_order(
        db, tenant.id, order.id, provider or FakeProviders(db), queued=True
    )
    return tenant, order, execution


def test_queue_is_atomic_and_clicks_are_idempotent(session):
    tenant, order, execution = queued(session)
    assert execution.status == "pending" and order.status == "queued"
    assert execution.started_at is None and execution.steps == []
    original = message(session, execution)
    assert (
        process_order(
            session, tenant.id, order.id, FakeProviders(session), queued=True
        ).id
        == execution.id
    )
    assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 1
    provider = FakeProviders(session)
    assert deliver(session, original, provider)
    assert execution.status == "completed"
    assert deliver(session, original, provider)
    assert len(provider.calls) == 3
    assert session.scalar(select(func.count()).select_from(EventReceipt)) == 1


def test_queue_transaction_rolls_back_whole_request(session, monkeypatch):
    tenant, order = make_order(session)

    def fail_commit():
        raise RuntimeError("Database write failed")

    with monkeypatch.context() as patch:
        patch.setattr(session, "commit", fail_commit)
        with pytest.raises(RuntimeError):
            process_order(
                session, tenant.id, order.id, FakeProviders(session), queued=True
            )
    session.rollback()
    assert session.scalar(select(func.count()).select_from(WorkflowExecution)) == 0
    assert session.scalar(select(func.count()).select_from(OutboxEvent)) == 0
    session.refresh(order)
    assert order.status == "received"


def test_api_queues_without_needing_kafka(api_client, engine, monkeypatch):
    monkeypatch.setenv("WORKFLOW_MODE", "kafka")
    with Session(engine, expire_on_commit=False) as db:
        tenant, order = make_order(db)
        path = f"/api/v1/tenants/{tenant.id}/orders/{order.id}/process"
    first = api_client.post(path)
    assert first.status_code == 202 and first.json()["status"] == "pending"
    assert api_client.post(path).json()["id"] == first.json()["id"]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 1


class Producer:
    def __init__(self, failure=False):
        self.failure, self.sent = failure, []

    def produce(self, topic, *, key, value, on_delivery):
        self.sent.append((topic, key, value))
        on_delivery("unavailable" if self.failure else None, None)

    def flush(self, timeout):
        return 0


def test_publisher_retries_unconfirmed_delivery(session):
    _, _, execution = queued(session)
    producer = Producer(failure=True)
    assert publish_one(session, producer)
    event = session.get(OutboxEvent, execution.active_event_id)
    assert event.published_at is None and event.attempts == 1
    assert event.last_error and not publish_one(session, producer)
    event.next_attempt_at = now() - timedelta(seconds=1)
    session.commit()
    producer.failure = False
    assert publish_one(session, producer)
    assert event.published_at is not None and event.last_error is None
    assert len(producer.sent) == 2 and producer.sent[0] == producer.sent[1]


@pytest.mark.parametrize("raw", [b"not json", b'{"schema_version":99}', b"null"])
def test_malformed_messages_are_saved_before_acknowledging(session, raw):
    assert deliver(session, raw)
    assert deliver(session, raw)
    assert session.scalar(select(func.count()).select_from(QuarantinedMessage)) == 1


def test_forged_tenant_and_unknown_events_do_not_run(session):
    _, _, execution = queued(session)
    payload = json.loads(message(session, execution))
    payload["tenant_id"] = str(uuid4())
    provider = FakeProviders(session)
    assert deliver(session, json.dumps(payload).encode(), provider)
    payload["event_id"] = str(uuid4())
    assert deliver(session, json.dumps(payload).encode(), provider, offset=1)
    assert not provider.calls and execution.status == "pending"


def test_approval_resume_is_queued_with_original_snapshot(session):
    tenant, order = make_order(session)
    save_definition(session, tenant.id, DefinitionCreate(**approval_definition()))
    provider = FakeProviders(session)
    execution = process_order(session, tenant.id, order.id, provider, queued=True)
    original = message(session, execution)
    assert deliver(session, original, provider)
    approval = session.scalar(select(Approval))
    assert execution.status == "needs_attention" and not provider.calls
    decide_approval(
        session,
        tenant.id,
        approval.id,
        ApprovalDecision(decision="approve"),
        provider,
        queued=True,
    )
    assert execution.status == "pending" and not provider.calls
    assert deliver(
        session, original, provider
    )  # Previous command cannot undo the decision.
    resumed = message(session, execution)
    assert resumed != original and deliver(session, resumed, provider, offset=1)
    assert execution.status == "completed" and len(provider.calls) == 3


def test_queued_retry_preserves_successful_steps(session):
    tenant, _, execution = queued(session)
    provider = FakeProviders(
        session,
        (
            "fulfillment_request",
            ProviderError("provider_unavailable", "Unavailable", retryable=True),
        ),
    )
    deliver(session, message(session, execution), provider)
    reservation = execution.steps[1].external_reference
    assert execution.status == "failed"
    provider.failure = None
    provider.lookup = lambda *_: None
    data = RecoveryAction(
        request_key="retry-1", action="retry", note="Provider restored"
    )
    recover(session, tenant.id, execution.id, data, provider, queued=True)
    event = message(session, execution)
    assert execution.status == "pending" and len(provider.calls) == 3
    assert (
        recover(session, tenant.id, execution.id, data, provider, queued=True).status
        == "pending"
    )
    assert message(session, execution) == event
    with pytest.raises(WorkflowConflictError):
        recover(
            session,
            tenant.id,
            execution.id,
            data.model_copy(update={"request_key": "another"}),
            provider,
            queued=True,
        )
    session.rollback()
    assert deliver(session, event, provider, offset=1)
    assert (
        execution.status == "completed"
        and provider.calls.count("inventory_reservation") == 1
    )
    assert execution.steps[1].external_reference == reservation


@pytest.mark.parametrize("accepted", [True, False])
def test_worker_crash_reconciles_before_any_repeated_write(session, accepted):
    _, order, execution = queued(session)
    raw = message(session, execution)
    execution.status, execution.run_token = "running", uuid4()
    execution.heartbeat_at = now() - timedelta(seconds=61)
    step = StepExecution(
        execution_id=execution.id,
        step_name="inventory_reservation",
        status="running",
        attempt_number=1,
        input_summary={
            "tenant_id": str(execution.tenant_id),
            "items": [{"sku": "A", "quantity": 2}],
            "idempotency_key": "same-key",
        },
        idempotency_key="same-key",
        started_at=now(),
    )
    session.add(step)
    session.commit()
    provider = FakeProviders(session)
    provider.lookup = lambda *_: (
        {"id": str(uuid4()), "status": "reserved"} if accepted else None
    )
    assert deliver(session, raw, provider)
    assert "inventory_reservation" not in provider.calls
    assert execution.status == ("completed" if accepted else "needs_attention")
    assert order.status == execution.status
    if accepted:
        assert step.output_summary["reconciled"]
    else:
        assert step.status == "unknown" and step.retryable


def test_live_worker_claim_is_not_acknowledged_or_stolen(session):
    _, _, execution = queued(session)
    raw = message(session, execution)
    execution.status, execution.run_token, execution.heartbeat_at = (
        "running",
        uuid4(),
        now(),
    )
    token = execution.run_token
    session.commit()
    assert not deliver(session, raw)
    assert execution.run_token == token and session.scalar(select(EventReceipt)) is None


def test_postgres_simultaneous_queue_requests(pg_engine):
    with Session(pg_engine, expire_on_commit=False) as db:
        tenant, order = make_order(db)
        tenant_id, order_id = tenant.id, order.id
    barrier = Barrier(2)

    def submit(_):
        with Session(pg_engine, expire_on_commit=False) as db:
            barrier.wait(timeout=10)
            return process_order(
                db, tenant_id, order_id, FakeProviders(db), queued=True
            ).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(submit, range(2)))
    assert ids[0] == ids[1]
    with Session(pg_engine) as db:
        assert db.scalar(select(func.count()).select_from(OutboxEvent)) == 1
