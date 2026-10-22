import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { errorMessage } from '../api/client'
import { getIntegrations, saveIntegration } from '../api/integrations'
import type { Integration } from '../api/integrations'
import { decideApproval, getApprovals, getDefinitions, getExecution, getVersions, saveDefinition } from '../api/workflows'
import type { Approval, Definition } from '../api/workflows'
import type { Execution } from '../types/order'
import { ExecutionDetails } from './ExecutionDetails'

const standard = ['inventory_check', 'inventory_reservation', 'fulfillment_request'].map(type => ({ id: type, type }))
function approvalPreset(threshold: string) {
  return [{ id: 'value_check', type: 'condition', rules: { match: 'all', rules: [{ field: 'order_total', operator: 'greater_than', value: threshold }] } }, { id: 'approve_order', type: 'approval', when: { condition_step: 'value_check', matches: true }, reason: `Order value exceeds ${threshold}` }, ...standard]
}

function WorkflowEditor({ tenant, value, onSaved }: { tenant: string; value: Definition | null; onSaved: () => void }) {
  const [name, setName] = useState(value?.name ?? '')
  const [description, setDescription] = useState(value?.configuration.description ?? '')
  const [enabled, setEnabled] = useState(value?.enabled ?? true)
  const [isDefault, setDefault] = useState(value?.is_default ?? false)
  const [steps, setSteps] = useState(JSON.stringify(value?.configuration.steps ?? standard, null, 2))
  const [threshold, setThreshold] = useState('500.00')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('')
    try {
      const parsed: unknown = JSON.parse(steps)
      if (!Array.isArray(parsed)) throw new Error('Workflow steps must be an array.')
      await saveDefinition(tenant, { name, description, enabled, is_default: isDefault, trigger: 'order_processing', steps: parsed, ...(value && { expected_version: value.version }) }, value?.id)
      onSaved()
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return <form className="tenant-form" aria-label="Workflow configuration" onSubmit={e => void save(e)}><h3>{value ? `Edit ${value.name}, version ${value.version}` : 'Create workflow'}</h3><fieldset disabled={busy}>
    <label className="form-field">Workflow name<input required value={name} maxLength={100} onChange={e => setName(e.target.value)} /></label>
    <label className="form-field">Description<input value={description} maxLength={500} onChange={e => setDescription(e.target.value)} /></label>
    <label className="form-field">Trigger<select value="order_processing" onChange={() => {}}><option value="order_processing">Order processing requested</option></select></label>
    <label><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} /> Workflow enabled</label>{' '}
    <label><input type="checkbox" checked={isDefault} onChange={e => setDefault(e.target.checked)} /> Default for this retailer</label>
    <div className="form-actions"><button type="button" onClick={() => setSteps(JSON.stringify(standard, null, 2))}>Use standard steps</button><label>Approval threshold<input type="number" min="0" step="0.01" value={threshold} onChange={e => setThreshold(e.target.value)} /></label><button type="button" onClick={() => setSteps(JSON.stringify(approvalPreset(threshold), null, 2))}>Use approval steps</button></div>
    {/* <label className="form-field">Workflow steps JSON<textarea rows={15} required value={steps} onChange={e => setSteps(e.target.value)} /></label>
    <p>Supported: condition, approval, inventory_check, inventory_reservation, fulfillment_request. Approval branches can reference earlier condition steps. The server validates every configuration.</p> */}
    <button type="submit">{busy ? 'Saving workflow...' : 'Save workflow'}</button>
  </fieldset>{error && <p role="alert">{error}</p>}</form>
}

