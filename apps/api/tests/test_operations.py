from datetime import timedelta
from uuid import uuid4

import pytest
from test_approvals import approval_definition
from test_recovery import RecoveryProvider, failed
from test_workflow import FakeProviders

from app.schemas.definition import DefinitionCreate
from app.schemas.operations import RecoveryAction
from app.services.definition import save_definition
from app.services.operations import list_operations, summary
from app.services.recovery import recover
from app.services.workflow import now, process_order
from tests_helpers import make_order


def test_operations_counts_filters_and_tenant_isolation(session):
    t, _order, execution = failed(session)
    other_tenant, other_order = make_order(session)
    process_order(session, other_tenant.id, other_order.id, FakeProviders(session))
    totals = summary(session, t.id)
    assert totals["orders"] == {"needs_attention": 1}
    assert totals["executions"] == {"failed": 1}
    assert totals["pending_approvals"] == totals["import_failures"] == 0
    assert totals["average_completed_duration_seconds"] is None
    assert (
        len(
            list_operations(
                session, t.id, status="failed", error_category="provider_unavailable"
            )
        )
        == 1
    )
    assert list_operations(session, t.id, status="completed") == []
    assert list_operations(session, t.id, offset=1) == []
    assert list_operations(session, t.id, start=now() + timedelta(days=1)) == []
    result = recover(
        session,
        t.id,
        execution.id,
        RecoveryAction(
            request_key="r", action="retry", note="Retry confirmed transient failure"
        ),
        RecoveryProvider(session),
    )
    assert result.status == "completed"
    totals = summary(session, t.id)
    assert totals["orders"] == {"completed": 1} and totals["retry_requests"] == 1
    assert totals["average_completed_duration_seconds"] >= 0
    with pytest.raises(ValueError):
        summary(session, t.id, now(), now() - timedelta(days=1))


def test_pending_approval_filter_and_count(session):
    t, order = make_order(session)
    save_definition(session, t.id, DefinitionCreate(**approval_definition()))
    process_order(session, t.id, order.id, FakeProviders(session))
    assert len(list_operations(session, t.id, approval_status="pending")) == 1
    assert summary(session, t.id)["pending_approvals"] == 1


def test_operations_api_validation_and_recovery_scope(api_client):
    c = api_client
    tenant_id = c.post("/api/v1/tenants", json={"name": "A", "slug": "a"}).json()["id"]
    base = f"/api/v1/tenants/{tenant_id}"
    assert c.get(base + "/operations").json() == []
    assert c.get(base + "/operations/summary").json()["orders"] == {}
    assert c.get(base + "/operations?limit=0").status_code == 422
    assert c.get(base + "/operations?status=delivered").status_code == 422
    assert (
        c.get(
            base + "/operations?start=2026-10-22T00:00:00Z&end=2026-10-21T00:00:00Z"
        ).status_code
        == 422
    )
    assert c.get(f"/api/v1/tenants/{uuid4()}/operations").status_code == 404
    assert c.get(base + f"/executions/{uuid4()}/audit").status_code == 404
    assert (
        c.post(
            base + f"/executions/{uuid4()}/recovery",
            json={"request_key": "r", "action": "investigated", "note": "Investigated"},
        ).status_code
        == 404
    )
