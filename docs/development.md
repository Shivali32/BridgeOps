# BridgOps development and safe Windows update

Kafka background processing is available on `work/bridgops-kafka`. Follow
[kafka.md](kafka.md) for that branch's update commands and publisher/worker setup.
The Docker app profile now includes Kafka and both background processes.

This version is a trusted-local demonstration. Use Docker Desktop with WSL 2,
Python 3.12, Node.js 22 and Git. The existing project can remain at `D:\BridgOps`.

## 1. Safely get the completed branch

Run in PowerShell. This stops if local changes need to be saved; it never discards them.

```powershell
Set-Location D:\BridgOps
git status --short
$pendingChanges = git status --porcelain
if ($LASTEXITCODE -ne 0) { throw "Could not inspect the repository." }
if ($pendingChanges) { throw "Save local changes with a commit or stash before switching branches." }

git fetch origin
if ($LASTEXITCODE -ne 0) { throw "Git fetch failed." }
$targetBranch = "work/bridgops-stage2-to-stage5"
git show-ref --verify --quiet "refs/heads/$targetBranch"
if ($LASTEXITCODE -eq 0) {
    git switch $targetBranch
    if ($LASTEXITCODE -ne 0) { throw "Branch switch failed." }
    git merge --ff-only "origin/$targetBranch"
} else {
    git switch --track -c $targetBranch "origin/$targetBranch"
}
if ($LASTEXITCODE -ne 0) { throw "Review the Git result before continuing." }
```

If you have local changes, commit them on your current branch or use
`git stash push -u -m "Before BridgOps Stage 5 update"`, then rerun the block.
Keep the stash until you have reviewed whether those changes are still needed.
Do not blindly apply old changes over the completed implementation. No merge to
main, forced update, branch deletion or database reset is required.

## 2. Preserve and configure the environment

