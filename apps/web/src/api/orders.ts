import { request } from './client'
import type { Execution, Order, OrderInput } from '../types/order'

export const getOrders = (tenant: string, offset = 0, signal?: AbortSignal) =>
  request<Order[]>(`/tenants/${tenant}/orders?limit=10&offset=${offset}`, { signal })
export const createOrder = (tenant: string, data: OrderInput) =>
  request<Order>(`/tenants/${tenant}/orders`, { method: 'POST', body: JSON.stringify(data) })
export const processOrder = (tenant: string, id: string) =>
  request<Execution>(`/tenants/${tenant}/orders/${id}/process`, { method: 'POST' })
export const getExecutions = (tenant: string, id: string, signal?: AbortSignal) =>
  request<Execution[]>(`/tenants/${tenant}/orders/${id}/executions`, { signal })
