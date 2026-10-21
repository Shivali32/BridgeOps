
# BridgOps Development Progress

Last updated: 2026-10-21

## Current Stage

Stage 1: Application Foundation

Current task:
Step 7 - Documentation and setup verification

## Completed

### Repository and Environment
- Initialized Git repository
- Renamed project to BridgOps
- Configured Python development environment
- Configured Node.js environment
- Verified Docker Desktop and WSL 2
- Created GitHub repository and pushed code

### Backend
- Created FastAPI application
- Implemented health endpoints
- Configured PostgreSQL with Docker Compose
- Configured SQLAlchemy database connection
- Configured Alembic migrations
- Created Tenant model
- Implemented tenant CRUD API
- Added Pydantic validation
- Added database error handling

### Frontend
- Initialized React with TypeScript and Vite
- Configured local API proxy
- Created Tenant API client
- Implemented tenant listing
- Implemented tenant creation
- Implemented tenant editing
- Implemented tenant deactivation
- Added loading and error states

### Testing and CI
- 11 backend tests passed
- 7 frontend tests passed
- Frontend build and lint passed
- GitHub Actions backend job passed
- GitHub Actions frontend job passed

## In Progress

- README improvements
- Architecture documentation
- Developer setup instructions
- Stage 1 final verification

## Upcoming

### Stage 1 Completion
- Verify documentation links
- Verify a clean project setup
- Add basic Python linting
- Confirm GitHub repository is up to date

### Stage 2
- Define Order and OrderItem models
- Implement order submission API
- Create simulated inventory integration
- Create simulated fulfillment integration
- Implement first synchronous order workflow
- Store workflow execution status
- Display orders in React
- Add integration tests

## Known Limitations

- No authentication or authorization
- Tenant management is development-only
- Tenant data isolation is not yet enforced for business operations
- No order processing yet
- No workflow engine yet
- No Kafka consumers or producers
- No external retail integrations
- No production deployment
- Frontend tests use mocked API responses
- Backend tenant API tests use SQLite

## Deferred Features

- Kafka
- Transactional outbox
- Configurable workflows
- Approval workflows
- Multi-store permissions
- Prometheus and Grafana
- Airflow
- Kubernetes
- Terraform
- GCP

## Important Decisions

See decisions.md.

## Local Development

Database:

    docker compose up -d postgres

Backend:

    cd apps/api
    python -m uvicorn app.main:app --reload

Frontend:

    cd apps/web
    npm run dev

Detailed instructions:

See development.md.

## Stage 1 Exit Criteria

- [x] Git repository created
- [x] FastAPI backend working
- [x] PostgreSQL connection working
- [x] Alembic migrations configured
- [x] Tenant CRUD API implemented
- [x] React TypeScript frontend working
- [x] Frontend communicates with backend
- [x] Backend automated tests pass
- [x] Frontend automated tests pass
- [x] GitHub Actions CI passes
- [ ] Documentation committed and verified
- [ ] Fresh-clone setup verified
- [ ] Final Stage 1 review completed

## Autonomous development checkpoint, 2026-10-21

Authoritative baseline: `df1e1b6` on `main`. The handoff described order API
routes that were absent from the repository. Stage 1 baseline: 24 backend tests,
7 frontend tests, lint/format/build passed in the Work environment.

### Step 2.3D

- Added tenant-scoped order POST/list/detail routes with 201/200/409/404/422 semantics.
- Rejected writes for inactive tenants; validated missing tenants on reads.
- Made creation rollback atomic and restricted race recovery to the specific
  PostgreSQL order uniqueness constraint.
- Added service/API/rollback/scoping/pagination tests and PostgreSQL concurrent
  identical/conflicting submissions using independent sessions and isolated schemas.
- CI now runs on development branches, supplies PostgreSQL 17, and checks migrations.
- Local result: 32 passed, 2 PostgreSQL tests skipped (no Docker/server available).
  PostgreSQL behavior remains unverified until CI runs. No SQLite concurrency claim.

Roadmap for this branch supersedes the older roadmap above:
2 synchronous workflows; 3 connectors/mappings; 4 configurable workflows/approvals;
5 operations/recovery; 6 Kafka (deferred). No authentication or authorization yet.

### Step 2.4

- Independent inventory HTTP service on 8001 with PostgreSQL-backed stock and
  reservations. A sorted row-lock sequence prevents overselling; the idempotency
  key is claimed before stock changes. Failed multi-item reservations roll back.
