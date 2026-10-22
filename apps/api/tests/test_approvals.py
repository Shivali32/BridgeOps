from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_workflow import FakeProviders

from app.models.definition import Approval
from app.schemas.definition import ApprovalDecision, DefinitionCreate, DefinitionUpdate
from app.services.definition import WorkflowConflictError, save_definition
from app.services.workflow import decide_approval, process_order
from tests_helpers import make_order


def approval_definition(threshold="20.00"):
    return {
        "name": "High value approval",
        "is_default": True,
        "steps": [
            {
                "id": "value_check",
                "type": "condition",
                "rules": {
                    "rules": [
                        {
                            "field": "order_total",
                            "operator": "greater_than",
                            "value": threshold,
                        }
                    ]
                },
            },
            {
                "id": "approve_order",
                "type": "approval",
                "when": {"condition_step": "value_check"},
                "reason": "High value order",
            },
            *[
                {"id": kind, "type": kind}
                for kind in (
                    "inventory_check",
                    "inventory_reservation",
                    "fulfillment_request",
                )
            ],
        ],
    }


def pending(db):
    tenant, order = make_order(db)
    definition = save_definition(
        db, tenant.id, DefinitionCreate(**approval_definition())
    )
    provider = FakeProviders(db)
    execution = process_order(db, tenant.id, order.id, provider)
    approval = db.scalar(select(Approval).where(Approval.execution_id == execution.id))
    assert execution.status == "needs_attention" and provider.calls == []
    return tenant, order, definition, execution, approval


def test_approval_resume_uses_original_snapshot(session):
    t, order, definition, _execution, approval = pending(session)
    changed = approval_definition("1000")
    changed["steps"][-1]["id"] = "renamed_fulfillment"
    save_definition(
        session, t.id, DefinitionUpdate(**changed, expected_version=1), definition.id
    )
    provider = FakeProviders(session)
    result = decide_approval(
        session,
        t.id,
        approval.id,
        ApprovalDecision(decision="approve", note="Checked"),
        provider,
    )
    assert result.status == order.status == "completed"
    assert result.definition_snapshot["version"] == 1
    assert result.steps[-1].step_name == "fulfillment_request"
    assert provider.calls == [
        "inventory_check",
        "inventory_reservation",
        "fulfillment_request",
    ]
    assert approval.status == "approved" and approval.decision_note == "Checked"
    again = decide_approval(
        session, t.id, approval.id, ApprovalDecision(decision="approve"), provider
    )
    assert again.id == result.id and len(provider.calls) == 3
    with pytest.raises(WorkflowConflictError):
        decide_approval(
            session, t.id, approval.id, ApprovalDecision(decision="reject"), provider
        )


def test_rejection_never_reserves_stock(session):
    t, order, _, _execution, approval = pending(session)
    provider = FakeProviders(session)
    result = decide_approval(
        session,
        t.id,
        approval.id,
        ApprovalDecision(decision="reject", note="Not permitted"),
        provider,
    )
    assert result.status == order.status == "failed"
    assert result.error_category == "approval_rejected" and not provider.calls


def test_false_condition_skips_approval(session):
    t, order = make_order(session, price="1.00")
    save_definition(session, t.id, DefinitionCreate(**approval_definition()))
    provider = FakeProviders(session)
    result = process_order(session, t.id, order.id, provider)
    assert result.status == "completed"
    assert result.steps[0].output_summary["matched"] is False
    assert result.steps[1].status == "skipped"
    assert session.scalar(select(Approval)) is None


def test_missing_price_stops_before_side_effects(session):
    t, order = make_order(session, price=None)
    save_definition(session, t.id, DefinitionCreate(**approval_definition()))
    provider = FakeProviders(session)
    result = process_order(session, t.id, order.id, provider)
    assert result.status == "needs_attention" and not provider.calls
    assert result.error_category == "validation_error"


def test_definition_api_validation_and_approval_scoping(api_client):
    c = api_client
    t = c.post("/api/v1/tenants", json={"name": "A", "slug": "a"}).json()["id"]
    base = f"/api/v1/tenants/{t}"
    data = approval_definition()
    value = c.post(base + "/workflow-definitions", json=data)
    assert value.status_code == 201
    definition = value.json()
    assert (
        c.patch(
            base + f"/workflow-definitions/{definition['id']}",
            json={**data, "expected_version": 1},
        ).status_code
        == 200
    )
    assert (
        len(c.get(base + f"/workflow-definitions/{definition['id']}/versions").json())
        == 2
    )
    assert (
        c.patch(
            base + f"/workflow-definitions/{definition['id']}",
            json={**data, "expected_version": 1},
        ).status_code
        == 409
    )
    assert (
        c.get(
            f"/api/v1/tenants/{uuid4()}/workflow-definitions/{definition['id']}/versions"
        ).status_code
        == 404
    )
    order = c.post(
        base + "/orders",
        json={
            "external_order_id": "W",
            "items": [{"sku": "A", "quantity": 1, "unit_price": "30.00"}],
        },
    ).json()
    assert (
        c.post(base + f"/orders/{order['id']}/process").json()["status"]
        == "needs_attention"
    )
    approvals = c.get(base + "/approvals?status=pending").json()
    assert len(approvals) == 1
    assert (
        c.post(
            f"/api/v1/tenants/{uuid4()}/approvals/{approvals[0]['id']}/decision",
            json={"decision": "reject"},
        ).status_code
        == 404
    )
    assert (
        c.post(
            base + f"/approvals/{approvals[0]['id']}/decision",
            json={"decision": "reject"},
        ).json()["status"]
        == "failed"
    )


def test_postgres_concurrent_conflicting_approval_decisions(pg_engine):
    with Session(pg_engine, expire_on_commit=False) as db:
        t, _, _, execution, approval = pending(db)
        tenant_id, approval_id, execution_id = t.id, approval.id, execution.id
    barrier = Barrier(2)
    calls = []

    def decide(action):
        with Session(pg_engine, expire_on_commit=False) as db:
            provider = FakeProviders(db)
            barrier.wait(timeout=10)
            try:
                decide_approval(
                    db,
                    tenant_id,
                    approval_id,
                    ApprovalDecision(decision=action),
                    provider,
                )
                calls.extend(provider.calls)
                return action
            except WorkflowConflictError:
                return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(decide, ["approve", "reject"]))
    assert results.count("conflict") == 1
    with Session(pg_engine) as db:
        value = db.get(Approval, approval_id)
        assert len(calls) == (3 if value.status == "approved" else 0)
        assert value.execution_id == execution_id
