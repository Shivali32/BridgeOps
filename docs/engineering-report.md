# BridgOps Stage 5 engineering report

Date: 21 October 2026. Scope: complete the existing project through Stage 5 and
stop before Kafka. The original repository and migration history were preserved.

For the later Kafka implementation, see [kafka.md](kafka.md) and [progress.md](progress.md).
This report preserves the original Stage 5 delivery evidence.

## A. Repository and delivery

| Item | Value |
|---|---|
| Repository | https://github.com/Shivali32/BridgeOps |
| Development branch | work/bridgops-stage2-to-stage5 |
| Default branch | main, not merged |
| Starting commit | df1e1b6 |
| Latest verified implementation checkpoint | 5a699bb, followed by the final report/diagnostic checkpoint |
| Publication | Milestone commits published to the development branch |
| Pull request | https://github.com/Shivali32/BridgeOps/pull/1 (draft) |
| Development location | Work's isolated Linux environment, not the user's Windows filesystem |

The supplied handoff was ahead of the actual repository. Order schemas and a service
existed, but order API routes were absent. Those routes, tenant checks, rollback
handling and tests were implemented before building the remaining product.

The finished branch remains separate from main. No force push, history rewrite,
existing branch deletion, database reset, paid infrastructure or Kafka was introduced.

## B. Milestone status

| Stage | Milestone | Implementation | Tests | Commit | CI |
|---|---|---|---|---|---|
| 2 | Order API, duplicate handling and rollback | Complete | Service/API and PostgreSQL races | db17bca | Passed |
| 2 | Independent inventory service | Complete | Stock, isolation, duplicate and competing reservations | b44877d | Passed |
| 2 | Independent fulfillment service | Complete | Idempotency, conflicts and PostgreSQL races | a2b9413 | Passed |
| 2 | Synchronous workflow runner | Complete | Success/failure, transaction boundaries and real HTTP | be81cab | Passed |
| 2 | React order workspace | Complete | Forms, errors, history and browser journey | dce3223 | Passed |
| 3 | Connector registry and canonical mappings | Complete | Source equivalence and invalid transformations | 959b1b4 | Passed |
| 3 | Tenant configurations and import records | Complete | Versions, token checks, CSV partial failures and scoping | c119ced | Passed |
| 3 | Integration UI and three-retailer HTTP scenarios | Complete | Forms, upload, results and browser CSV import | 3ba0680 | Passed |
| 4 | Versioned definitions and typed rules | Complete | Decimal rules, missing data, invalid branches and history | cb846d3 | Passed |
| 4 | Conditional execution and approvals | Complete | Pause/resume, rejection, version snapshot and concurrent decisions | d79919a | Passed |
| 4 | Workflow and approval UI | Complete | Presets, assignment, versions and browser approval | 97a114e, 5bd3ffb | Passed |
| 5 | Operations, recovery and audit APIs | Complete | Retry/reconciliation, limits, fencing, summaries and concurrency | aa03c81 | Passed |
| 5 | Central operations and recovery UI | Complete | Filters, details, notes, eligibility and browser retry | 021e2f1 | Passed |
| 5 | Actual Docker stack and repeatable seeded demo | Complete | Compose image smoke and demo run twice | 29e2c85, 7d48567, 5a699bb | Passed |

## C. Delivered behavior

Backend capabilities include tenant-scoped order submission, retrieval and pagination;
normalized duplicate comparison; explicit synchronous processing; durable step records;
provider references; versioned integration configuration; JSON and grouped CSV import;
workflow configuration; rules; approvals; recovery and operational aggregation.

The inventory API checks stock, creates stable reservations and supports reconciliation
by tenant/key or ID. Stock locks prevent overselling. Fulfillment persists accepted
requests with stable IDs and idempotency. Both services support controlled local
failures and delays, including a response delayed after its business effect commits.
Accepted fulfillment never means delivered.

