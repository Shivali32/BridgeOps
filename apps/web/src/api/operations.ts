import { request } from './client'
import type { Execution } from '../types/order'
export interface Operation {
  id: string; order_id: string; tenant_id: string; external_order_id: string; status: string
  source: { source?: string; source_connector?: string; integration_id?: string }
  workflow_name: string; workflow_version: number; started_at: string | null; completed_at: string | null
  error_category: string | null; error_message: string | null
}
export interface Summary {
  orders: Record<string, number>; executions: Record<string, number>; pending_approvals: number
  import_failures: number; retry_requests: number; average_completed_duration_seconds: number | null
}
export interface Audit {
  id: string; action: string; previous_state: object; new_state: object; note: string
  development_operator: string; created_at: string
}
export const getOperations = (t: string, query: string, signal?: AbortSignal) => request<Operation[]>(`/tenants/${t}/operations?${query}`, { signal })
export const getSummary = (t: string, query: string, signal?: AbortSignal) => request<Summary>(`/tenants/${t}/operations/summary?${query}`, { signal })
export const getAudit = (t: string, id: string, signal?: AbortSignal) => request<Audit[]>(`/tenants/${t}/executions/${id}/audit`, { signal })
export const recoverExecution = (t: string, id: string, data: object) => request<Execution>(`/tenants/${t}/executions/${id}/recovery`, { method: 'POST', body: JSON.stringify(data) })
