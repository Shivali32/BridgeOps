import os
from uuid import UUID

from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.providers.common import (
    DbSession,
    ItemsRequest,
    ReservationCreate,
    Simulator,
    canonical_items,
)
from app.providers.models import Reservation, Stock

app = FastAPI(title="BridgOps simulated inventory", version="0.1.0")
simulator = Simulator()
app.put("/demo/behavior")(simulator.configure)


class StockSet(BaseModel):
    tenant_id: UUID
    sku: str = Field(min_length=1, max_length=100, pattern=r"^\S+$")
    available: int = Field(ge=0, le=1_000_000)


@app.get("/health")
def health():
    return {"status": "healthy", "service": "inventory"}


@app.put("/inventory/stock")
def set_stock(data: StockSet, db: DbSession):
    if os.getenv("ENABLE_DEMO_ADMIN") != "true":
        raise HTTPException(404, "Development controls are disabled")
    stock = db.get(Stock, (data.tenant_id, data.sku))
    if stock is None:
        stock = Stock(**data.model_dump())
        db.add(stock)
    else:
        stock.available = data.available
    db.commit()
    return data


@app.post("/inventory/check")
def check(data: ItemsRequest, db: DbSession):
    behavior = simulator.before()
    stock = {
        s.sku: s.available
        for s in db.scalars(
            select(Stock).where(
                Stock.tenant_id == data.tenant_id,
                Stock.sku.in_([i.sku for i in data.items]),
            )
        )
    }
    result = [
        {
            "sku": i.sku,
            "requested": i.quantity,
            "available": stock.get(i.sku),
            "sufficient": stock.get(i.sku, 0) >= i.quantity,
        }
        for i in data.items
    ]
    simulator.after(behavior)
    return {"available": all(i["sufficient"] for i in result), "items": result}


def response(reservation: Reservation):
    return {
        "id": str(reservation.id),
        "tenant_id": str(reservation.tenant_id),
        "idempotency_key": reservation.idempotency_key,
        "items": reservation.items,
        "status": reservation.status,
    }


def existing_reservation(db, data, items):
    old = db.scalar(
        select(Reservation).where(
            Reservation.tenant_id == data.tenant_id,
            Reservation.idempotency_key == data.idempotency_key,
        )
    )
    if old is not None and old.items != items:
        raise HTTPException(409, "Idempotency key has different reservation data")
    return old


@app.post("/inventory/reservations", status_code=201)
def reserve(data: ReservationCreate, result: Response, db: DbSession):
    items = canonical_items(data)
    old = existing_reservation(db, data, items)
    if old:
        result.status_code = 200
        return response(old)
    behavior = simulator.before()
    try:
        reservation = Reservation(
            tenant_id=data.tenant_id, idempotency_key=data.idempotency_key, items=items
        )
        # Claim the idempotency key before touching stock. A competing duplicate
        # waits here, then reads the winner after rolling back its transaction.
        db.add(reservation)
        db.flush()
        for item in items:  # sorted lock order avoids multi-SKU deadlocks
            stock = db.scalar(
                select(Stock)
                .where(Stock.tenant_id == data.tenant_id, Stock.sku == item["sku"])
                .with_for_update()
            )
            if stock is None:
                raise HTTPException(422, f"Unknown SKU: {item['sku']}")
            if stock.available < item["quantity"]:
                raise HTTPException(409, "Insufficient stock")
            stock.available -= item["quantity"]
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if (
            getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
            != "uq_provider_reservation_key"
        ):
            raise
        old = existing_reservation(db, data, items)
        if old is None:
            raise
        result.status_code = 200
        return response(old)
    except Exception:
        db.rollback()
        raise
    simulator.after(behavior)
    return response(reservation)


@app.get("/inventory/reservations/by-key/{key}")
def by_key(key: str, tenant_id: UUID, db: DbSession):
    value = db.scalar(
        select(Reservation).where(
            Reservation.tenant_id == tenant_id, Reservation.idempotency_key == key
        )
    )
    if value is None:
        raise HTTPException(404, "Reservation not found")
    return response(value)


@app.get("/inventory/reservations/{reservation_id}")
def get_reservation(reservation_id: UUID, tenant_id: UUID, db: DbSession):
    value = db.scalar(
        select(Reservation).where(
            Reservation.tenant_id == tenant_id, Reservation.id == reservation_id
        )
    )
    if value is None:
        raise HTTPException(404, "Reservation not found")
    return response(value)
