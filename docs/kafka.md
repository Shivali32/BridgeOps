# Kafka workflow processing

Processing an order now returns HTTP 202 with a pending execution. The UI shows
Queued and refreshes progress. A separate worker performs the existing workflow.
The same path handles approved orders and eligible recovery actions.

## Update and run on Windows

Stop any host Uvicorn processes using ports 8000-8002 before starting Compose.
Save any local code changes before switching branches. Keep your existing `.env`
credentials and database volume. With Docker Desktop running, use PowerShell:

```powershell
cd D:\BridgOps
git fetch origin
git switch work/bridgops-kafka
git pull --ff-only origin work/bridgops-kafka
docker compose --profile app up -d --build
docker compose --profile app ps
Invoke-RestMethod http://127.0.0.1:8000/health/db
```

Git creates a local tracking branch automatically when only the matching remote
branch exists. Compose applies the new migration before the application starts.
The migration, kafka-volume-init and kafka-init containers should exit successfully;
they are jobs. The volume setup job gives Kafka's non-root user ownership of its
data directory before the broker starts.
Kafka, publisher and worker should stay running alongside the existing services.

In another terminal:

```powershell
cd D:\BridgOps\apps\web
npm.cmd ci
npm.cmd run dev
```

Open http://localhost:5173. The [grocery walkthrough](grocery-demo.md) still works:

```powershell
cd D:\BridgOps
docker compose --profile app exec -T api python scripts/grocery_demo.py
```

Seed scripts now wait for queued executions to finish or pause. Run them with
the worker available. Rerunning them preserves earlier orders and decisions.

## Show background processing

Use a new order ID each time. Sunrise Neighborhood Pantry has stock for
CAGE-FREE-EGGS-12CT and CHEDDAR-CHEESE-8OZ after grocery seeding.

1. Stop the worker: `docker compose --profile app stop worker`.
2. In Orders, save a new grocery order and click Process. It stays Queued.
3. Add and process another order. Both requests are accepted without waiting.
4. Restart: `docker compose --profile app start worker`.
5. Watch the orders complete automatically. Inspect their saved steps.

For a broker outage, stop `kafka`, submit a new order, then start `kafka` again.
The API can save the order and its command while Kafka is down. The publisher
retries with a delay, capped at 60 seconds. Completion may therefore take a
little longer after a broker restart.

## How dispatch is made reliable

- The API saves the execution, its frozen workflow version and the outbox event
  in one PostgreSQL transaction. Repeated Process clicks reuse the execution.
- The publisher claims an outbox row, publishes with broker confirmation, then
  records publication. A lost confirmation can lead to another delivery of the
  same event ID.
- A worker validates the event against its durable outbox record, including its
  retailer and execution. It locks the execution before claiming it.
- The worker saves workflow results and a consumer receipt before committing the
  Kafka offset. A replay reuses the result and cannot start the work again.
- Approval and recovery commands use a new event ID for the same execution.
  Older events cannot reverse a later decision. Workflow version snapshots and
  completed steps are preserved.
- A running execution has a 60-second ownership lease, refreshed at step
  boundaries. After a crash, another delivery waits for that lease to expire.
  Interrupted reservations or fulfillment writes are looked up before continuing.
  If the outcome cannot be verified, the order needs operator attention rather
  than an automatic repeat of the write.
- Business failures remain visible for controlled recovery. They are not retried
  endlessly because a Kafka message was redelivered. The existing three-attempt
  recovery limit still applies.
- Malformed, unknown or altered events are saved in `quarantined_messages`, with
  their topic/partition/offset, reason and payload digest, before their offsets
  are committed. Raw payloads are not logged or copied into that table.

The delivery model is at least once with duplicate-safe business operations.
Kafka transactions do not make PostgreSQL and external HTTP effects one atomic
transaction. Provider idempotency and reconciliation remain necessary.

## Processes, storage and settings

| Component | Purpose |
| --- | --- |
| Kafka | One local KRaft broker, persistent `kafka_data` volume |
| kafka-init | Creates `bridgops.workflow.commands.v1`, three partitions |
| publisher | Sends pending PostgreSQL outbox events |
| worker | Consumes commands using group `bridgops-workflows-v1` |
| PostgreSQL | Orders, workflows, outbox, receipts, quarantine and audit history |

Messages use a versioned JSON envelope with event, tenant, order and execution
IDs. The key is retailer ID plus execution ID, keeping commands for an execution
on the same partition. Commands carry references, while business data and
recovery notes stay in PostgreSQL.

Compose uses `kafka:19092` internally. Host Python connects to
`127.0.0.1:9092`. Kafka uses a 512 MB maximum JVM heap for this local setup.
It is a single broker with replication factor one, not a highly available
cluster. Ports bind to localhost and the existing local-demo access model applies.

For host Python development, start the backing services:

```powershell
cd D:\BridgOps
docker compose --profile app up -d postgres kafka kafka-init inventory fulfillment migrate
cd apps\api
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

In two additional terminals, from apps/api, run:

```powershell
.\.venv\Scripts\python.exe -m app.messaging.publisher
```

```powershell
.\.venv\Scripts\python.exe -m app.messaging.worker
```

Use one worker mode at a time. Stop the Compose worker/publisher before running
their host equivalents. `WORKFLOW_MODE=kafka` is the default. The explicit
`inline` mode is retained for isolated service tests and older synchronous checks.
Do not switch a running queued deployment to inline to clear pending work.

## Inspect and verify

The retailer-scoped `GET /api/v1/tenants/{id}/queue` endpoint reports commands
waiting for publication, published commands awaiting a worker, processed commands
and recent publication attempts. Workflow and business errors remain in Operations.

```powershell
docker compose --profile app logs --tail 100 publisher worker kafka
```

The full isolated Docker verification includes stopping/restarting the worker,
stopping/restarting Kafka, injecting a duplicate event and a malformed event,
and checking that stock was decremented once per order:

```powershell
cd D:\BridgOps
py -3.12 apps/api/scripts/smoke_kafka.py
```

This check intentionally interrupts the shared local services. Run it outside
another person's demo. It adds its own retailer and restores the services.
CI runs it on a fresh isolated stack, plus the existing grocery demos and browser
journeys. Unit and PostgreSQL tests cover atomic enqueueing, duplicate claims,
interrupted provider calls, approvals, queued retries and ownership checks.

To stop without deleting data, use `docker compose --profile app down`. Do not
add `-v` unless you intend to delete the PostgreSQL and Kafka volumes.

Outbox/receipt retention policies and Prometheus/Grafana monitoring remain
follow-up work; this stage keeps the records for investigation and demonstration.
