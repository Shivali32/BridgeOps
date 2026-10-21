import { request } from './client'
import type { Execution } from '../types/order'
export interface Definition {
  id: string; tenant_id: string; name: string; enabled: boolean; is_default: boolean
  version: number; configuration: { name: string; description?: string; trigger: string; steps: unknown[] }
}
export interface Approval {
  id: string; tenant_id: string; execution_id: string; step_name: string; reason: string
  status: string; decision_note: string | null; development_operator: string | null
  created_at: string; decided_at: string | null
}
export const getDefinitions = (t: string, signal?: AbortSignal) => request<Definition[]>(`/tenants/${t}/workflow-definitions?limit=100`, { signal })
export const saveDefinition = (t: string, data: object, id?: string) => request<Definition>(`/tenants/${t}/workflow-definitions${id ? '/' + id : ''}`, { method: id ? 'PATCH' : 'POST', body: JSON.stringify(data) })
export const getVersions = (t: string, id: string) => request<{ version: number; snapshot: object; created_at: string }[]>(`/tenants/${t}/workflow-definitions/${id}/versions`)
export const getApprovals = (t: string, status = 'pending', signal?: AbortSignal) => request<Approval[]>(`/tenants/${t}/approvals${status ? '?status=' + status : ''}`, { signal })
export const decideApproval = (t: string, id: string, decision: string, note: string, operator: string) => request<Execution>(`/tenants/${t}/approvals/${id}/decision`, { method: 'POST', body: JSON.stringify({ decision, note, development_operator: operator }) })
export const getExecution = (t: string, id: string) => request<Execution>(`/tenants/${t}/executions/${id}`)
