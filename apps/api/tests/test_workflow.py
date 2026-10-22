from uuid import uuid4

import httpx
import pytest
from sqlalchemy import func, select

from app.models import StepExecution, WorkflowExecution
from app.services.providers import ProviderError, Providers
from app.services.workflow import process_order
from tests_helpers import make_order


class FakeProviders:
    def __init__(self, db, failure=None):
        self.db = db
        self.failure = failure
        self.calls = []

    def call(self, name, payload):
        assert not self.db.in_transaction(), "HTTP must run outside DB transactions"
        self.calls.append(name)
        if self.failure and name == self.failure[0]:
            raise self.failure[1]
        return (
            {"available": True}
            if name == "inventory_check"
            else {
                "id": str(uuid4()),
                "status": "reserved" if name == "inventory_reservation" else "accepted",
            }
        )


def test_workflow_success_and_duplicate(session):
    t, order = make_order(session)
    provider = FakeProviders(session)
    result = process_order(session, t.id, order.id, provider)
    assert result.status == order.status == "completed"
    assert [s.status for s in result.steps] == ["completed"] * 3
    assert result.steps[2].output_summary["status"] == "accepted"
    assert len(provider.calls) == 3
    again = process_order(session, t.id, order.id, provider)
    assert again.id == result.id and len(provider.calls) == 3
    assert session.scalar(select(func.count()).select_from(WorkflowExecution)) == 1


@pytest.mark.parametrize(
    "step,unknown,expected,calls",
    [
        ("inventory_check", False, "failed", 1),
        ("inventory_reservation", True, "needs_attention", 2),
        ("fulfillment_request", False, "failed", 3),
        ("fulfillment_request", True, "needs_attention", 3),
    ],
)
def test_workflow_failures(session, step, unknown, expected, calls):
    t, order = make_order(session)
    provider = FakeProviders(
        session,
        (
            step,
            ProviderError(
                "timeout_unknown" if unknown else "provider_unavailable",
                "Provider unavailable",
                unknown=unknown,
                retryable=True,
            ),
        ),
    )
    result = process_order(session, t.id, order.id, provider)
    assert result.status == expected
    assert len(provider.calls) == calls
    assert result.steps[-1].status == ("unknown" if unknown else "failed")
    assert all(s.status == "completed" for s in result.steps[:-1])
    assert session.scalar(select(func.count()).select_from(StepExecution)) == calls
    if step == "fulfillment_request":
        assert order.status == "needs_attention"


@pytest.mark.parametrize(
    "status,category,retryable",
    [
        (503, "provider_unavailable", True),
        (401, "authorization_error", False),
        (422, "provider_rejected", False),
    ],
)
def test_provider_error_classification(status, category, retryable):
    provider = Providers(
        httpx.MockTransport(
            lambda _: httpx.Response(status, text="SECRET provider internals")
        )
    )
    with pytest.raises(ProviderError) as caught:
        provider.call("fulfillment_request", {})
    assert caught.value.category == category
    assert caught.value.retryable is retryable
    assert "SECRET" not in str(caught.value)


def test_provider_timeout_and_malformed_responses():
    def timeout(request):
        raise httpx.ReadTimeout(
            "credential_should_never_be_serialized", request=request
        )

    for transport in (
        httpx.MockTransport(timeout),
        httpx.MockTransport(lambda _: httpx.Response(200, json={})),
    ):
        with pytest.raises(ProviderError) as caught:
            Providers(transport).call("inventory_reservation", {})
        assert caught.value.unknown
        assert "credential" not in str(caught.value)


def test_postgres_concurrent_processing_claim(pg_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier, Lock

    from sqlalchemy.orm import Session

    with Session(pg_engine, expire_on_commit=False) as db:
        tenant, order = make_order(db)
        tenant_id, order_id = tenant.id, order.id
    barrier, lock = Barrier(2), Lock()
    calls = []

    def run(_):
        with Session(pg_engine, expire_on_commit=False) as db:

            class Provider(FakeProviders):
                def call(self, name, payload):
                    with lock:
                        calls.append(name)
                    return super().call(name, payload)

            barrier.wait(timeout=10)
            return process_order(db, tenant_id, order_id, Provider(db)).id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(run, range(2)))
    assert ids[0] == ids[1]
    assert calls == ["inventory_check", "inventory_reservation", "fulfillment_request"]
