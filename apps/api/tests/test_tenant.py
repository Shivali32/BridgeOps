import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db import get_db
from app.main import app
from app.models.base import Base


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(bind=engine)

    def override_get_db():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_create_tenant(client):
    response = client.post(
        "/api/v1/tenants",
        json={
            "name": "Retailer A",
            "slug": "retailer-a",
        },
    )

    assert response.status_code == 201

    data = response.json()
    assert data["name"] == "Retailer A"
    assert data["slug"] == "retailer-a"
    assert data["is_active"] is True
    assert "id" in data


def test_get_tenant(client):
    created = client.post(
        "/api/v1/tenants",
        json={"name": "Retailer A", "slug": "retailer-a"},
    ).json()

    response = client.get(f"/api/v1/tenants/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_list_tenants(client):
    client.post(
        "/api/v1/tenants",
        json={"name": "Retailer A", "slug": "retailer-a"},
    )

    client.post(
        "/api/v1/tenants",
        json={"name": "Retailer B", "slug": "retailer-b"},
    )

    response = client.get("/api/v1/tenants")

    assert response.status_code == 200
    assert len(response.json()) == 2


def test_duplicate_slug(client):
    payload = {
        "name": "Retailer A",
        "slug": "retailer-a",
    }

    client.post("/api/v1/tenants", json=payload)
    response = client.post("/api/v1/tenants", json=payload)

    assert response.status_code == 409


def test_update_tenant(client):
    created = client.post(
        "/api/v1/tenants",
        json={"name": "Retailer A", "slug": "retailer-a"},
    ).json()

    response = client.patch(
        f"/api/v1/tenants/{created['id']}",
        json={"name": "Retailer A Group"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "Retailer A Group"


def test_deactivate_tenant(client):
    created = client.post(
        "/api/v1/tenants",
        json={"name": "Retailer A", "slug": "retailer-a"},
    ).json()

    tenant_url = f"/api/v1/tenants/{created['id']}"

    response = client.delete(tenant_url)

    assert response.status_code == 204

    result = client.get(tenant_url)
    assert result.json()["is_active"] is False


def test_get_missing_tenant(client):
    response = client.get("/api/v1/tenants/00000000-0000-0000-0000-000000000001")

    assert response.status_code == 404


@pytest.mark.parametrize(
    "slug",
    ["Retailer A", "retailer_a", "invalid--slug"],
)
def test_invalid_slug(client, slug):
    response = client.post(
        "/api/v1/tenants",
        json={"name": "Retailer", "slug": slug},
    )

    assert response.status_code == 422
