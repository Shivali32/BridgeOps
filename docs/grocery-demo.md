# Five-store grocery walkthrough

These are fictional stores with realistic names, grocery products and sample USD
prices. They are easy to explain without knowing retail software. No customer
names, addresses or outside store accounts are needed.

## Prepare the presentation

In PowerShell, from the repository root:

```powershell
cd D:\BridgOps
git pull --ff-only origin work/bridgops-stage2-to-stage5
docker compose --profile app up -d --build
docker compose --profile app exec -T api python scripts/grocery_demo.py
```

Your existing `.env` needs database credentials and `INGEST_TOKEN`. The Compose
setup passes the token to the API and seed script. Do not paste it into the script.

In another PowerShell window:

```powershell
cd D:\BridgOps\apps\web
npm.cmd ci
npm.cmd run dev
```

Open http://localhost:5173 and refresh the retailer list. Keep the first terminal
available for the restocking step. If using host Python with all three APIs
already running, the equivalent seed command is:

```powershell
cd D:\BridgOps\apps\api
.\.venv\Scripts\python.exe scripts/grocery_demo.py
```

The script creates five retailers, five integrations, five workflow definitions,
stock for all ordered products, 15 valid orders and one invalid CSV import.
On a fresh run, 12 orders complete, one waits for approval, one fails a stock
check and one remains received for you to process live. Prices are per pack;
quantity 2 of FRESH-STRAWBERRIES-1LB means two one-pound packs.

| Store | Familiar products | Source of orders | Main thing to show |
| --- | --- | --- | --- |
| Maplewood Fresh Market | Strawberries, milk, bread, eggs, frozen peas | Online store, using the Shopify-style adapter | An ordinary order moves through all three steps |
| Cedar Grove Grocers | Rice, lentils, cooking oil, canned tomatoes | Checkout system, using the REST adapter | A large basket pauses for a manager's approval |
| Orchard Lane Produce | Apples, bananas, tomatoes, spinach, carrots | CSV spreadsheet | Good orders import while an incorrect row stays visible |
| Harbor Fresh Foods | Salmon, frozen shrimp, broccoli, mango | Online store, using the Shopify-style adapter | A stock shortage stops an order; restocking allows a retry |
| Sunrise Neighborhood Pantry | Bread, peanut butter, oats, milk, eggs, cheese | Pickup system, using the REST adapter | Click Process on an order during the presentation |

## Opening, about 20 seconds

Say: "Imagine these five grocery stores use different ways to receive orders.
One uses an online shop, another has a checkout system, and another sends a
spreadsheet. BridgOps brings those orders into one place, checks what can be
fulfilled, and shows the manager anything that needs a decision."

Explain only three terms as needed:

- Retailer: a store using the platform.
- SKU: a product code. Our codes include the food name and pack size.
- Reservation: setting stock aside for an order so it is not sold twice.

## 1. Start with a simple grocery basket

Select **Maplewood Fresh Market**, then open **MW-1001** in Orders. It contains
two strawberry packs, a gallon of milk and a loaf of sourdough, totaling **$19.76**.
Open its execution details.

Say: "First we check there is enough stock. Next we set those products aside.
Finally, we ask fulfillment to handle the order. Each step has its own result,
so we can see where a problem happened."

The completed status means the fulfillment service accepted the request. This
application does not track a real delivery. The inventory and fulfillment APIs
are separate local services that stand in for outside systems.

## 2. Make a manager's decision

Select **Cedar Grove Grocers** and open **CG-2003**. The basket contains eight
10-pound rice bags and four gallons of sunflower oil, totaling **$207.88**.
Its assigned workflow requires approval for orders above **$150**.

Say: "This could be a bulk order for a community meal. The store wants a manager
to review larger orders before setting stock aside."

In Workflows or Operations, open the pending approval. Enter a note such as
"Bulk order reviewed with the store manager" and choose **Approve**. Show that
the same execution continues through stock reservation and fulfillment.

Say: "The rule belongs to this store. The manager's decision is saved, and the
order continues without being entered again."

## 3. Show an everyday spreadsheet mistake

Select **Orchard Lane Produce**, open Integrations and inspect its import history.
**OL-3001**, **OL-3002** and **OL-3003** imported and completed. **OL-3004** has
a banana quantity of zero, so it stays in import history as an error and does
not create an order.

Say: "A spreadsheet can contain mistakes. We keep the good orders, and tell the
store which row needs fixing instead of hiding the problem."

Optional live correction: use the integration's CSV upload/paste form with your
development token and this content:

```csv
order_reference,product_code,qty,unit_price
OL-3004,BANANAS-2LB,2,1.49
```

The corrected order totals **$2.98**. Process it from Orders. The original failed
import remains as history, with a new successful import showing the correction.

## 4. Fix a stock shortage

Select **Harbor Fresh Foods** and open **HF-4003** in Operations. The basket needs
four one-pound salmon packs and one bag of frozen green beans. Only one salmon
pack was initially available, so the stock check failed before any reservation.

Say: "The order is valid, but the store cannot fill it yet. We stop here rather
than promising food that is not available."

In the repository-root PowerShell window, represent a fresh stock arrival:

```powershell
docker compose --profile app exec -T api python scripts/grocery_demo.py --restock-harbor
```

For host Python, use:

```powershell
cd D:\BridgOps\apps\api
.\.venv\Scripts\python.exe scripts/grocery_demo.py --restock-harbor
```

This sets available salmon stock to at least eight packs. In Operations, add a
note such as "New salmon stock received" and choose **Retry eligible step**.
Show the original failed check, the successful retry, reservation and fulfillment.

Say: "We fixed the cause and continued the same order. The history shows both
the problem and what we did to resolve it."

## 5. Process a new order live

Select **Sunrise Neighborhood Pantry** and open **SN-5003**. It contains a carton
of eggs and two packs of cheddar, totaling **$10.77**. It starts as received.
Choose **Process**, then inspect the completed steps.

Say: "This is what happens when another everyday grocery order arrives. The
store can follow it from receipt to fulfillment acceptance in one place."

## Close with Operations

Show the database-backed summary and execution list for the selected store.
Switch retailers to show that their orders, rules and operations are separate.

Say: "The useful part is bringing different systems together and making problems
visible. A manager can see what completed, what needs approval, and what needs
fixing without searching through several systems."

## Rerunning the script

The normal seed command reuses the same retailers, integrations, orders and import
records. It initializes only missing stock, and does not undo approvals, retries
or live processing. Edited integration/workflow settings cause a clear stop
instead of being overwritten. Existing unrelated retailers are kept.

After presenting, a rerun will therefore show your decisions as they now stand;
it will not recreate the original pending approval or shortage. Use a separate
fresh local database if you need to repeat every initial state from scratch.

The older three-retailer script remains available as `scripts/demo.py`.
