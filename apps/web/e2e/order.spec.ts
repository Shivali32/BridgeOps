import { expect, test } from '@playwright/test'

test('operator creates and processes an order through the actual HTTP services', async ({ page, request }) => {
  const retailer = `Browser ${Date.now()}`
  const created = await request.post('http://127.0.0.1:8000/api/v1/tenants', { data: { name: retailer, slug: `browser-${Date.now()}` } })
  expect(created.status()).toBe(201)
  const tenant = await created.json() as { id: string }
  const stock = await request.put('http://127.0.0.1:8001/inventory/stock', { data: { tenant_id: tenant.id, sku: 'BROWSER-A', available: 10 } })
  expect(stock.ok()).toBeTruthy()
  await page.goto('/')
  await page.getByLabel('Retailer for orders').selectOption(tenant.id)
  await page.getByLabel('External order ID').fill('BROWSER-1')
  await page.getByLabel('SKU 1', { exact: true }).fill('BROWSER-A')
  await page.getByLabel('Quantity 1', { exact: true }).fill('2')
  await page.getByLabel('Unit price 1', { exact: true }).fill('12.50')
  await page.getByRole('button', { name: 'Save order', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Process BROWSER-1', exact: true })).toBeVisible()
  await page.getByRole('button', { name: 'Process BROWSER-1', exact: true }).click()
  await expect(page.getByText('Fulfillment request accepted. Delivery is outside this workflow.')).toBeVisible()
  await expect(page.getByText('Provider reference:', { exact: false })).toHaveCount(2)
  await page.screenshot({ path: 'test-results/order-workflow.png', fullPage: true })
})

test('operator configures a CSV integration and sees valid and invalid row results', async ({ page, request }) => {
  const created = await request.post('http://127.0.0.1:8000/api/v1/tenants', { data: { name: 'CSV browser retailer', slug: `csv-browser-${Date.now()}` } })
  const tenant = await created.json() as { id: string }
  await page.goto('/')
  await page.getByLabel('Retailer for orders').selectOption(tenant.id)
  await page.getByRole('button', { name: 'Integrations', exact: true }).click()
  await page.getByLabel('Integration name').fill('Browser CSV')
  await page.getByLabel('Connector type').selectOption('csv')
  await page.getByRole('button', { name: 'Save integration' }).click()
  await page.getByRole('button', { name: 'Test Browser CSV' }).click()
  await page.getByLabel('Development ingestion token').fill('ci_local_ingestion_token')
  await page.getByLabel('Upload CSV').setInputFiles({ name: 'orders.csv', mimeType: 'text/csv', buffer: Buffer.from('order_reference,product_code,qty,unit_price\nCSV-GOOD,A,2,12.50\nCSV-BAD,A,0,1.00') })
  await expect(page.getByLabel('CSV content')).toHaveValue(/CSV-GOOD/)
  await page.getByRole('button', { name: 'Import orders' }).click()
  await expect(page.getByText('succeeded', { exact: true }).first()).toBeVisible()
  await expect(page.getByText('failed', { exact: true }).first()).toBeVisible()
  const orders = await request.get(`http://127.0.0.1:8000/api/v1/tenants/${tenant.id}/orders`)
  expect((await orders.json() as unknown[]).length).toBe(1)
})
