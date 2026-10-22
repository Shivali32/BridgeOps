# BridgOps

A multi-tenant retail integration and workflow platform for local development.
Connect different order formats, apply retailer-specific workflows, pause for approval,
and recover failures without repeating successful business operations.

**Local demo only. Authentication and tenant authorization are not implemented.**
All Compose ports bind to loopback. A tenant selector is not an access-control system.

## What works

- Tenant management and tenant-scoped orders with normalized duplicate handling.
- Simulated Shopify-style JSON, custom REST JSON and grouped CSV imports.
- Versioned integration mappings with validation and persistent import results.
- Configurable, versioned workflows with typed rules and conditional approvals.
- Separate inventory and fulfillment REST services with persistent idempotency.
- Stock reservations protected against concurrent overselling.
- Execution steps, provider references, failure categories and approval history.
- Operations filters, database summaries, safe retries, reconciliation and audit notes.
- A React workspace for orders, integrations, workflows, approvals and operations.
- Kafka background processing with a transactional PostgreSQL outbox, publisher,
  duplicate-safe worker, crash reconciliation and malformed-message quarantine.

Completed workflow means **fulfillment request accepted**, not delivered.
Saving/importing an order does not start processing automatically. Process is an
explicit action that queues a workflow and returns HTTP 202. The UI refreshes
progress while the Kafka worker processes it. Approvals and eligible recovery
actions also queue work without keeping the API request open.

## Run locally on Windows

Requirements: Python 3.12, Node.js 22, Git and Docker Desktop with WSL 2.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set a local PostgreSQL password and `INGEST_TOKEN`. When reusing an existing database,
keep its existing credentials. Changing `.env` does not change an initialized database password.

```powershell
docker compose --profile app up -d --build
cd apps\web
npm.cmd ci
npm.cmd run dev
```

Open http://localhost:5173. The app profile starts PostgreSQL, migrations, the API,
inventory, fulfillment, Kafka, its topic setup job, the publisher and the worker.
PostgreSQL alone remains `docker compose up -d postgres`.

Seed three example retailers, including a pending approval and a CSV validation failure:

```powershell
# From the repository root, in another terminal:
docker compose --profile app exec -T api python scripts/demo.py
```

The demo can be repeated. It reuses orders/configurations and only initializes missing
stock. It does not reset your database. Refresh retailer choices in React afterward.

See [Windows setup and safe branch update](docs/development.md),
[Kafka setup and interruption demo](docs/kafka.md),
[five-store grocery walkthrough](docs/grocery-demo.md),
[demonstration guide](docs/demo.md), [architecture](docs/architecture.md),
[progress](docs/progress.md), and [engineering report](docs/engineering-report.md).

## Local services

| Service | Address |
|---|---|
| React | http://localhost:5173 |
| API and Swagger | http://127.0.0.1:8000/docs |
| Inventory and Swagger | http://127.0.0.1:8001/docs |
| Fulfillment and Swagger | http://127.0.0.1:8002/docs |
| PostgreSQL host port | localhost:5433 |
| Kafka host listener | localhost:9092 |

## Checks

From `apps/api` in a virtual environment with requirements installed:

```powershell
python -m pytest -v
python -m ruff check app tests scripts
python -m ruff format --check app tests scripts
```

From `apps/web`:

```powershell
npm.cmd run test
npm.cmd run lint
npm.cmd run build
```

PostgreSQL concurrency tests use `TEST_DATABASE_URL` and isolated random schemas.
Without it, those tests are explicitly skipped. CI supplies PostgreSQL 17, verifies
migrations, runs real HTTP and browser scenarios, and checks the actual Compose images.

## Stack and scope

Python, FastAPI, Pydantic, SQLAlchemy, PostgreSQL 17, Alembic, React, TypeScript,
Vite, Apache Kafka, confluent-kafka, pytest, Ruff, Vitest, Testing Library, Playwright,
Docker Compose and GitHub Actions.

Stages 1 to 5 cover the local integration product. Stage 6 adds Kafka background
processing. Monitoring, scheduled data jobs and cloud deployment remain later work.
See [Kafka setup](docs/kafka.md) and [verification status](docs/progress.md).

Limitations: no authentication/authorization, no live Shopify account integration,
no payment/delivery processing, no stock release or fulfillment cancellation, and
no production deployment. Demo failure controls require trusted local development.
