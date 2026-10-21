from sqlalchemy import select, update

from app.models import Tenant
from app.models.definition import WorkflowDefinition, WorkflowVersion
from app.schemas.definition import DefinitionCreate, DefinitionUpdate
from app.services.order import OrderNotFoundError, require_tenant


class WorkflowConflictError(Exception):
    pass


def get_definition(db, tenant_id, definition_id, *, lock=False):
    stmt = select(WorkflowDefinition).where(
        WorkflowDefinition.id == definition_id,
        WorkflowDefinition.tenant_id == tenant_id,
    )
    value = db.scalar(stmt.with_for_update() if lock else stmt)
    if value is None:
        raise OrderNotFoundError("Workflow definition not found.")
    return value


def save_definition(db, tenant_id, data: DefinitionCreate, definition_id=None):
    require_tenant(db, tenant_id, active=True)
    # Serialize default selection and configuration updates for this tenant.
    db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    if definition_id:
        value = get_definition(db, tenant_id, definition_id, lock=True)
        if (
            not isinstance(data, DefinitionUpdate)
            or data.expected_version != value.version
        ):
            raise WorkflowConflictError("Workflow changed. Refresh before saving.")
        value.version += 1
    else:
        value = WorkflowDefinition(tenant_id=tenant_id, version=1)
        db.add(value)
    if data.is_default:
        with db.no_autoflush:
            db.execute(
                update(WorkflowDefinition)
                .where(WorkflowDefinition.tenant_id == tenant_id)
                .values(is_default=False)
            )
    value.name, value.enabled, value.is_default = (
        data.name,
        data.enabled,
        data.is_default,
    )
    value.configuration = data.model_dump(mode="json", exclude={"expected_version"})
    db.flush()
    db.add(
        WorkflowVersion(
            tenant_id=tenant_id,
            definition_id=value.id,
            version=value.version,
            snapshot={
                "id": str(value.id),
                "version": value.version,
                **value.configuration,
            },
        )
    )
    db.commit()
    return value