Three distinct source formats share one canonical Pydantic order model. Shopify-style
JSON uses line_items and prices. Custom REST JSON uses products and prices in cents.
CSV groups rows per external order and reports invalid groups without discarding
successful ones. Configurable mappings use explicit operations, defaults and Decimal
conversion. No arbitrary Python or expression execution is allowed.

Workflow definitions are versioned and validated. They support condition, approval,
inventory_check, inventory_reservation and fulfillment_request steps. Approval branches
reference earlier conditions and run before reservation. Rules use order value,
quantity, SKU membership or source fields, with all/any groups. Missing prices stop
value rules. A paused execution continues its original snapshot after configuration edits.

Operations shows actual database summaries, tenant-scoped execution filters, source,
errors, timestamps, step attempts and manual audit history. Recovery uses persistent
request keys, provider reconciliation, stable business keys, attempt limits and ownership
fencing. Completed steps are preserved. Investigation notes do not change completion
state. Supplied references must match the tenant and original operation.

React extends the original tenant dashboard with Orders, Integrations, Workflows and
Operations tabs. It includes input validation, loading/empty/error states, pagination,
configuration editors, import samples, CSV upload, approval decisions, execution details,
retry eligibility and recovery notes. It does not claim tenant selection is authorization.

Six additive migrations extend the original two migrations. Current head is
7af6_operations. There are 15 application/provider tables plus Alembic's version table.
No development data was deleted or migration history replaced.

## D. Verification evidence

| Check | Actual result |
|---|---|
| Original backend baseline | 24 passed |
| Original frontend baseline | 7 passed |
| Final local backend | 101 passed, 10 explicitly skipped PostgreSQL tests |
| PostgreSQL-backed CI backend | 111 passed, no skipped tests in the verified functional run |
| Final frontend tests | 35 passed across 7 files |
| Backend Ruff | Lint and formatting checks passed for app, tests and scripts |
| Frontend ESLint | Passed |
| TypeScript/Vite build | Passed |
| Real HTTP tests | Actual Uvicorn servers for platform, inventory and fulfillment |
| Browser checks | Four Playwright journeys passed against PostgreSQL and real services |
| Migration verification | Upgrade to head and Alembic model-drift check passed in CI |
| Compose configuration | Validated in CI |
| Actual Compose images/demo | Image build/start, HTTP smoke and three-retailer demo twice passed |

Full verification evidence, all three jobs passed:
https://github.com/Shivali32/BridgeOps/actions/runs/39665127385

That run built and started the actual Docker images, applied migrations, verified a
complete HTTP workflow and ran the three-retailer seed twice. Both runs reused the
same tenant IDs and preserved duplicate behavior. Browser screenshots were inspected.

The final report/diagnostic checkpoint runs the same required pipeline. Its current
result is available through the branch Actions view:
https://github.com/Shivali32/BridgeOps/actions?query=branch%3Awork%2Fbridgops-stage2-to-stage5

PostgreSQL tests use independent sessions and isolated random schemas. They exercise
identical/conflicting order creation, competing stock reservations, fulfillment
duplicates/conflicts, initial workflow claims, conflicting approval decisions and
same/different-key concurrent recovery requests. SQLite results are not presented
as proof of PostgreSQL concurrency.

Real HTTP scenarios cover standard processing, all three source formats, invalid CSV
groups, approval pause/resume, provider failure followed by safe retry, and a response
lost after provider acceptance. The latter is resolved both by key lookup and supplied
reference verification. Tests inspect database state and remaining stock.

The four browser journeys cover order creation/processing, integration configuration
and CSV import, approval through the central operations console, and failure inspection
followed by retry without a duplicate reservation. Screenshots/traces are attached to
CI as browser-workflow-evidence.

Work had no Docker daemon or usable Chromium binary. Native PostgreSQL/browser/Compose
verification therefore ran on GitHub's isolated CI runners. This did not access the
user's Windows database. The documented Windows commands have not been executed on
the user's computer. One dependency deprecation warning remains for the pinned
Starlette/httpx TestClient combination; it does not fail the executed tests.

## E. Published milestone history

