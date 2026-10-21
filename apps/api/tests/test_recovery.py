from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_workflow import FakeProviders

from app.models.operations import AuditEvent
from app.schemas.operations import RecoveryAction
from app.services.definition import WorkflowConflictError
from app.services.providers import ProviderError
from app.services.recovery import recover
from app.services.workflow import now, process_order, run_execution
from tests_helpers import make_order


class RecoveryProvider(FakeProviders):
    def __init__(self, db, found=False, fail=False):
        super().__init__(
            db,
            (
                "fulfillment_request",
                ProviderError("provider_unavailable", "HTTP 503", retryable=True),
            )
            if fail
            else None,
        )
        self.found = found
        self.lookups = 0

    def lookup(self, kind, payload, reference=None):
        assert not self.db.in_transaction()
        self.lookups += 1
        return (
            {**payload, "id": str(reference or uuid4()), "status": "accepted"}
            if self.found
            else None
        )


def failed(db, unknown=False):
    t, order = make_order(db)
    provider = FakeProviders(
        db,
        (
            "fulfillment_request",
            ProviderError(
                "timeout_unknown" if unknown else "provider_unavailable",
                "Provider response unavailable",
                unknown=unknown,
                retryable=True,
            ),
        ),
    )
    execution = process_order(db, t.id, order.id, provider)
    return t, order, execution


def action(kind="retry", key=None, **kwargs):
    return RecoveryAction(
        request_key=key or str(uuid4()),
        action=kind,
        note="Investigated local failure",
        **kwargs,
    )


def test_retry_preserves_completed_steps_and_is_request_idempotent(session):
    t, order, execution = failed(session)
    successful_ids = [s.id for s in execution.steps[:2]]
    provider = RecoveryProvider(session)
    data = action()
    result = recover(session, t.id, execution.id, data, provider)
    assert result.status == order.status == "completed"
    assert provider.calls == ["fulfillment_request"] and provider.lookups == 1
    assert [s.id for s in result.steps[:2]] == successful_ids
    fulfillment = [s for s in result.steps if s.step_name == "fulfillment_request"]
    assert [s.status for s in fulfillment] == ["failed", "completed"]
    assert [s.attempt_number for s in fulfillment] == [1, 2]
    assert recover(session, t.id, execution.id, data, provider).id == execution.id
    assert len(provider.calls) == 1
    with pytest.raises(WorkflowConflictError, match="different action data"):
        recover(
            session,
            t.id,
            execution.id,
            action("investigated", data.request_key),
            provider,
        )
    assert session.scalar(
        select(AuditEvent).where(AuditEvent.action == "retry_requested")
    )


def test_unknown_outcome_is_reconciled_without_repeating_fulfillment(session):
    t, _, execution = failed(session, unknown=True)
    provider = RecoveryProvider(session, found=True)
    result = recover(session, t.id, execution.id, action("reconcile"), provider)
    assert result.status == "completed" and not provider.calls
    assert result.steps[-1].output_summary["reconciled"]
    assert result.steps[-2].status == "unknown"


def test_absent_outcome_requires_explicit_retry(session):
    t, _, execution = failed(session, unknown=True)
    provider = RecoveryProvider(session)
    result = recover(session, t.id, execution.id, action("reconcile"), provider)
    assert result.status == "needs_attention" and provider.calls == []
    result = recover(session, t.id, execution.id, action("retry"), provider)
    assert result.status == "completed" and provider.calls == ["fulfillment_request"]


def test_retry_limit_and_nonretryable_failure(session):
    t, _, execution = failed(session)
    provider = RecoveryProvider(session, fail=True)
    for _ in range(2):
        recover(session, t.id, execution.id, action(), provider)
    with pytest.raises(WorkflowConflictError, match="three-attempt"):
        recover(session, t.id, execution.id, action(), provider)
    assert len(provider.calls) == 2


def test_investigation_note_does_not_complete_execution(session):
    t, _, execution = failed(session)
    provider = RecoveryProvider(session)
    result = recover(session, t.id, execution.id, action("investigated"), provider)
    assert result.status == "failed" and not provider.calls and provider.lookups == 0
    event = session.scalar(select(AuditEvent))
    assert event.previous_state["status"] == event.new_state["status"] == "failed"


def test_stale_worker_is_fenced_after_reconciliation(session):
    t, _, execution = failed(session, unknown=True)
    old_token = execution.run_token
    execution.status = "running"
    execution.error_category = None
    execution.heartbeat_at = now() - timedelta(seconds=120)
    execution.steps[-1].status = "running"
    session.commit()
    with pytest.raises(WorkflowConflictError):
        recover(session, t.id, execution.id, action("retry"), RecoveryProvider(session))
    provider = RecoveryProvider(session, found=True)
    assert (
        recover(session, t.id, execution.id, action("reconcile"), provider).status
        == "completed"
    )
    obsolete = RecoveryProvider(session)
    assert (
        run_execution(session, t.id, execution.id, obsolete, old_token).status
        == "completed"
    )
    assert not obsolete.calls


@pytest.mark.parametrize("same_key", [True, False])
def test_postgres_concurrent_retry_requests(pg_engine, same_key):
    with Session(pg_engine, expire_on_commit=False) as db:
        t, _, execution = failed(db)
        tenant_id, execution_id = t.id, execution.id
    data = action(key="shared-retry")
    barrier = Barrier(2)
    calls = []

    def retry(n):
        with Session(pg_engine, expire_on_commit=False) as db:
            provider = RecoveryProvider(db)
            barrier.wait(timeout=10)
            try:
                result = recover(
                    db,
                    tenant_id,
                    execution_id,
                    data if same_key else action(key=f"retry-{n}"),
                    provider,
                )
                calls.extend(provider.calls)
                return result.id
            except WorkflowConflictError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(retry, range(2)))
    assert calls == ["fulfillment_request"]
    assert ids[0] == ids[1] if same_key else ids.count("conflict") == 1


def test_nonretryable_failure_rejects_retry(session):
    tenant, order = make_order(session)
    provider = FakeProviders(
        session,
        ("inventory_check", ProviderError("insufficient_stock", "Insufficient stock")),
    )
    execution = process_order(session, tenant.id, order.id, provider)
    with pytest.raises(WorkflowConflictError, match="not retryable"):
        recover(
            session, tenant.id, execution.id, action("retry"), RecoveryProvider(session)
        )
