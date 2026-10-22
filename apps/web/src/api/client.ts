export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api/v1${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options.headers },
  })
  if (!response.ok) {
    let message = `Request failed (HTTP ${response.status})`
    try {
      const body: unknown = await response.json()
      if (body && typeof body === 'object' && 'detail' in body) {
        if (typeof body.detail === 'string') message = body.detail
        else if (Array.isArray(body.detail)) message = body.detail.map((e: { loc?: string[]; msg?: string }) => `${e.loc?.join('.')}: ${e.msg}`).join('; ')
      }
    } catch { /* Keep the HTTP message when the response is not JSON. */ }
    throw new Error(message)
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}

export function errorMessage(error: unknown) {
  return error instanceof Error ? error.message : 'The request could not be completed.'
}
