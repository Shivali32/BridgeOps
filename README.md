
# BridgOps

### Multi-Tenant Retail Integration & Workflow Platform

BridgOps is a software platform designed to help retail businesses connect independent applications, automate operational workflows, and monitor business processes from a centralized dashboard.

The platform is being developed as a production-style full-stack engineering project focused on backend systems, enterprise integrations, multi-tenancy, reliability, and distributed architecture.

## The Problem

Retail businesses often use separate systems for order management, inventory, fulfillment, delivery, and customer communication.

These applications may expose different APIs, use different data formats, and require manual coordination.

BridgOps aims to provide a common integration and workflow layer between these systems.

For example:

Order Received → Inventory Check → Stock Reservation → Fulfillment → Notification

The platform will also handle failures, retries, workflow tracking, and customer-specific configurations.

## Current Implementation

Stage 1: Application Foundation

Implemented:
- FastAPI REST backend
- PostgreSQL database using Docker Compose
- SQLAlchemy ORM and Alembic migrations
- Tenant creation, retrieval, updates, and deactivation
- Pydantic request and response validation
- React and TypeScript frontend
- Interactive tenant management dashboard
- API error handling and loading states
- Backend tests with pytest
- Frontend tests with Vitest and React Testing Library
- GitHub Actions continuous integration

The current implementation focuses on tenant administration and basic full-stack infrastructure.

Authentication, tenant-level authorization, order processing, and workflow execution are not implemented yet.

## Technology Stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI |
| Frontend | React, TypeScript, Vite |
| Database | PostgreSQL |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Local Infrastructure | Docker Compose |
| Backend Testing | pytest |
| Frontend Testing | Vitest, React Testing Library |
| CI | GitHub Actions |

## Architecture

React Dashboard
    |
    v
Vite Development Proxy
    |
    v
FastAPI REST API
    |
    v
SQLAlchemy
    |
    v
PostgreSQL

The initial architecture uses a modular FastAPI backend with a separate React frontend.

The database uses a shared-database tenancy model. Each tenant represents a business account.

Tenant authentication and isolation will be enforced before exposing the platform publicly.

See [Architecture Documentation](docs/architecture.md).

## Getting Started

### Requirements

- Python 3.12
- Node.js 22
- Docker Desktop with Docker Compose
- Git

### Quick Start

1. Clone the repository.
2. Copy `.env.example` to `.env` and configure a local database password.
3. Start PostgreSQL using Docker Compose.
4. Install backend dependencies and run Alembic migrations.
5. Start the FastAPI server.
6. Install frontend dependencies and start Vite.

Detailed instructions:

[Development Setup](docs/development.md)

### Local URLs

| Service | URL |
|---|---|
| Frontend | http://localhost:5173 |
| API | http://127.0.0.1:8000 |
| Swagger Documentation | http://127.0.0.1:8000/docs |
| API Health | http://127.0.0.1:8000/health |
| Database Health | http://127.0.0.1:8000/health/db |

## Testing

Backend:

    cd apps/api
    python -m pytest -v

Frontend:

    cd apps/web
    npm run test
    npm run lint
    npm run build

GitHub Actions automatically runs backend and frontend checks on pushes to main and pull requests targeting main.

## Development Roadmap

- Stage 1: Application foundation and tenant management
- Stage 2: Orders and simulated external integrations
- Stage 3: Kafka and asynchronous workflow processing
- Stage 4: Multi-tenancy, authorization, and configurable workflows
- Stage 5: Monitoring and reliability
- Stage 6: Airflow and data reconciliation
- Stage 7: Kubernetes and infrastructure automation
- Stage 8: CI/CD and automated quality improvements
- Stage 9: Final validation and portfolio preparation

Basic CI was introduced early in Stage 1.

See [Development Progress](docs/progress.md).

## Project Status

Active development.

The project is currently intended for local development and demonstration. It is not production-ready or safe for public deployment without authentication, authorization, and further security testing.
