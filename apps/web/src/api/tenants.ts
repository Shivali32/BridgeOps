
import type {
  Tenant,
  TenantCreate,
  TenantUpdate,
} from '../types/tenant'

const API_BASE = '/api/v1/tenants'

async function handleResponse<T>(
  response: Response
): Promise<T> {
  if (!response.ok) {
    if (response.status === 409) {
      throw new Error('A retailer with this slug already exists.')
    }

    if (response.status === 404) {
      throw new Error('Retailer not found.')
    }

    if (response.status === 422) {
      throw new Error('Invalid retailer information.')
    }

    throw new Error(
      `Request failed (HTTP ${response.status})`
    )
  }

  return (await response.json()) as T
}

export async function getTenants(
  signal?: AbortSignal
): Promise<Tenant[]> {
  const response = await fetch(API_BASE, { signal })

  return handleResponse<Tenant[]>(response)
}

export async function createTenant(
  data: TenantCreate
): Promise<Tenant> {
  const response = await fetch(API_BASE, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  })

  return handleResponse<Tenant>(response)
}

export async function updateTenant(
  id: string,
  data: TenantUpdate
): Promise<Tenant> {
  const response = await fetch(`${API_BASE}/${id}`, {
    method: 'PATCH',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(data),
  })

  return handleResponse<Tenant>(response)
}

export async function deactivateTenant(
  id: string
): Promise<void> {
  const response = await fetch(`${API_BASE}/${id}`, {
    method: 'DELETE',
  })

  if (!response.ok) {
    throw new Error(
      `Unable to deactivate retailer (HTTP ${response.status})`
    )
  }
}
