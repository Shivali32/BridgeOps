import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { getConnectors, getIntegrations, getImports, importCsv, importPayload, saveIntegration } from '../api/integrations'
import type { ConnectorInfo, Integration, ImportResult, Mapping } from '../api/integrations'
import { errorMessage } from '../api/client'
import Status from './Status'

function IntegrationEditor({ tenant, connectors, value, onSaved }: { tenant: string; connectors: ConnectorInfo[]; value: Integration | null; onSaved: () => void }) {
  const [name, setName] = useState(value?.name ?? '')
  const [type, setType] = useState(value?.connector_type ?? connectors[0].type)
  const [mapping, setMapping] = useState<Mapping>(value?.mapping ?? connectors[0].default_mapping)
  const [enabled, setEnabled] = useState(value?.enabled ?? true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function save(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError('')
    try { await saveIntegration(tenant, { name, connector_type: type, enabled, mapping, ...(value && { expected_version: value.version, ...(value.workflow_id && { workflow_id: value.workflow_id }) }) }, value?.id); onSaved() }
    catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return <form className="tenant-form" aria-label="Integration configuration" onSubmit={e => void save(e)}>
    <h3>{value ? `Edit ${value.name}, version ${value.version}` : 'Add integration'}</h3>
    <fieldset disabled={busy}>
      <label className="form-field">Integration name<input required maxLength={100} value={name} onChange={e => setName(e.target.value)} /></label>
      <label className="form-field">Connector type<select value={type} disabled={!!value} onChange={e => { setType(e.target.value); setMapping(connectors.find(c => c.type === e.target.value)!.default_mapping) }}>{connectors.map(c => <option key={c.type}>{c.type}</option>)}</select></label>
      <label><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} /> Integration enabled</label>
      <h4>Source field mapping</h4>
      <div className="mapping-grid">{(['external_id', 'items', 'sku', 'quantity', 'unit_price'] as const).map(key => <label className="form-field" key={key}>{key.replaceAll('_', ' ')}<input required={key !== 'unit_price'} value={mapping[key] ?? ''} onChange={e => setMapping({ ...mapping, [key]: key === 'unit_price' && !e.target.value ? null : e.target.value })} /></label>)}</div>
      <label><input type="checkbox" checked={mapping.price_in_cents} onChange={e => setMapping({ ...mapping, price_in_cents: e.target.checked })} /> Source prices are in cents</label>
      <div className="mapping-grid"><label className="form-field">Default quantity<input type="number" min="1" step="1" value={mapping.default_quantity ?? ''} onChange={e => setMapping({ ...mapping, default_quantity: e.target.value ? Number(e.target.value) : null })} /></label><label className="form-field">Default unit price<input type="number" min="0" step="0.01" value={mapping.default_price ?? ''} onChange={e => setMapping({ ...mapping, default_price: e.target.value || null })} /></label></div>
      <button type="submit">{busy ? 'Saving integration...' : 'Save integration'}</button>
    </fieldset>
    {error && <p role="alert">{error}</p>}
  </form>
}

export function ImportPanel({ tenant, integration, onImported }: { tenant: string; integration: Integration; onImported: () => void }) {
  const [token, setToken] = useState('')
  const [text, setText] = useState(integration.connector_type === 'csv' ? 'order_reference,product_code,qty,unit_price\nCSV-1,A,2,12.50\nCSV-2,A,0,1.00' : JSON.stringify(integration.connector_type === 'shopify_simulated' ? { id: 'SHOP-1', line_items: [{ sku: 'A', quantity: 2, price: '12.50' }] } : { reference: 'REST-1', products: [{ product_code: 'A', count: 2, price_cents: 1250 }] }, null, 2))
  const [results, setResults] = useState<ImportResult[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(e: FormEvent) {
    e.preventDefault(); setBusy(true); setError(''); setResults([])
    try {
      if (new TextEncoder().encode(text).length > 262144) throw new Error('Import is limited to 256 KiB.')
      const result = integration.connector_type === 'csv' ? await importCsv(tenant, integration.id, text, token) : [await importPayload(tenant, integration.id, JSON.parse(text) as object, token)]
      setResults(result); onImported()
    } catch (e) { setError(errorMessage(e)) } finally { setBusy(false) }
  }
  return <form className="tenant-form" aria-label="Import source data" onSubmit={e => void submit(e)}>
    <h3>Test {integration.name}</h3><p>Imports save orders. Process them from the Orders tab.</p>
    <fieldset disabled={busy || !integration.enabled}>
      <label className="form-field">Development ingestion token<input type="password" autoComplete="off" required value={token} onChange={e => setToken(e.target.value)} /></label>
      <label className="form-field">{integration.connector_type === 'csv' ? 'CSV content' : 'Provider JSON'}<textarea rows={9} required value={text} onChange={e => setText(e.target.value)} /></label>
      {integration.connector_type === 'csv' && <label className="form-field">Upload CSV<input type="file" accept=".csv,text/csv" onChange={e => {
        const file = e.target.files?.[0]; if (!file) return
        if (file.size > 262144) { setError('Import is limited to 256 KiB.'); return }
        file.text().then(setText).catch(e => setError(errorMessage(e)))
      }} /></label>}
      <button type="submit">{busy ? 'Importing...' : 'Import orders'}</button>
    </fieldset>
    {!integration.enabled && <p>Enable this integration to import orders.</p>}
    {error && <p role="alert">{error}</p>}
    <ImportResults results={results} />
  </form>
}

function ImportResults({ results }: { results: ImportResult[] }) {
  return <ul>{results.map(r => <li key={r.id}>{r.source_reference ?? 'Invalid input'}: <Status value={r.status} /> {r.duplicate && '(existing order)'} {r.row_numbers.length > 0 && `Rows ${r.row_numbers.join(', ')}`} {r.error_message && <span role="alert">{r.error_message}</span>}</li>)}</ul>
}

export default function IntegrationManager({ tenant }: { tenant: string }) {
  const [integrations, setIntegrations] = useState<Integration[]>([])
  const [connectors, setConnectors] = useState<ConnectorInfo[]>([])
  const [imports, setImports] = useState<ImportResult[]>([])
  const [editing, setEditing] = useState<Integration | null>(null)
  const [testing, setTesting] = useState('')
  const [refresh, setRefresh] = useState(0)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    const c = new AbortController()
    async function load() {
      setLoading(true); setError('')
      try {
        const [values, types, history] = await Promise.all([getIntegrations(tenant, c.signal), getConnectors(tenant, c.signal), getImports(tenant, c.signal)])
        if (!c.signal.aborted) { setIntegrations(values); setConnectors(types); setImports(history) }
      } catch (e) { if (!c.signal.aborted) setError(errorMessage(e)) }
      finally { if (!c.signal.aborted) setLoading(false) }
    }
    void load(); return () => c.abort()
  }, [tenant, refresh])
  const selected = integrations.find(i => i.id === testing)
  return <section><div className="section-header"><h3>Integrations</h3><button onClick={() => setRefresh(v => v + 1)}>Refresh integrations</button></div>
    {error && <p role="alert">{error}</p>}{loading && <p>Loading integrations...</p>}
    <div className="table-container"><table className="tenant-table"><thead><tr><th>Name</th><th>Connector</th><th>Version</th><th>Status</th><th>Actions</th></tr></thead><tbody>{integrations.map(i => <tr key={i.id}><td>{i.name}</td><td>{i.connector_type}</td><td>{i.version}</td><td>{i.enabled ? 'Enabled' : 'Disabled'}</td><td className="table-actions"><button onClick={() => setEditing(i)}>Edit {i.name}</button><button onClick={() => setTesting(i.id)}>Test {i.name}</button></td></tr>)}</tbody></table></div>
    {connectors.length > 0 && <IntegrationEditor key={editing ? `${editing.id}-${editing.version}` : `new-${refresh}`} tenant={tenant} value={editing} connectors={connectors} onSaved={() => { setEditing(null); setRefresh(v => v + 1) }} />}
    {editing && <button onClick={() => setEditing(null)}>Cancel edit</button>}
    {selected && <ImportPanel key={selected.id} tenant={tenant} integration={selected} onImported={() => setRefresh(v => v + 1)} />}
    <h3>Recent imports</h3>{!imports.length && !loading && <p>No import history.</p>}<ImportResults results={imports} />
  </section>
}
