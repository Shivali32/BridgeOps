import csv
import hashlib
import io
import json
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.connectors import Mapping, connector
from app.models.integration import ImportRecord, Integration
from app.schemas.integration import IntegrationCreate, IntegrationUpdate
from app.services.order import (
    OrderConflictError,
    OrderNotFoundError,
    create_order,
    require_tenant,
)


class IntegrationConflictError(Exception):
    pass


def get_integration(db, tenant_id, integration_id, *, lock=False):
    stmt = select(Integration).where(
        Integration.id == integration_id, Integration.tenant_id == tenant_id
    )
    value = db.scalar(stmt.with_for_update() if lock else stmt)
    if value is None:
        raise OrderNotFoundError("Integration not found.")
    return value


def save_integration(
    db: Session, tenant_id: UUID, data: IntegrationCreate, integration_id=None
):
    require_tenant(db, tenant_id, active=True)
    if data.workflow_id is not None:
        from app.models.definition import WorkflowDefinition

        if (
            db.scalar(
                select(WorkflowDefinition.id).where(
                    WorkflowDefinition.id == data.workflow_id,
                    WorkflowDefinition.tenant_id == tenant_id,
                )
            )
            is None
        ):
            raise OrderNotFoundError("Workflow definition not found.")
    value = None
    if integration_id:
        value = get_integration(db, tenant_id, integration_id, lock=True)
        if (
            not isinstance(data, IntegrationUpdate)
            or data.expected_version != value.version
        ):
            raise IntegrationConflictError(
                "Configuration changed. Refresh before saving."
            )
        if data.connector_type != value.connector_type:
            raise IntegrationConflictError(
                "Connector type cannot change. Create another integration."
            )
        value.version += 1
    config = data.model_dump(exclude={"mapping", "expected_version"})
    config["mapping"] = (
        data.mapping or connector(data.connector_type).default_mapping
    ).model_dump(mode="json")
    if value is None:
        value = Integration(tenant_id=tenant_id, **config)
        db.add(value)
    else:
        for name, item in config.items():
            setattr(value, name, item)
    db.commit()
    return value


def snapshot(value):
    return {
        "id": str(value.id),
        "version": value.version,
        "connector_type": value.connector_type,
        "mapping": value.mapping,
    }


def import_one(db, tenant_id, config, payload, row_numbers=None):
    record = ImportRecord(
        tenant_id=tenant_id,
        integration_id=UUID(config["id"]),
        config_snapshot=config,
        payload_digest=hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()
        ).hexdigest(),
        row_numbers=row_numbers or [],
        status="pending",
        duplicate=False,
    )
    db.add(record)
    db.commit()
    try:
        data = connector(config["connector_type"]).convert(
            payload, Mapping.model_validate(config["mapping"])
        )
        record.source_reference = data.external_order_id
        order, created = create_order(db, tenant_id, data)
        record.order_id = order.id
        record.status = "succeeded"
        record.duplicate = not created
    except (ValueError, OrderConflictError) as exc:
        record.status = "failed"
        record.error_message = str(exc)[:1000]
    db.add(record)
    db.commit()
    return record


def ingest(db, tenant_id, integration_id, payload):
    require_tenant(db, tenant_id, active=True)
    value = get_integration(db, tenant_id, integration_id)
    if not value.enabled:
        raise IntegrationConflictError("Integration is disabled.")
    if value.connector_type == "csv":
        raise IntegrationConflictError(
            "Use the CSV import endpoint for this connector."
        )
    config = snapshot(value)
    db.commit()  # Freeze the configuration used by this import.
    return import_one(db, tenant_id, config, payload)


def ingest_csv(db, tenant_id, integration_id, csv_text):
    require_tenant(db, tenant_id, active=True)
    value = get_integration(db, tenant_id, integration_id)
    if not value.enabled or value.connector_type != "csv":
        raise IntegrationConflictError("An enabled CSV integration is required.")
    config = snapshot(value)
    mapping = Mapping.model_validate(config["mapping"])
    # CSV is flat. Nested paths and a renamed synthetic rows collection are not supported.
    names = [mapping.external_id, mapping.sku, mapping.quantity]
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")), strict=True)
    if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
        raise ValueError("CSV headers are missing or duplicated.")
    if any("." in name for name in names) or mapping.items != "rows":
        raise ValueError("CSV mapping must use flat columns and items=rows.")
    if not set(names).issubset(reader.fieldnames):
        raise ValueError("CSV must include: " + ", ".join(names))
    groups = {}
    try:
        for number, row in enumerate(reader, 2):
            if number > 501:
                raise ValueError("CSV is limited to 500 data rows.")
            reference = (row.get(mapping.external_id) or "").strip()
            key = reference or f"__invalid_row_{number}"
            group = groups.setdefault(
                key,
                {
                    "payload": {mapping.external_id: reference, "rows": []},
                    "numbers": [],
                },
            )
            if None in row or any(x is None for x in row.values()):
                row = {}  # The complete order group will fail required item validation.
            group["payload"]["rows"].append(row)
            group["numbers"].append(number)
            if len(groups) > 100:
                raise ValueError("CSV is limited to 100 orders.")
    except csv.Error:
        raise ValueError("Malformed CSV input.") from None
    if not groups:
        raise ValueError("CSV contains no orders.")
    db.commit()
    return [
        import_one(db, tenant_id, config, group["payload"], group["numbers"])
        for group in groups.values()
    ]
