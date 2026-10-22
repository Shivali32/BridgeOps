import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { errorMessage } from '../api/client'
import { getIntegrations } from '../api/integrations'
import type { Integration } from '../api/integrations'
import { getOrders } from '../api/orders'
import { getExecution } from '../api/workflows'
import { getAudit, getOperations, getSummary, recoverExecution } from '../api/operations'
import type { Audit, Operation, Summary } from '../api/operations'
import type { Execution, Order } from '../types/order'
import { ExecutionDetails } from './ExecutionDetails'
import { ApprovalPanel } from './WorkflowManager'
import Status from './Status'

export function RecoveryPanel({ tenant, execution, onChanged }: { tenant: string; execution: Execution; onChanged: () => void }) {
  const [note, setNote] = useState('')
  const [operator, setOperator] = useState('Local demo operator (unverified)')
  const [reference, setReference] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [pending, setPending] = useState<{ fingerprint: string; key: string } | null>(null)
  const canRecover = ['failed', 'needs_attention', 'running'].includes(execution.status) && !['approval_pending', 'approval_rejected'].includes(execution.error_category ?? '')
  const latest = new Map(execution.steps.map(s => [s.step_name, s]))
  const unresolved = [...latest.values()].filter(s => ['failed', 'unknown', 'running'].includes(s.status))
  const retryable = unresolved.some(s => s.retryable && s.attempt_number < 3)
  const hasReference = unresolved.some(s => 'idempotency_key' in s.input_summary)
  async function action(kind: string) {
    if (!note.trim() || !operator.trim()) { setError('Add a resolution note and development operator.'); return }
    setBusy(true); setError(''); setMessage('')
    const data = { action: kind, note: note.trim(), development_operator: operator.trim(), external_reference: kind === 'verify_reference' ? reference : null }
    const fingerprint = JSON.stringify(data)
    const key = pending?.fingerprint === fingerprint ? pending.key : crypto.randomUUID()
    setPending({ fingerprint, key })
    try { const value = await recoverExecution(tenant, execution.id, { ...data, request_key: key }); setPending(null); setMessage(`Action recorded. Execution is ${value.status.replaceAll('_', ' ')}.`); onChanged() }
    catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return <section className="tenant-form"><h4>Failure recovery and investigation</h4><p>Successful steps are preserved. Business operations are reconciled before retry. Retry limit: three attempts. Running executions can be reconciled after 60 seconds without progress.</p>
    <fieldset disabled={busy}>
      <label className="form-field">Resolution note<textarea required maxLength={1000} value={note} onChange={e => setNote(e.target.value)} /></label>
      <label className="form-field">Recovery development operator<input maxLength={100} value={operator} onChange={e => setOperator(e.target.value)} /></label>
      <label className="form-field">External reference UUID<input value={reference} onChange={e => setReference(e.target.value)} /></label>
      <div className="table-actions"><button disabled={!canRecover || !retryable || execution.status === 'running'} onClick={() => void action('retry')}>Retry eligible step</button><button disabled={!canRecover || !hasReference} onClick={() => void action('reconcile')}>Reconcile provider outcome</button><button disabled={!canRecover || !hasReference || !reference.trim()} onClick={() => void action('verify_reference')}>Verify external reference</button><button onClick={() => void action('investigated')}>Record investigation</button></div>
    </fieldset>{busy && <p>Recording recovery action...</p>}{error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
  </section>
}

const emptyFilters = { status: '', integration_id: '', approval_status: '', error_category: '', start: '', end: '' }
export default function OperationsDashboard({ tenant }: { tenant: string }) {
  const [filters, setFilters] = useState(emptyFilters)
  const [active, setActive] = useState(emptyFilters)
  const [offset, setOffset] = useState(0)
  const [values, setValues] = useState<Operation[]>([])
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [orders, setOrders] = useState<Order[]>([])
  const [summary, setSummary] = useState<Summary | null>(null)
  const [selected, setSelected] = useState('')
  const [execution, setExecution] = useState<Execution | null>(null)
  const [audit, setAudit] = useState<Audit[]>([])
  const [refresh, setRefresh] = useState(0)
  const [error, setError] = useState('')
  const [detailsError, setDetailsError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    const c = new AbortController()
    async function load() {
      setLoading(true); setError('')
      const query = new URLSearchParams({ limit: '10', offset: String(offset) })
      const dates = new URLSearchParams()
      for (const [key, value] of Object.entries(active)) {
        if (!value) continue
        const converted = ['start', 'end'].includes(key) ? new Date(value).toISOString() : value
        query.set(key, converted); if (['start', 'end'].includes(key)) dates.set(key, converted)
      }
      try {
        const [rows, totals, sources, savedOrders] = await Promise.all([getOperations(tenant, query.toString(), c.signal), getSummary(tenant, dates.toString(), c.signal), getIntegrations(tenant, c.signal), getOrders(tenant, 0, c.signal)])
        if (!c.signal.aborted) { setValues(rows); setSummary(totals); setIntegrations(sources); setOrders(savedOrders) }
      } catch (e) { if (!c.signal.aborted) setError(errorMessage(e)) }
      finally { if (!c.signal.aborted) setLoading(false) }
    }
    void load(); return () => c.abort()
  }, [tenant, active, offset, refresh])
  useEffect(() => {
    const c = new AbortController()
    async function load() {
      setDetailsError('')
      if (!selected) return
      try {
        const [result, events] = await Promise.all([getExecution(tenant, selected, c.signal), getAudit(tenant, selected, c.signal)])
        if (!c.signal.aborted) { setExecution(result); setAudit(events) }
      } catch (e) { if (!c.signal.aborted) setDetailsError(errorMessage(e)) }
    }
    void load(); return () => c.abort()
  }, [tenant, selected, refresh])
  useEffect(() => {
    const timer = window.setInterval(() => setRefresh(v => v + 1), 2000)
    return () => window.clearInterval(timer)
  }, [])
  function apply(e: FormEvent) { e.preventDefault(); setOffset(0); setActive({ ...filters }) }
  return <section><div className="section-header"><h3>Operations console</h3><button disabled={loading} onClick={() => setRefresh(v => v + 1)}>Refresh operations</button></div>
    <p>All views belong to the selected retailer. Summaries use the selected date range; other filters apply to the execution list.</p>
    <form className="tenant-form" onSubmit={apply}><div className="mapping-grid">
      <label className="form-field">Execution status<select value={filters.status} onChange={e => setFilters({ ...filters, status: e.target.value })}><option value="">All statuses</option>{['running', 'completed', 'failed', 'needs_attention', 'pending'].map(s => <option key={s}>{s}</option>)}</select></label>
      <label className="form-field">Integration filter<select value={filters.integration_id} onChange={e => setFilters({ ...filters, integration_id: e.target.value })}><option value="">All sources</option>{integrations.map(i => <option key={i.id} value={i.id}>{i.name}</option>)}</select></label>
      <label className="form-field">Approval filter<select value={filters.approval_status} onChange={e => setFilters({ ...filters, approval_status: e.target.value })}><option value="">Any approval state</option>{['pending', 'approved', 'rejected'].map(s => <option key={s}>{s}</option>)}</select></label>
      <label className="form-field">Error category<select value={filters.error_category} onChange={e => setFilters({ ...filters, error_category: e.target.value })}><option value="">All errors</option>{['validation_error', 'configuration_error', 'insufficient_stock', 'provider_rejected', 'provider_unavailable', 'timeout_unknown', 'authorization_error', 'approval_pending', 'approval_rejected'].map(s => <option key={s}>{s}</option>)}</select></label>
      <label className="form-field">From time<input type="datetime-local" value={filters.start} onChange={e => setFilters({ ...filters, start: e.target.value })} /></label><label className="form-field">To time<input type="datetime-local" value={filters.end} onChange={e => setFilters({ ...filters, end: e.target.value })} /></label>
    </div><button type="submit">Apply operations filters</button></form>
    {loading && <p>Loading operations...</p>}{error && <p role="alert">{error}</p>}
    {summary && <div className="metrics-grid">
      <div><strong>{Object.values(summary.orders).reduce((a, b) => a + b, 0)}</strong><span>Orders received</span></div><div><strong>{summary.orders.queued ?? 0}</strong><span>Orders queued</span></div><div><strong>{summary.orders.completed ?? 0}</strong><span>Orders completed</span></div><div><strong>{summary.executions.failed ?? 0}</strong><span>Failed workflows</span></div><div><strong>{summary.executions.needs_attention ?? 0}</strong><span>Workflows needing attention</span></div><div><strong>{summary.pending_approvals}</strong><span>Pending approvals</span></div><div><strong>{summary.import_failures}</strong><span>Import failures</span></div><div><strong>{summary.retry_requests}</strong><span>Retry requests</span></div><div><strong>{summary.average_completed_duration_seconds === null ? 'No completed runs' : `${summary.average_completed_duration_seconds.toFixed(2)}s`}</strong><span>Average completed elapsed time, including approval waits</span></div>
    </div>}
    {!loading && !error && !values.length && <p>No executions match these filters.</p>}
    <div className="table-container"><table className="tenant-table"><thead><tr><th>Order</th><th>Workflow</th><th>Source</th><th>Status</th><th>Last error</th><th>Started</th><th>Details</th></tr></thead><tbody>{values.map(v => <tr key={v.id}><td>{v.external_order_id}</td><td>{v.workflow_name} v{v.workflow_version}</td><td>{v.source.source ?? 'Order API'}</td><td><Status value={v.status === 'pending' ? 'queued' : v.status} /></td><td>{v.error_category && <strong>{v.error_category}: </strong>}{v.error_message ?? 'None'}</td><td>{v.started_at ? new Date(v.started_at).toLocaleString() : 'Pending'}</td><td><button onClick={() => { setExecution(null); setAudit([]); setSelected(v.id) }}>Inspect {v.external_order_id}</button></td></tr>)}</tbody></table></div>
    <div className="pagination"><button disabled={offset === 0 || loading} onClick={() => setOffset(v => Math.max(0, v - 10))}>Previous executions</button><span>Page {offset / 10 + 1}</span><button disabled={values.length < 10 || loading} onClick={() => setOffset(v => v + 10)}>Next executions</button></div>
    {detailsError && <p role="alert">{detailsError}</p>}
    {execution && <><h4>Order {execution.order_id}</h4><pre>{JSON.stringify({ source: execution.definition_snapshot.source, items: execution.definition_snapshot.order_items }, null, 2)}</pre><ExecutionDetails execution={execution} /><RecoveryPanel tenant={tenant} execution={execution} onChanged={() => setRefresh(v => v + 1)} /><h4>Audit history (first 50 events)</h4>{audit.length === 0 && <p>No manual actions recorded.</p>}<ul>{audit.map(a => <li key={a.id}><strong>{a.action.replaceAll('_', ' ')}</strong> · {new Date(a.created_at).toLocaleString()}<p>{a.development_operator} (unverified): {a.note}</p><details><summary>State change</summary><pre>{JSON.stringify({ before: a.previous_state, after: a.new_state }, null, 2)}</pre></details></li>)}</ul></>}
    <h4>Latest saved orders, all dates</h4><ul>{orders.map(o => <li key={o.id}>{o.external_order_id} · <Status value={o.status} /> · {new Date(o.created_at).toLocaleString()}</li>)}</ul>
    <ApprovalPanel key={`approvals-${refresh}`} tenant={tenant} />
  </section>
}
