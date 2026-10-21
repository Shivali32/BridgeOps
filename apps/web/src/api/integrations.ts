import { request } from './client'
export interface Mapping {
  external_id: string; items: string; sku: string; quantity: string; unit_price: string | null
  price_in_cents: boolean; default_quantity: number | null; default_price: string | null
}
export interface ConnectorInfo { type: string; default_mapping: Mapping }
export interface Integration {
  id: string; tenant_id: string; name: string; connector_type: string; enabled: boolean
  version: number; mapping: Mapping; created_at: string
}
export interface ImportResult {
  id: string; integration_id: string; order_id: string | null; source_reference: string | null
  status: string; duplicate: boolean; row_numbers: number[]; error_message: string | null; created_at: string
}
export const getIntegrations = (t: string, signal?: AbortSignal) => request<Integration[]>(`/tenants/${t}/integrations?limit=100`, { signal })
export const getConnectors = (t: string, signal?: AbortSignal) => request<ConnectorInfo[]>(`/tenants/${t}/connectors`, { signal })
export const getImports = (t: string, signal?: AbortSignal) => request<ImportResult[]>(`/tenants/${t}/imports`, { signal })
export const saveIntegration = (t: string, data: object, id?: string) => request<Integration>(`/tenants/${t}/integrations${id ? '/' + id : ''}`, { method: id ? 'PATCH' : 'POST', body: JSON.stringify(data) })
export const importPayload = (t: string, id: string, payload: object, token: string) => request<ImportResult>(`/tenants/${t}/integrations/${id}/ingest`, { method: 'POST', headers: { 'X-Development-Token': token }, body: JSON.stringify(payload) })
export const importCsv = (t: string, id: string, csv: string, token: string) => request<ImportResult[]>(`/tenants/${t}/integrations/${id}/csv`, { method: 'POST', headers: { 'X-Development-Token': token }, body: JSON.stringify({ csv_text: csv }) })
