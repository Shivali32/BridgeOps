from uuid import UUID

from fastapi import FastAPI, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.providers.common import (
    DbSession,
    ReservationCreate,
    Simulator,
    canonical_items,
)
from app.providers.models import FulfillmentRequest

app = FastAPI(title="BridgOps simulated fulfillment", version="0.1.0")
simulator = Simulator()
app.put("/demo/behavior")(simulator.configure)


class FulfillmentCreate(ReservationCreate):
    reservation_id: UUID
    order_id: UUID


def response(value):
    return {
        "id": str(value.id),
        "tenant_id": str(value.tenant_id),
        "idempotency_key": value.idempotency_key,
        "status": value.status,
        **value.payload,
    }


def existing(db, data, payload):
    value = db.scalar(
        select(FulfillmentRequest).where(
            FulfillmentRequest.tenant_id == data.tenant_id,
            FulfillmentRequest.idempotency_key == data.idempotency_key,
        )
    )
    if value is not None and value.payload != payload:
        raise HTTPException(409, "Idempotency key has different fulfillment data")
    return value


@app.get("/health")
def health():
    return {"status": "healthy", "service": "fulfillment"}


@app.post("/fulfillment/requests", status_code=201)
def request_fulfillment(data: FulfillmentCreate, result: Response, db: DbSession):
    payload = {
        "order_id": str(data.order_id),
        "reservation_id": str(data.reservation_id),
        "items": canonical_items(data),
    }
    old = existing(db, data, payload)
    if old is not None:
        result.status_code = 200
        return response(old)
    behavior = simulator.before()
    try:
        value = FulfillmentRequest(
            tenant_id=data.tenant_id,
            idempotency_key=data.idempotency_key,
            payload=payload,
        )
        db.add(value)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if (
            getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            != "uq_provider_fulfillment_key"
        ):
            raise
        value = existing(db, data, payload)
        if value is None:
            raise
        result.status_code = 200
    simulator.after(behavior)
    return response(value)


@app.get("/fulfillment/requests/by-key/{key}")
def by_key(key: str, tenant_id: UUID, db: DbSession):
    value = db.scalar(
        select(FulfillmentRequest).where(
            FulfillmentRequest.tenant_id == tenant_id,
            FulfillmentRequest.idempotency_key == key,
        )
    )
    if value is None:
        raise HTTPException(404, "Fulfillment request not found")
    return response(value)


@app.get("/fulfillment/requests/{request_id}")
def get_request(request_id: UUID, tenant_id: UUID, db: DbSession):
    value = db.scalar(
        select(FulfillmentRequest).where(
            FulfillmentRequest.tenant_id == tenant_id,
            FulfillmentRequest.id == request_id,
        )
    )
    if value is None:
        raise HTTPException(404, "Fulfillment request not found")
    return response(value)
