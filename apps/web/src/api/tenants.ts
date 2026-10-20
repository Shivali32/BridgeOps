
import type { Tenant } from '../types/tenant'

const API_BASE = '/api/v1'

export async function getTenants(
  signal?: AbortSignal
): Promise<Tenant[]> {
  const response = await fetch(`${API_BASE}/tenants`, {
    signal,
  })

  if (!response.ok) {
    throw new Error(
      `Unable to load tenants (HTTP ${response.status})`
    )
  }

  return (await response.json()) as Tenant[]
}
