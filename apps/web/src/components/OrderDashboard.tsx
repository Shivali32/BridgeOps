import { ExecutionDetails } from './ExecutionDetails'
export { ExecutionDetails } from './ExecutionDetails'
import WorkflowManager from './WorkflowManager'
import Status from './Status'
import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import IntegrationManager from './IntegrationManager'
import { getTenants } from '../api/tenants'
import { createOrder, getOrders, getExecutions, processOrder } from '../api/orders'
import { errorMessage } from '../api/client'
import type { Tenant } from '../types/tenant'
import type { Execution, Order } from '../types/order'


function OrderForm({ tenant, onSaved }: { tenant: string; onSaved: () => void }) {
  const [externalId, setExternalId] = useState('')
  const [items, setItems] = useState([{ sku: '', quantity: '1', unit_price: '' }])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault()
    setError('')
    if (items.some(i => !i.sku.trim() || !Number.isInteger(Number(i.quantity)) || Number(i.quantity) <= 0) || new Set(items.map(i => i.sku.trim())).size !== items.length) {
      setError('Use unique SKUs and positive whole quantities.'); return
    }
    setBusy(true)
    try {
      await createOrder(tenant, { external_order_id: externalId.trim(), items: items.map(i => ({ sku: i.sku.trim(), quantity: Number(i.quantity), unit_price: i.unit_price || null })) })
      setExternalId(''); setItems([{ sku: '', quantity: '1', unit_price: '' }]); onSaved()
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return <form onSubmit={e => void submit(e)} className="tenant-form" aria-label="New order">
    <h3>Submit order</h3>
    <fieldset disabled={busy}>
      <label className="form-field">External order ID<input required maxLength={100} value={externalId} onChange={e => setExternalId(e.target.value)} /></label>
      {items.map((item, index) => <div className="item-row" key={index}>
        <label>SKU {index + 1}<input required maxLength={100} value={item.sku} onChange={e => setItems(items.map((v, j) => j === index ? { ...v, sku: e.target.value } : v))} /></label>
        <label>Quantity {index + 1}<input type="number" min="1" step="1" required value={item.quantity} onChange={e => setItems(items.map((v, j) => j === index ? { ...v, quantity: e.target.value } : v))} /></label>
        <label>Unit price {index + 1}<input type="number" min="0" step="0.01" value={item.unit_price} onChange={e => setItems(items.map((v, j) => j === index ? { ...v, unit_price: e.target.value } : v))} /></label>
        <button type="button" disabled={items.length === 1} onClick={() => setItems(items.filter((_, j) => j !== index))}>Remove item {index + 1}</button>
      </div>)}
      <div className="form-actions"><button type="button" disabled={items.length >= 100} onClick={() => setItems([...items, { sku: '', quantity: '1', unit_price: '' }])}>Add item</button><button type="submit">{busy ? 'Saving...' : 'Save order'}</button></div>
    </fieldset>
    {error && <p role="alert" className="error-message">{error}</p>}
  </form>
}

export function Orders({ tenant }: { tenant: string }) {
  const [orders, setOrders] = useState<Order[]>([])
  const [selected, setSelected] = useState<Order | null>(null)
  const [executions, setExecutions] = useState<Execution[]>([])
  const [offset, setOffset] = useState(0)
  const [refresh, setRefresh] = useState(0)
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [detailsError, setDetailsError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      setLoading(true); setError('')
      try { const result = await getOrders(tenant, offset, controller.signal); if (!controller.signal.aborted) setOrders(result) }
      catch (e) { if (!controller.signal.aborted) setError(errorMessage(e)) }
      finally { if (!controller.signal.aborted) setLoading(false) }
    }
    void load(); return () => controller.abort()
  }, [tenant, offset, refresh])
  useEffect(() => {
    const controller = new AbortController()
    async function load() {
      if (!selected) return
      setDetailsError(''); setExecutions([])
      try { const result = await getExecutions(tenant, selected.id, controller.signal); if (!controller.signal.aborted) setExecutions(result) }
      catch (e) { if (!controller.signal.aborted) setDetailsError(errorMessage(e)) }
    }
    void load(); return () => controller.abort()
  }, [tenant, selected, refresh])
  async function process(order: Order) {
    setBusy(true); setDetailsError('')
    try { await processOrder(tenant, order.id); setSelected(order); setRefresh(v => v + 1) }
    catch (e) { setDetailsError(errorMessage(e)) } finally { setBusy(false) }
  }
  return <>
    <OrderForm tenant={tenant} onSaved={() => { setOffset(0); setRefresh(v => v + 1) }} />
    <div className="section-header"><h3>Orders</h3><button onClick={() => setRefresh(v => v + 1)} disabled={loading || busy}>Refresh orders</button></div>
    {error && <p role="alert">{error}</p>}{loading && <p>Loading orders...</p>}
    {!loading && !orders.length && <p>No orders for this retailer.</p>}
    <div className="table-container"><table className="tenant-table"><thead><tr><th>External ID</th><th>Status</th><th>Items</th><th>Received</th><th>Actions</th></tr></thead><tbody>
      {orders.map(order => <tr key={order.id}><td>{order.external_order_id}</td><td><Status value={order.status} /></td><td>{order.items.length}</td><td>{new Date(order.created_at).toLocaleString()}</td><td className="table-actions"><button onClick={() => setSelected(order)}>View {order.external_order_id}</button><button disabled={busy || order.status !== 'received'} onClick={() => void process(order)}>Process {order.external_order_id}</button></td></tr>)}
    </tbody></table></div>
    <div className="pagination"><button disabled={offset === 0 || loading || busy} onClick={() => setOffset(v => Math.max(0, v - 10))}>Previous orders</button><span>Page {offset / 10 + 1}</span><button disabled={orders.length < 10 || loading || busy} onClick={() => setOffset(v => v + 10)}>Next orders</button></div>
    {detailsError && <p role="alert">{detailsError}</p>}
    {selected && <section aria-label="Order details"><h3>{selected.external_order_id} details</h3><ul>{selected.items.map(i => <li key={i.sku}>{i.sku}: {i.quantity} units, price {i.unit_price ?? 'not provided'}</li>)}</ul>
      {!executions.length && !detailsError && <p>No workflow history yet.</p>}
      {executions.map(e => <ExecutionDetails key={e.id} execution={e} />)}
    </section>}
  </>
}

