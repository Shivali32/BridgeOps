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
