import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Order,
    OrderItem,
    StepExecution,
    Tenant,
    WorkflowExecution,
)
from app.models.base import Base


@pytest.fixture
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(connection, record):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


def create_tenant(db, name, slug):
    tenant = Tenant(name=name, slug=slug)
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


def create_order(db, tenant, external_id):
    order = Order(
        tenant_id=tenant.id,
        external_order_id=external_id,
        items=[
            OrderItem(sku="RICE-5KG", quantity=2),
            OrderItem(sku="MILK-1L", quantity=3),
        ],
    )

    db.add(order)
    db.commit()
    db.refresh(order)
    return order


def test_create_order_with_items(db):
    tenant = create_tenant(db, "Retailer A", "retailer-a")
    order = create_order(db, tenant, "WEB-1001")

    assert order.status == "received"
    assert order.tenant_id == tenant.id
    assert len(order.items) == 2
    assert order.items[0].order_id == order.id


def test_duplicate_order_same_tenant(db):
    tenant = create_tenant(db, "Retailer A", "retailer-a")

    create_order(db, tenant, "WEB-1001")

    duplicate = Order(
        tenant_id=tenant.id,
        external_order_id="WEB-1001",
    )

    db.add(duplicate)

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()


def test_same_order_id_different_tenants(db):
    first = create_tenant(db, "Retailer A", "retailer-a")
    second = create_tenant(db, "Retailer B", "retailer-b")

    order_a = create_order(db, first, "WEB-1001")
    order_b = create_order(db, second, "WEB-1001")

    assert order_a.id != order_b.id
    assert order_a.tenant_id != order_b.tenant_id


def test_invalid_quantity(db):
    tenant = create_tenant(db, "Retailer A", "retailer-a")

    order = Order(
        tenant_id=tenant.id,
        external_order_id="WEB-1002",
        items=[
            OrderItem(sku="RICE-5KG", quantity=0),
        ],
    )

    db.add(order)

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()


def test_workflow_cannot_reference_other_tenant_order(db):
    first = create_tenant(db, "Retailer A", "retailer-a")
    second = create_tenant(db, "Retailer B", "retailer-b")

    order = create_order(db, first, "WEB-1001")

    execution = WorkflowExecution(
        tenant_id=second.id,
        order_id=order.id,
    )

    db.add(execution)

    with pytest.raises(IntegrityError):
        db.commit()

    db.rollback()


def test_workflow_execution_with_steps(db):
    tenant = create_tenant(db, "Retailer A", "retailer-a")
    order = create_order(db, tenant, "WEB-1001")

    execution = WorkflowExecution(
        tenant_id=tenant.id,
        order_id=order.id,
        status="running",
        steps=[
            StepExecution(
                step_name="check_inventory",
                status="completed",
            ),
            StepExecution(
                step_name="reserve_inventory",
                status="pending",
            ),
        ],
    )

    db.add(execution)
    db.commit()
    db.refresh(execution)

    assert execution.order_id == order.id
    assert execution.tenant_id == tenant.id
    assert len(execution.steps) == 2
    assert execution.steps[0].execution_id == execution.id
