import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.tenant import Tenant
from app.schemas.tenant import TenantCreate, TenantUpdate


class DuplicateTenantSlugError(Exception):
    pass


def create_tenant(
    db: Session,
    data: TenantCreate,
) -> Tenant:
    tenant = Tenant(**data.model_dump())

    db.add(tenant)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise DuplicateTenantSlugError() from None

    db.refresh(tenant)
    return tenant


def get_tenant(
    db: Session,
    tenant_id: uuid.UUID,
) -> Tenant | None:
    return db.get(Tenant, tenant_id)


def list_tenants(
    db: Session,
    offset: int = 0,
    limit: int = 50,
) -> list[Tenant]:
    statement = (
        select(Tenant)
        .order_by(Tenant.created_at, Tenant.id)
        .offset(offset)
        .limit(limit)
    )

    return list(db.scalars(statement).all())


def update_tenant(
    db: Session,
    tenant: Tenant,
    data: TenantUpdate,
) -> Tenant:
    updates = data.model_dump(exclude_unset=True)

    for field, value in updates.items():
        setattr(tenant, field, value)

    db.commit()
    db.refresh(tenant)

    return tenant


def deactivate_tenant(
    db: Session,
    tenant: Tenant,
) -> None:
    tenant.is_active = False
    db.commit()
