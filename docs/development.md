
# BridgOps Development Setup

## 1. Prerequisites

Install:

- Git
- Python 3.12
- Node.js 22
- Docker Desktop
- Docker Compose

Windows with PowerShell and WSL 2 is the primary local development environment.

## 2. Clone the Repository

```powershell
git clone https://github.com/YOUR_USERNAME/BridgOps.git
cd BridgOps
```

Replace YOUR_USERNAME with the actual GitHub username.

## 3. Configure Environment Variables

From the repository root:

```powershell
Copy-Item .env.example .env
```

Edit `.env`:

```dotenv
POSTGRES_USER=bridgops
POSTGRES_PASSWORD=your_local_password
POSTGRES_DB=bridgops_db
```

Choose your own local development password.

Do not commit `.env` to Git.

Important: PostgreSQL initializes its database credentials when its data directory is first created.

Changing the password in `.env` later does not automatically change an existing PostgreSQL user's password.

## 4. Start PostgreSQL

Make sure Docker Desktop is running.

From the repository root:

```powershell
docker compose up -d postgres
```

Check the container:

```powershell
docker compose ps
```

Expected: PostgreSQL is healthy.

Database connection:
- Host: localhost
- Windows port: 5433
- Container port: 5432
- Database: bridgops_db

## 5. Set Up the Backend

Open a PowerShell terminal:

```powershell
cd apps\api
py -3.12 -m venv .venv
```

Activate the virtual environment:

```powershell
.\.venv\Scripts\Activate.ps1
```

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

If PowerShell blocks activation, use a process-scoped execution policy:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Then retry activation.

## 6. Apply Database Migrations

From `apps/api`:

```powershell
python -m alembic upgrade head
```

Check the applied migration:

```powershell
python -m alembic current
```

Do not manually recreate application tables.

## 7. Start FastAPI

From `apps/api`:

```powershell
python -m uvicorn app.main:app --reload
```

The backend runs at:

http://127.0.0.1:8000

API documentation:

http://127.0.0.1:8000/docs

Health checks:

http://127.0.0.1:8000/health

http://127.0.0.1:8000/health/db

## 8. Set Up the Frontend

Open another PowerShell terminal.

Navigate to the frontend:

```powershell
cd apps\web
```

Install dependencies:

```powershell
npm.cmd ci
```

Start Vite:

```powershell
npm.cmd run dev
```

Open:

http://localhost:5173

Vite forwards `/api` requests to FastAPI through the development proxy.

FastAPI must be running for API-backed frontend functionality.

## 9. Run Backend Tests

From `apps/api`:

```powershell
python -m pytest -v
```

The current tenant API tests use a temporary SQLite database.

They do not require a running PostgreSQL container.

## 10. Run Frontend Tests

From `apps/web`:

```powershell
npm.cmd run test
npm.cmd run lint
npm.cmd run build
```

Frontend component tests use mocked API functions.

## 11. Verify Tenant Management

Start PostgreSQL, FastAPI, and React.

Open the frontend and:

1. Create a retailer.
2. Verify it appears in the list.
3. Edit the retailer name.
4. Try creating a duplicate slug.
5. Deactivate the retailer.
6. Refresh the browser and verify the status persists.

## 12. Stop the Services

Stop the FastAPI and Vite development servers with Ctrl+C.

From the repository root:

```powershell
docker compose down
```

This stops and removes the Compose containers and network while preserving the database volume.

Do not use `docker compose down -v` unless you intentionally want to delete the database volume.

## 13. Common Issues

### ModuleNotFoundError: No module named 'app'

Run Uvicorn from `apps/api`.

### npm.ps1 is blocked

Use `npm.cmd` in PowerShell.

### Database connection fails

Verify:
- Docker Desktop is running
- PostgreSQL is healthy
- Port 5433 is accessible
- `.env` credentials match PostgreSQL

### Frontend API request fails

Check:
- FastAPI is running on port 8000
- Vite is running on port 5173
- `vite.config.ts` contains the development proxy

### Migration fails

Check PostgreSQL connectivity and inspect the migration error before changing the database.

## 14. Security Notes

- Do not commit secrets.
- Do not expose tenant administration endpoints publicly.
- Do not use local database credentials in production.
- Authentication and tenant authorization are not yet implemented.

## Simulated inventory (Step 2.4)

After applying migrations, run from `apps/api` in another terminal:

```powershell
$env:ENABLE_DEMO_ADMIN = "true"
python -m uvicorn app.providers.inventory:app --port 8001
```

