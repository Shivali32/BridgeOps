import { afterEach, expect, it, vi } from 'vitest'
import { request } from './client'

afterEach(() => vi.unstubAllGlobals())
it('shows field validation errors returned by FastAPI', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: [{ loc: ['body', 'items', 'quantity'], msg: 'Input should be greater than 0' }] }), { status: 422 })))
  await expect(request('/test')).rejects.toThrow('body.items.quantity: Input should be greater than 0')
})
it('handles a non-JSON service failure', async () => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('Unavailable', { status: 503 })))
  await expect(request('/test')).rejects.toThrow('HTTP 503')
})