| Commit | Change |
|---|---|
| db17bca | Verify order APIs, rollback and concurrent submissions |
| b44877d | Persistent inventory API and atomic reservations |
| a2b9413 | Idempotent fulfillment provider API |
| be81cab | Durable synchronous order workflows over HTTP |
| dce3223 | React order and execution dashboard |
| 959b1b4 | Reusable connectors and controlled mappings |
| bf6d97e | Real browser order journey in CI |
| c119ced | Tenant integration/import persistence and independent startup correction |
| 3ba0680 | Integration UI and three-retailer import verification |
| cb846d3 | Versioned workflow definitions and typed rules |
| d79919a | Conditional workflows, approval pauses and resumption |
| 97a114e | Workflow configuration and approval UI |
| 5bd3ffb | Exact browser locator for workflow saving |
| aa03c81 | Operations, reconciliation and fenced recovery |
| 021e2f1 | Operations console and central approval management |
| 29e2c85 | Recovery boundary coverage and actual Docker demo checks |
| 7d48567 | Environment discovery for shallow container layouts |
| 5a699bb | Healthy service readiness and stable timeout verification |

The final documentation/diagnostic checkpoint follows these commits. The development
branch and pull request show its exact current head.

## F. Architecture

The system remains a modular FastAPI backend with a React/TypeScript frontend and
PostgreSQL. Separate provider processes communicate through synchronous HTTP.
Connectors normalize inputs into the existing order service. The workflow service
resolves configuration, snapshots it, persists steps and coordinates the providers.
Approval decisions and recovery actions claim executions and preserve audit history.

See [architecture.md](architecture.md) for component relationships, database boundaries,
concurrency controls, state meanings and security limits. The service boundary remains
usable for a future worker without making Kafka a prerequisite for this version.

## G. Known limits

- Authentication, user identity, tenant permissions and production authorization are absent.
- Operator names are self-reported development labels, not verified identities.
- Source connectors simulate incoming formats; they do not connect a live Shopify account.
- Processing starts through an explicit Process action and remains synchronous.
- The provider simulators share one physical PostgreSQL instance and run with one worker.
- No stock release, fulfillment cancellation, shipment, payment or delivery handling exists.
- Existing order contents are immutable. Corrected conflicting business data needs a new
  source revision ID; failed transformations can be corrected and reimported normally.
- A crash can leave a pending import. A stale execution without a persisted external
  step needs developer investigation rather than an unsafe state override.
- There is no broker, durable background dispatch or production deployment.
- Windows execution on the user's machine remains a local setup step.

## H. Windows setup

[development.md](development.md) contains copy-paste PowerShell blocks to inspect local
changes, fetch/switch safely, preserve .env, start PostgreSQL, apply migrations, start
the API and supporting services, start React, run tests and stop without deleting data.
It also provides a host-Python alternative to the complete Compose profile.

After the safe branch update and environment check:

```powershell
Set-Location D:\BridgOps
docker compose --profile app up -d --build
docker compose --profile app exec -T api python scripts/demo.py
Set-Location apps\web
npm.cmd ci
npm.cmd run dev
```

Open http://localhost:5173. Keep existing database credentials and set your own local
INGEST_TOKEN. Do not run the host API and container API on the same port simultaneously.

## I. Product demonstration

[demo.md](demo.md) covers all three seeded retailers, source mappings, workflow
history, CSV correction, high-value approval, provider failure, safe retry, unknown
outcome reconciliation and supplied-reference verification using actual endpoints.

Retailer A demonstrates standard Shopify-style fulfillment. B uses custom REST cents
and waits for approval above $500. C demonstrates successful CSV orders plus a recorded
invalid row. The shared operations console makes each execution and recovery inspectable.

## J. Stage 6 handoff

Kafka is intentionally not implemented. [stage6-handoff.md](stage6-handoff.md) explains
how a future transactional outbox and worker could reuse the verified service boundary,
claims, snapshots, provider keys and recovery semantics. Authentication remains a
prerequisite before exposing the product publicly.