```powershell
Set-Location D:\BridgOps
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Keep existing PostgreSQL credentials when reusing the current Docker volume.
Ensure `.env` contains POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB and INGEST_TOKEN.
Use a local token of your choice; do not commit it. Changing .env does not change
an existing PostgreSQL user's password. Do not delete the database volume to fix credentials.

## 3. Start PostgreSQL and apply migrations

The app profile applies migrations automatically. To also set up your host Python
environment for tests and development, run:

```powershell
Set-Location D:\BridgOps
docker compose up -d postgres
docker compose ps
Set-Location apps\api
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m alembic current
```

The expected migration head is `7af7_kafka_outbox`. Nine migrations preserve the
existing tenant/order migration history. No table recreation or volume deletion is needed.

## 4. Start the API and supporting services

Recommended: run all backend services through Compose.

```powershell
Set-Location D:\BridgOps
docker compose --profile app up -d --build
docker compose --profile app ps
Invoke-RestMethod http://127.0.0.1:8000/health/db
```

The profile includes PostgreSQL, the migration job, API, inventory and fulfillment.
Published ports bind to 127.0.0.1. The migration container exits successfully after
applying migrations. Provider tables share the physical database for this local demo.

For Kafka host development, follow [kafka.md](kafka.md), including its publisher
and worker commands. The three API commands below alone do not process queued work.
Alternatively, leave only PostgreSQL in Docker and start these commands in three
separate PowerShell terminals from `D:\BridgOps\apps\api`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

```powershell
$env:ENABLE_DEMO_ADMIN = "true"
.\.venv\Scripts\python.exe -m uvicorn app.providers.inventory:app --port 8001
```

```powershell
$env:ENABLE_DEMO_ADMIN = "true"
.\.venv\Scripts\python.exe -m uvicorn app.providers.fulfillment:app --port 8002
```

Use one backend mode at a time so ports are not claimed twice. Host defaults use
localhost:5433. POSTGRES_HOST/POSTGRES_PORT override these values. INVENTORY_URL,
FULFILLMENT_URL and PROVIDER_TIMEOUT_SECONDS configure trusted outbound endpoints
and the default three-second timeout. Provider failure controls are single-worker.

## 5. Start React

In another PowerShell terminal:

```powershell
Set-Location D:\BridgOps\apps\web
npm.cmd ci
npm.cmd run dev
```

Open http://localhost:5173. Vite proxies /api to the API on port 8000.
Swagger is available on ports 8000, 8001 and 8002 at /docs.

## 6. Seed the three-retailer demo

For a presentation with realistic grocery products and five named stores, use
[grocery-demo.md](grocery-demo.md). Its seed command is
`docker compose --profile app exec -T api python scripts/grocery_demo.py`.
The original smaller example below is still supported.

With the Compose stack running:

```powershell
Set-Location D:\BridgOps
docker compose --profile app exec -T api python scripts/demo.py
```

With host Python services:

```powershell
Set-Location D:\BridgOps\apps\api
.\.venv\Scripts\python.exe scripts/demo.py
```

The script creates/reuses three demo retailers and their integrations. It initializes
only missing stock, reuses existing orders and leaves prior configurations unchanged.
Retailer A completes a Shopify-style order, B waits for approval on a $600 REST
order, and C imports valid CSV orders while preserving an invalid-row result.
Refreshing retailer choices makes them available in React. See [demo.md](demo.md).

## 7. Run checks

```powershell
Set-Location D:\BridgOps\apps\api
.\.venv\Scripts\python.exe -m pytest -v
.\.venv\Scripts\python.exe -m ruff check app tests scripts
.\.venv\Scripts\python.exe -m ruff format --check app tests scripts
```

Without TEST_DATABASE_URL, PostgreSQL concurrency tests are explicitly skipped.
HTTP tests still start real HTTP servers, using an isolated temporary SQLite file.
CI runs these HTTP tests against PostgreSQL as well.

To run PostgreSQL tests locally, create a dedicated database once:

```powershell
Set-Location D:\BridgOps
docker compose exec -T postgres sh -c 'createdb -U "$POSTGRES_USER" bridgops_test'
```

If the database already exists, keep it. From apps/api, this command constructs
its URL using your existing credentials without printing them:

```powershell
Set-Location D:\BridgOps\apps\api
.\.venv\Scripts\python.exe -c "import os,subprocess,sys; from app.db import DATABASE_URL; os.environ['TEST_DATABASE_URL']=DATABASE_URL.set(database='bridgops_test').render_as_string(hide_password=False); sys.exit(subprocess.call([sys.executable,'-m','pytest','-v']))"
```

PostgreSQL fixtures create and drop their own random schemas. Do not point tests
at an external production database. SQLite tests do not prove PostgreSQL concurrency.

Frontend:

```powershell
Set-Location D:\BridgOps\apps\web
npm.cmd run test
npm.cmd run lint
npm.cmd run build
```

Browser tests require all three HTTP services and an isolated demonstration database.
The CSV browser test expects INGEST_TOKEN=ci_local_ingestion_token on that isolated
API. Do not replace a normal local token merely to run tests against valuable data.
CI provisions the isolated environment automatically.

```powershell
npm.cmd exec playwright install chromium
npm.cmd exec playwright test
```

## 8. Stop without deleting data

```powershell
Set-Location D:\BridgOps
docker compose --profile app down
```

Stop host Uvicorn/Vite processes with Ctrl+C when using them. Do not add `-v`
unless you intentionally want to delete the PostgreSQL volume.

## Troubleshooting

- Run backend commands from apps/api. Do not change application imports to mask
  a wrong working directory.
- Use npm.cmd when PowerShell blocks npm.ps1.
- If a port is occupied, stop the other host/container process before restarting.
- If ingestion returns 403, check INGEST_TOKEN and the form's development-token field.
- If a workflow waits for approval, use Workflows or Operations to decide it.
- A completed workflow means provider acceptance, not delivery.
- A fulfillment failure keeps the reservation. Use controlled recovery rather than
  submitting another order with changed contents under the same external ID.
- A lost response is uncertain. Reconcile the provider outcome before retrying.
- A running execution requires 60 seconds without progress before stale reconciliation.
- No authentication or tenant authorization exists. Keep this version local.
