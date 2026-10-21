
# BridgOps Architecture

## 1. Overview

BridgOps is a multi-tenant retail integration and workflow platform.

The initial implementation follows a modular monorepo architecture with:

- React + TypeScript frontend
- FastAPI backend
- PostgreSQL database
- Docker Compose for local infrastructure
- GitHub Actions for continuous integration

The architecture is designed to evolve toward asynchronous workflow execution and independent integration workers.

## 2. Current Architecture

```text
Browser
   |
   v
React + TypeScript (Vite)
   |
   | HTTP / JSON
   v
Vite Development Proxy
   |
   v
FastAPI
   |
   +--- API Routers
   |
   +--- Pydantic Schemas
   |
   +--- Service Layer
   |
   v
SQLAlchemy
   |
   v
PostgreSQL (Docker)
```

The Vite proxy is used only during local development.

## 3. Backend Responsibilities

### API Layer

Location: `apps/api/app/api/`

Responsible for:
- HTTP routing
- Request and response handling
- Dependency injection
- HTTP status codes
- Translating application errors into API responses

### Schema Layer

Location: `apps/api/app/schemas/`

Responsible for:
- Request validation
- Response serialization
- API data contracts

Pydantic is used for validation.

### Service Layer

Location: `apps/api/app/services/`

Responsible for:
- Business operations
- Database transactions
- Tenant creation and updates
- Database query logic

### Database Models

Location: `apps/api/app/models/`

SQLAlchemy models define database tables and relationships.

The initial model is `Tenant`.

### Database Configuration

Location: `apps/api/app/db.py`

Responsible for:
- Loading database configuration
- Creating the SQLAlchemy engine
- Creating database sessions
- Managing session cleanup

## 4. Frontend Responsibilities

Location: `apps/web/src/`

### API Client

`src/api/` contains functions for communicating with FastAPI.

### Types

`src/types/` defines TypeScript interfaces matching API contracts.

### Components

`src/components/` contains reusable React UI components.

Current components include:
- TenantList
- TenantForm

## 5. Multi-Tenancy

A tenant represents one retail business.

For example:
- Retailer A
- Retailer B
- Retailer C

The initial system uses a shared PostgreSQL database.

Each tenant has a unique UUID and slug.

Future business tables will include tenant ownership identifiers.

Important:

Tenant administration is currently accessible without authentication or authorization.

Tenant-scoped access control, authenticated user identity, and cross-tenant isolation tests must be implemented before public deployment.

## 6. Tenant Request Flow

Example: Create a retailer.

1. User fills out the React form.
2. React sends POST /api/v1/tenants.
3. FastAPI validates the request using Pydantic.
4. The service layer creates a SQLAlchemy Tenant object.
5. SQLAlchemy commits the transaction to PostgreSQL.
6. FastAPI returns the created tenant.
7. React refreshes the tenant list.

## 7. Database Migrations

Alembic manages PostgreSQL schema changes.

Models are defined using SQLAlchemy.

Migration files are stored in:

`apps/api/alembic/versions/`

Schema updates are applied using:

`python -m alembic upgrade head`

Migration files must be reviewed and committed to Git.

## 8. Current Error Handling

The application handles:
- Invalid tenant data
- Duplicate tenant slugs
- Missing tenant records
- Unavailable API responses
- Database health failures

More advanced transaction recovery and retry behavior will be implemented later.

## 9. Planned Architecture Evolution

Future stages will add:

- Simulated external REST integrations
- Order and fulfillment processing
- Kafka event producers and consumers
- Asynchronous workflow workers
- Retry and dead-letter mechanisms
- Transactional outbox
- Configurable tenant workflows
- Prometheus and Grafana
- Airflow reconciliation
- Kubernetes deployment
- Terraform infrastructure

These are planned components, not currently implemented features.

## 10. Key Design Principles

- Start with a modular backend
- Separate API and business logic
- Validate data at API boundaries
- Use database migrations
- Keep tenant ownership explicit
- Avoid unnecessary microservices
- Introduce asynchronous processing for concrete needs
- Make failures observable and recoverable
- Prioritize maintainability over tool count