Or build the Compose inventory service with `docker compose --profile app up -d --build inventory`.
This service uses the same physical database for a lightweight demo, but separate
provider tables and HTTP APIs. It does not read the platform's orders or tenants.
All published ports bind to loopback. Do not expose this unauthenticated demo.

`PUT http://127.0.0.1:8001/inventory/stock` accepts a tenant UUID, sku and available
quantity. `PUT /demo/behavior` accepts mode (`normal`, `unavailable`, `delay_before`,
`delay_after`), remaining (0 to 100) and delay_seconds (0 to 10). These controls
require ENABLE_DEMO_ADMIN=true. `delay_after` commits before delaying the response,
so callers must reconcile the outcome instead of assuming failure.

The simulator controls are process-local and intended for a single Uvicorn worker.
Reservations and stock are persistent. API requests accept `tenant_id` in JSON;
lookups require `tenant_id` as a query parameter. See each service's `/docs`.

## Simulated fulfillment (Step 2.5)

In a separate backend virtual-environment terminal:

```powershell
$env:ENABLE_DEMO_ADMIN = "true"
python -m uvicorn app.providers.fulfillment:app --port 8002
```

Compose equivalent: `docker compose --profile app up -d --build fulfillment`.
The same bounded `/demo/behavior` controls are supported. Fulfillment POST accepts
`tenant_id`, `order_id`, `reservation_id`, `items`, and `idempotency_key`.
The returned `accepted` status never represents delivery.

## Process an order (Step 2.6)

`POST /api/v1/tenants/{tenant_id}/orders/{order_id}/process` runs synchronously.
`GET .../orders/{order_id}/executions` and `GET .../executions/{execution_id}`
return the persistent execution and its steps. Submitting an order only saves it;
processing is an explicit action. Repeating process returns the existing execution.

Set `INVENTORY_URL`, `FULFILLMENT_URL` and `PROVIDER_TIMEOUT_SECONDS` in the API
process if the default loopback ports 8001, 8002 and 3-second timeout do not apply.
A completed workflow means fulfillment was accepted, not delivered. A fulfillment
failure after reservation leaves stock reserved. No release/cancel API exists yet.
Unknown outcomes must be reconciled by the provider's tenant-scoped by-key lookup.
No blind automatic retries are performed.

The API session factory must use `expire_on_commit=False` so reading identifiers
does not open implicit transactions between a step commit and an external call.
A process crash can leave a running execution; repeated process calls intentionally
return it instead of duplicating work. Recovery controls are a later milestone.

## React order demonstration

Open http://localhost:5173, refresh retailer choices and select a retailer under
Order processing. Create stock for that tenant using the inventory service first.
Save an order, then click its Process button. View shows items, execution steps,
timestamps, requests/results and provider references. Refresh orders reloads states.
Prices remain decimal strings across the browser/API boundary. Orders are scoped
by tenant; selecting a tenant is not authentication.

## Integrations and imports (Stage 3)

Set `INGEST_TOKEN` in the repository `.env` to a local value and restart the API.
Do not commit that value. Configuration endpoints are for trusted local use only.

Use `/api/v1/tenants/{tenant_id}/connectors` to inspect built-in field mappings.
`POST /integrations` creates a name, connector_type, enabled flag and optional
mapping. `PATCH /integrations/{id}` takes the complete settings plus
expected_version, rejecting stale updates. Connector type is immutable.

For `shopify_simulated`, send `{id, line_items: [{sku, quantity, price}]}`.
For `custom_rest`, send `{reference, products: [{product_code, count, price_cents}]}`.
Both use `POST /integrations/{id}/ingest` with `X-Development-Token`.
For `csv`, `POST /integrations/{id}/csv` accepts `{csv_text: "..."}` and the same
header. Default columns: order_reference, product_code, qty, unit_price. Multiple
rows with the same order_reference form one order. A bad item fails its full order
group, while other groups are saved. The response identifies every group's rows.
Imports save orders; processing stays an explicit action in Stage 3.

`GET /imports?limit=50&offset=0` provides persistent results. Failed imports can
be corrected and submitted again as new import attempts. Successful duplicate
submissions reuse the same order. Import snapshots remain unchanged after updates.
Custom mappings accept dotted dictionary paths, defaults and Decimal cents conversion.
CSV mappings use flat columns and a synthetic items collection named rows.
Provider secrets and outbound URLs are not accepted in these configuration objects.
These simulated incoming adapters do not poll live Shopify or other provider APIs.