- Added reconciliation lookup by tenant and idempotency key.
- Development-only stock setup and bounded failure/delay controls.
- Added Compose app profile, backend Dockerfile and Alembic migration.
- Local: 34 passed, 4 PostgreSQL tests skipped; lint and format pass.
- Step 2.3D CI passed both jobs, including migrations and PostgreSQL races:
  https://github.com/Shivali32/BridgeOps/actions/runs/39656158054

### Step 2.5

- Independent fulfillment HTTP service on 8002; accepted requests have stable IDs,
  tenant-scoped lookups and persistent idempotency keys with conflict detection.
- Added reconciliation-by-key, development delay/failure controls, migration,
  Compose profile and PostgreSQL duplicate/conflict race tests.
- Local: 35 passed, 6 PostgreSQL tests skipped; lint/format pass.
- Accepted fulfillment means provider submission, not delivery.

### Step 2.6

- Synchronous workflow service and process/history/detail APIs now coordinate the
  inventory and fulfillment HTTP services. Order row locks serialize execution
  claims. Repeat processing returns the same execution without repeating effects.
- Step records persist before calls, with no transaction held during HTTP.
- Provider results, stable keys, references, timestamps and failure categories persist.
- Timeout/malformed mutation responses become unknown/needs_attention. Completed
  reservations remain visible if fulfillment fails; no automatic retry is attempted.
- Added migration, transaction-boundary assertions, failure tests, real HTTP tests
  for all three FastAPI servers, and a PostgreSQL concurrent workflow-claim test.
- Local: 46 passed, 7 PostgreSQL tests skipped; lint/format pass. Real HTTP success
  and timeout-after-provider-commit scenarios passed locally against test SQLite.
  CI runs those HTTP scenarios against PostgreSQL.
- Inventory milestone CI passed: https://github.com/Shivali32/BridgeOps/actions/runs/39656503661

### Step 2.7

- Extended the existing React application with a retailer-scoped order workspace,
  multi-item forms, optional decimal price strings, pagination, processing controls,
  step history, provider references, error/loading/empty states and refresh controls.
- Unknown outcomes and accepted fulfillment are described accurately.
- Added 9 frontend tests (16 total) covering forms, API errors, status/details,
  processing and tenant selection. Frontend lint and production build pass.
- Workflow milestone CI passed, including PostgreSQL races and real HTTP workflows:
  https://github.com/Shivali32/BridgeOps/actions/runs/39657334948
- Stage 2 implementation and automated HTTP/component verification are complete.
  Browser smoke verification is pending; no claim of Windows Docker verification.

### Steps 3.1 to 3.3

- Added a typed connector protocol and explicit registry for simulated Shopify,
  custom REST payloads and CSV row groups. Shared mapping code normalizes each
  distinct source representation to the existing Pydantic OrderCreate model.
- Controlled dotted-field mapping supports renaming, trimming, type validation,
  defaults and exact Decimal cents conversion. No eval, dynamic loading or secrets.
- Added equivalence, nested mapping, invalid configuration, duplicate SKU, missing
  field, malformed quantity and decimal edge-case tests.

### Browser verification infrastructure

- Added Playwright with a real browser order-submission/processing scenario and
  CI evidence upload. CI starts all three HTTP services against PostgreSQL.
- Browser download in Work returned invalid archives, so local browser execution
  is blocked. Component tests, lint and build still pass. CI browser result pending.

### Steps 3.4 and 3.5

- Tenant-owned integration create/update/list APIs with optimistic version checks,
  connector validation and enable/disable settings. Secrets are not configuration fields.
- Incoming simulated provider payloads and CSV imports require an environment-backed
  development token. Management endpoints remain trusted-local-only without user auth.
- Import records persist before processing and store mapping snapshots, payload
  digests, source references, row numbers, duplicate outcomes and safe error messages.
  A crash can leave a pending import for investigation; raw provider payloads are not stored.
- CSV groups multiple rows per order, rejects invalid order groups atomically, keeps
  successful groups, and limits input to 500 rows/100 orders/256 KiB.
- Imports use the existing order service and its tenant-scoped duplicate protection.
- Local: 63 backend tests passed, 7 PostgreSQL tests skipped; lint and format pass.

### Independent service startup correction

Browser CI detected a provider-model registration cycle that was hidden by pytest's
shared imports. Moved provider registration to Alembic and test setup, and added
fresh-interpreter import tests for API, inventory and fulfillment. Local backend:
66 passed, 7 PostgreSQL tests skipped. Browser CI will be rerun on this fix.
