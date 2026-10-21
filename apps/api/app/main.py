from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.orders import router as orders_router
from app.api.tenants import router as tenants_router
from app.api.workflows import router as workflows_router
from app.db import get_db

DbSession = Annotated[Session, Depends(get_db)]

app = FastAPI(
    title="BridgOps API",
    description="Retail Integration and Workflow Platform",
    version="0.1.0",
)

app.include_router(tenants_router)
app.include_router(orders_router)
app.include_router(workflows_router)


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "bridgops-api",
    }


@app.get("/health/db")
def database_health(db: DbSession):
    try:
        db.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "database": "connected",
        }

    except SQLAlchemyError:
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from None
