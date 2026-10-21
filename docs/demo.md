# Three-retailer product demonstration

Start the stack and seed data using [development.md](development.md). Open React,
refresh retailer choices and select each retailer under Order processing. The four
tabs share the same underlying application and selected tenant.

## Retailer A: standard e-commerce integration

Select Demo Retailer A. Integrations shows Demo shopify_simulated and its field
mapping. Recent imports records the mapping snapshot and successful source order.
Orders shows DEMO-A-1001 completed. View it to inspect inventory check, reservation
and accepted fulfillment, including timestamps, payload summaries and references.
Reimporting the same sample reuses the existing order. Clicking Process again through
the API returns the same execution; it does not reserve stock again.

## Retailer B: approval before business side effects

Select Demo Retailer B. Its custom REST connector maps price_cents to exact prices.
The $600 DEMO-B-1001 order uses the assigned high-value approval workflow and is
needs_attention. Workflows shows the versioned definition and assignment.

In Operations, filter Approval filter to pending and apply. Inspect the execution,
then review its source, item values, rule and pending approval. Add a decision note
and approve through the approval list. The workflow resumes, reserves stock and
requests fulfillment. Alternatively, reject a new approval order and confirm no
inventory reservation occurs. Decision history includes the unverified local operator.

To create another approval case without changing code, import a custom REST sample
with a new reference and total above $500, then Process it from Orders.

## Retailer C: CSV import and correction

Select Demo Retailer C. Its CSV integration groups rows by order_reference. The
seed imports DEMO-C-1001 and DEMO-C-1002 and records a failed DEMO-C-BAD row with
its row number. Successful orders are processed. The invalid row is preserved in
import history instead of being silently discarded.

Use Test on the CSV integration, enter your local ingestion token and upload or
paste a file. Correct the bad row's quantity to a positive integer and import it
again. This creates a new import attempt and a canonical order. Process that order
from Orders. Resubmitting unchanged successful rows reports existing orders.

Default CSV columns are order_reference, product_code, qty, unit_price. Price is
optional in meaning but the supplied header is useful. Missing prices prevent value
rules from making a decision; they never become zero.

## Fulfillment failure and safe retry

Choose a retailer with a standard workflow, such as Demo Retailer A. Its DEMO-A
SKU has initialized stock. Configure a single pre-effect provider failure:

```powershell
Invoke-RestMethod -Method Put -Uri http://127.0.0.1:8002/demo/behavior -ContentType "application/json" -Body '{"mode":"unavailable","remaining":1}'
```

Submit a new order with a new external ID and SKU DEMO-A, then Process it. The
inventory reservation completes and fulfillment fails with HTTP 503. Open Operations,
inspect the failure, add a resolution note, then choose Retry eligible step.

The retry first reconciles the provider key, preserves the completed reservation,
appends the fulfillment attempt and completes after acceptance. Step history shows
one reservation and two fulfillment attempts. Audit history records the request.
The browser CI scenario verifies the remaining stock equals the original stock minus
one reservation, with no duplicate decrement.

## Lost response and reconciliation

Configure a delay after the fulfillment side effect commits:

```powershell
Invoke-RestMethod -Method Put -Uri http://127.0.0.1:8002/demo/behavior -ContentType "application/json" -Body '{"mode":"delay_after","remaining":1,"delay_seconds":5}'
```

The API's default timeout is three seconds. Process another new standard order.
Its fulfillment step becomes unknown and the execution needs_attention. In Operations,
add a note and choose Reconcile provider outcome. The provider lookup verifies the
accepted request, appends a reconciled result and finishes without another submission.

Verify external reference is also supported. It checks the reference against tenant,
idempotency key, items and fulfillment references. It cannot arbitrarily mark a
failed order as completed. Record investigation only adds a note and preserves state.

## Operational views and isolation

Operations supports status, integration, approval, error and date filtering, with
pagination. Summaries use real database data. Source/error filters affect the list;
date filters also affect the summary. Latest saved orders are explicitly shown for
all dates. Average completed elapsed time includes approval waits.

Switching retailers clears the workspace state and loads tenant-scoped data. API
cross-tenant retrieval tests return 404. This proves data scoping, not user authorization.
Keep the demo local until authenticated access control is implemented.
