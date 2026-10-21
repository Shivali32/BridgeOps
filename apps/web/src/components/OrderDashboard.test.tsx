import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import OrderDashboard, { Orders, ExecutionDetails } from './OrderDashboard'
import { createOrder, getOrders, getExecutions, processOrder } from '../api/orders'
import { getTenants } from '../api/tenants'
import type { Execution, Order } from '../types/order'

vi.mock('../api/orders', () => ({ createOrder: vi.fn(), getOrders: vi.fn(), getExecutions: vi.fn(), processOrder: vi.fn() }))
vi.mock('../api/tenants', () => ({ getTenants: vi.fn() }))
const order: Order = { id: 'order-1', tenant_id: 'tenant-1', external_order_id: 'WEB-1', status: 'received', items: [{ sku: 'A', quantity: 2, unit_price: '12.50' }], created_at: '2026-10-21T12:00:00Z', updated_at: '2026-10-21T12:00:00Z' }
const execution: Execution = { id: 'run-1', tenant_id: 'tenant-1', order_id: 'order-1', status: 'needs_attention', started_at: '2026-10-21T12:00:00Z', completed_at: null, error_message: 'Response unavailable', error_category: 'timeout_unknown', definition_snapshot: { name: 'Standard fulfillment', version: 1 }, steps: [{ id: 'step-1', step_name: 'fulfillment_request', status: 'unknown', attempt_number: 1, started_at: null, completed_at: null, error_message: 'Response unavailable', error_category: 'timeout_unknown', retryable: true, external_reference: null, input_summary: {}, output_summary: {} }] }

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(getOrders).mockResolvedValue([order])
  vi.mocked(getExecutions).mockResolvedValue([])
  vi.mocked(createOrder).mockResolvedValue(order)
  vi.mocked(processOrder).mockResolvedValue(execution)
})

describe('Order workspace', () => {
  it('submits multiple items using strings for prices', async () => {
    const user = userEvent.setup()
    render(<Orders tenant="tenant-1" />)
    await screen.findByText('WEB-1')
    await user.type(screen.getByLabelText('External order ID'), 'WEB-2')
    await user.type(screen.getByLabelText('SKU 1'), 'A')
    await user.type(screen.getByLabelText('Unit price 1'), '12.50')
    await user.click(screen.getByRole('button', { name: 'Add item' }))
    await user.type(screen.getByLabelText('SKU 2'), 'B')
    await user.click(screen.getByRole('button', { name: 'Save order' }))
    await waitFor(() => expect(createOrder).toHaveBeenCalledWith('tenant-1', { external_order_id: 'WEB-2', items: [{ sku: 'A', quantity: 1, unit_price: '12.5' }, { sku: 'B', quantity: 1, unit_price: null }] }))
  })
  it('shows errors from order submission', async () => {
    vi.mocked(createOrder).mockRejectedValue(new Error('External order ID already exists with different items.'))
    const user = userEvent.setup()
    render(<Orders tenant="tenant-1" />)
    await user.type(screen.getByLabelText('External order ID'), 'WEB-1')
    await user.type(screen.getByLabelText('SKU 1'), 'A')
    await user.click(screen.getByRole('button', { name: 'Save order' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('different items')
  })
  it('displays items and actual workflow status', async () => {
    vi.mocked(getExecutions).mockResolvedValue([execution])
    const user = userEvent.setup()
    render(<Orders tenant="tenant-1" />)
    await user.click(await screen.findByRole('button', { name: 'View WEB-1' }))
    expect(await screen.findByText('needs attention')).toBeInTheDocument()
    expect(screen.getByText(/A: 2 units/)).toBeInTheDocument()
    expect(screen.getByText(/Outcome is uncertain/)).toBeInTheDocument()
  })
  it('runs processing and refreshes order history', async () => {
    const user = userEvent.setup()
    render(<Orders tenant="tenant-1" />)
    await user.click(await screen.findByRole('button', { name: 'Process WEB-1' }))
    await waitFor(() => expect(processOrder).toHaveBeenCalledWith('tenant-1', 'order-1'))
    await waitFor(() => expect(getExecutions).toHaveBeenCalled())
  })
  it('displays loading, empty and API error states', async () => {
    vi.mocked(getOrders).mockResolvedValue([])
    const user = userEvent.setup()
    render(<Orders tenant="tenant-1" />)
    expect(screen.getByText('Loading orders...')).toBeInTheDocument()
    expect(await screen.findByText('No orders for this retailer.')).toBeInTheDocument()
    vi.mocked(getOrders).mockRejectedValue(new Error('Database unavailable'))
    await user.click(screen.getByRole('button', { name: 'Refresh orders' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable')
  })
  it('selects a retailer before loading its orders', async () => {
    vi.mocked(getTenants).mockResolvedValue([{ id: 'tenant-1', name: 'Retailer A', slug: 'a', is_active: true, created_at: '' }])
    const user = userEvent.setup()
    render(<OrderDashboard />)
    expect(await screen.findByRole('option', { name: 'Retailer A' })).toBeInTheDocument()
    expect(getOrders).not.toHaveBeenCalled()
    await user.selectOptions(screen.getByLabelText('Retailer for orders'), 'tenant-1')
    expect(await screen.findByText('WEB-1')).toBeInTheDocument()
  })
  it('does not describe accepted fulfillment as delivery', () => {
    render(<ExecutionDetails execution={{ ...execution, status: 'completed', steps: [] }} />)
    expect(screen.getByText(/Delivery is outside this workflow/)).toBeInTheDocument()
  })
})