export function ApprovalPanel({ tenant }: { tenant: string }) {
  const [values, setValues] = useState<Approval[]>([])
  const [status, setStatus] = useState('pending')
  const [note, setNote] = useState('')
  const [operator, setOperator] = useState('Local demo operator (unverified)')
  const [execution, setExecution] = useState<Execution | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    const c = new AbortController()
    getApprovals(tenant, status, c.signal).then(v => { if (!c.signal.aborted) setValues(v) }).catch(e => { if (!c.signal.aborted) setError(errorMessage(e)) })
    return () => c.abort()
  }, [tenant, status, refresh])
  async function decide(value: Approval, action: string) {
    setBusy(true); setError('')
    try { setExecution(await decideApproval(tenant, value.id, action, note, operator)); setRefresh(v => v + 1); setNote('') }
    catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return <section><div className="section-header"><h3>Approvals</h3><button disabled={busy} onClick={() => setRefresh(v => v + 1)}>Refresh approvals</button></div>
    <p>Local demo decisions. Operator names are self-reported and unverified.</p>
    <label className="form-field">Approval status<select value={status} onChange={e => setStatus(e.target.value)}><option value="pending">Pending</option><option value="approved">Approved</option><option value="rejected">Rejected</option><option value="">All decisions</option></select></label>
    <label className="form-field">Decision note<textarea maxLength={1000} value={note} onChange={e => setNote(e.target.value)} /></label>
    <label className="form-field">Development operator<input required maxLength={100} value={operator} onChange={e => setOperator(e.target.value)} /></label>
    {error && <p role="alert">{error}</p>}{values.length === 0 && <p>No {status || 'recorded'} approvals.</p>}
    <ul>{values.map(a => <li key={a.id}><strong>{a.reason}</strong> · {a.status}<p>Execution <code>{a.execution_id}</code> · {new Date(a.created_at).toLocaleString()}</p>{a.decision_note && <p>{a.development_operator}: {a.decision_note}</p>}
      <div className="table-actions"><button disabled={busy} onClick={() => { setError(''); getExecution(tenant, a.execution_id).then(setExecution).catch(e => setError(errorMessage(e))) }}>Inspect approval {a.id}</button>{a.status === 'pending' && <><button disabled={busy || !operator.trim()} onClick={() => void decide(a, 'approve')}>Approve {a.id}</button><button disabled={busy || !operator.trim()} onClick={() => void decide(a, 'reject')}>Reject {a.id}</button></>}</div>
    </li>)}</ul>
    {execution && <><h4>Order and rule context</h4><pre>{JSON.stringify({ order_id: execution.order_id, items: execution.definition_snapshot.order_items, source: execution.definition_snapshot.source, steps: execution.definition_snapshot.steps }, null, 2)}</pre><ExecutionDetails execution={execution} /></>}
  </section>
}

export default function WorkflowManager({ tenant }: { tenant: string }) {
  const [values, setValues] = useState<Definition[]>([])
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [editing, setEditing] = useState<Definition | null>(null)
  const [source, setSource] = useState('')
  const [workflow, setWorkflow] = useState('')
  const [history, setHistory] = useState<object[]>([])
  const [error, setError] = useState('')
  const [refresh, setRefresh] = useState(0)
  useEffect(() => {
    const c = new AbortController()
    Promise.all([getDefinitions(tenant, c.signal), getIntegrations(tenant, c.signal)]).then(([v, i]) => { if (!c.signal.aborted) { setValues(v); setIntegrations(i) } }).catch(e => { if (!c.signal.aborted) setError(errorMessage(e)) })
    return () => c.abort()
  }, [tenant, refresh])
  async function assign(e: FormEvent) {
    e.preventDefault(); setError('')
    const integration = integrations.find(i => i.id === source)
    if (!integration) return
    try { await saveIntegration(tenant, { name: integration.name, connector_type: integration.connector_type, enabled: integration.enabled, mapping: integration.mapping, expected_version: integration.version, workflow_id: workflow || null }, integration.id); setRefresh(v => v + 1) }
    catch (e) { setError(errorMessage(e)) }
  }
  return <section><div className="section-header"><h3>Workflow definitions</h3><button onClick={() => setRefresh(v => v + 1)}>Refresh workflows</button></div>
    {error && <p role="alert">{error}</p>}
    <ul>{values.map(v => <li key={v.id}>{v.name} · v{v.version} · {v.enabled ? 'Enabled' : 'Disabled'}{v.is_default && ' · Retailer default'}<div className="table-actions"><button onClick={() => setEditing(v)}>Edit {v.name}</button><button onClick={() => { getVersions(tenant, v.id).then(setHistory).catch(e => setError(errorMessage(e))) }}>Versions of {v.name}</button></div></li>)}</ul>
    <WorkflowEditor key={editing ? editing.id + editing.version : 'new-' + refresh} tenant={tenant} value={editing} onSaved={() => { setEditing(null); setRefresh(v => v + 1) }} />
    {editing && <button onClick={() => setEditing(null)}>Cancel workflow edit</button>}
    {history.length > 0 && <details open><summary>Workflow versions</summary><pre>{JSON.stringify(history, null, 2)}</pre></details>}
    <form className="tenant-form" onSubmit={e => void assign(e)}><h3>Assign workflow to integration</h3><label className="form-field">Source integration<select required value={source} onChange={e => { setSource(e.target.value); setWorkflow(integrations.find(i => i.id === e.target.value)?.workflow_id ?? '') }}><option value="">Select source</option>{integrations.map(i => <option value={i.id} key={i.id}>{i.name} (version {i.version})</option>)}</select></label><label className="form-field">Assigned workflow<select value={workflow} onChange={e => setWorkflow(e.target.value)}><option value="">Use retailer default or built-in standard</option>{values.map(v => <option value={v.id} key={v.id}>{v.name}{!v.enabled && ' (disabled)'}</option>)}</select></label><button type="submit">Save workflow assignment</button></form>
    <ApprovalPanel tenant={tenant} />
  </section>
}