export default function OrderDashboard() {
  const [tab, setTab] = useState('orders')
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [selected, setSelected] = useState('')
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    getTenants(controller.signal).then(values => { if (!controller.signal.aborted) setTenants(values) }).catch(e => { if (!controller.signal.aborted) setError(errorMessage(e)) })
    return () => controller.abort()
  }, [refresh])
  return <section className="tenant-section"><div className="section-header"><div><h2>Order processing</h2><p>Save orders, run integrations and inspect each step.</p></div><button onClick={() => { setError(''); setRefresh(v => v + 1) }}>Refresh retailer choices</button></div>
    <p className="local-notice">Local demo. Tenant selection does not provide access control.</p>
    <label className="form-field">Retailer for orders<select value={selected} onChange={e => setSelected(e.target.value)}><option value="">Select a retailer</option>{tenants.map(t => <option key={t.id} value={t.id}>{t.name}{!t.is_active && ' (inactive)'}</option>)}</select></label>
    {error && <p role="alert">{error}</p>}
    {selected && <><nav className="workspace-nav" aria-label="Retail workspace"><button aria-pressed={tab === 'orders'} onClick={() => setTab('orders')}>Orders</button><button aria-pressed={tab === 'integrations'} onClick={() => setTab('integrations')}>Integrations</button><button aria-pressed={tab === 'workflows'} onClick={() => setTab('workflows')}>Workflows</button></nav>{tab === 'orders' ? <Orders key={selected} tenant={selected} /> : tab === 'integrations' ? <IntegrationManager key={selected} tenant={selected} /> : <WorkflowManager key={selected} tenant={selected} />}</>}
  </section>
}
