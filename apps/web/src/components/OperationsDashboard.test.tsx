import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import OperationsDashboard, { RecoveryPanel } from './OperationsDashboard'
import { getAudit, getOperations, getSummary, recoverExecution } from '../api/operations'
import { getIntegrations } from '../api/integrations'
import { getOrders } from '../api/orders'
import { getApprovals, getExecution } from '../api/workflows'
import type { Execution } from '../types/order'

vi.mock('../api/operations', () => ({ getAudit: vi.fn(), getOperations: vi.fn(), getSummary: vi.fn(), recoverExecution: vi.fn() }))
vi.mock('../api/integrations', () => ({ getIntegrations: vi.fn() }))
vi.mock('../api/orders', () => ({ getOrders: vi.fn() }))
vi.mock('../api/workflows', () => ({ getApprovals: vi.fn(), getExecution: vi.fn(), decideApproval: vi.fn() }))
const execution: Execution = { id: 'ex-1', tenant_id: 't', order_id: 'o', status: 'failed', started_at: '2026-10-21T12:00:00Z', completed_at: '2026-10-21T12:00:02Z', error_message: 'Provider returned HTTP 503.', error_category: 'provider_unavailable', definition_snapshot: { name: 'Standard', version: 1 }, steps: [{ id: 's-1', step_name: 'fulfillment_request', status: 'failed', attempt_number: 1, started_at: null, completed_at: null, error_message: 'Provider returned HTTP 503.', error_category: 'provider_unavailable', retryable: true, external_reference: null, input_summary: { idempotency_key: 'stable-key' }, output_summary: {} }] }
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(getOperations).mockResolvedValue([{ id: 'ex-1', order_id: 'o', tenant_id: 't', external_order_id: 'FAILED-1', status: 'failed', source: { source: 'Shop source' }, workflow_name: 'Standard', workflow_version: 1, started_at: '2026-10-21T12:00:00Z', completed_at: null, error_category: 'provider_unavailable', error_message: 'Provider returned HTTP 503.' }])
  vi.mocked(getSummary).mockResolvedValue({ orders: { needs_attention: 1 }, executions: { failed: 1 }, pending_approvals: 0, import_failures: 0, retry_requests: 0, average_completed_duration_seconds: null })
  vi.mocked(getAudit).mockResolvedValue([])
  vi.mocked(getIntegrations).mockResolvedValue([])
  vi.mocked(getOrders).mockResolvedValue([])
  vi.mocked(getApprovals).mockResolvedValue([])
  vi.mocked(getExecution).mockResolvedValue(execution)
  vi.mocked(recoverExecution).mockResolvedValue({ ...execution, status: 'completed' })
})
it('loads actual summaries and applies execution filters', async () => {
  const user = userEvent.setup()
  render(<OperationsDashboard tenant="t" />)
  expect(await screen.findByText('FAILED-1')).toBeInTheDocument()
  expect(screen.getByText('No completed runs')).toBeInTheDocument()
  await user.selectOptions(screen.getByLabelText('Execution status'), 'failed')
  await user.selectOptions(screen.getByLabelText('Error category'), 'provider_unavailable')
  await user.click(screen.getByRole('button', { name: 'Apply operations filters' }))
  await waitFor(() => expect(getOperations).toHaveBeenLastCalledWith('t', expect.stringContaining('status=failed'), expect.any(AbortSignal)))
  expect(vi.mocked(getOperations).mock.calls.at(-1)?.[1]).toContain('error_category=provider_unavailable')
})
it('shows execution details and recovery history', async () => {
  vi.mocked(getAudit).mockResolvedValue([{ id: 'audit-1', action: 'investigated', previous_state: { status: 'failed' }, new_state: { status: 'failed' }, note: 'Provider checked locally', development_operator: 'Demo operator', created_at: '2026-10-21T12:00:00Z' }])
  const user = userEvent.setup()
  render(<OperationsDashboard tenant="t" />)
  await user.click(await screen.findByRole('button', { name: 'Inspect FAILED-1' }))
  expect(await screen.findByText('Failure recovery and investigation')).toBeInTheDocument()
  expect(screen.getByText(/Provider checked locally/)).toBeInTheDocument()
  expect(screen.getByText('Eligible for controlled retry after reconciliation.')).toBeInTheDocument()
})
it('displays empty and failed query states', async () => {
  vi.mocked(getOperations).mockResolvedValue([])
  const user = userEvent.setup()
  render(<OperationsDashboard tenant="t" />)
  expect(await screen.findByText('No executions match these filters.')).toBeInTheDocument()
  vi.mocked(getOperations).mockRejectedValue(new Error('Database unavailable'))
  await user.click(screen.getByRole('button', { name: 'Refresh operations' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Database unavailable')
})
it('requires a note before recording a recovery action', async () => {
  const user = userEvent.setup()
  render(<RecoveryPanel tenant="t" execution={execution} onChanged={vi.fn()} />)
  await user.click(screen.getByRole('button', { name: 'Retry eligible step' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('resolution note')
  expect(recoverExecution).not.toHaveBeenCalled()
})
it('sends an idempotent recovery request and reports its result', async () => {
  const user = userEvent.setup()
  const onChanged = vi.fn()
  render(<RecoveryPanel tenant="t" execution={execution} onChanged={onChanged} />)
  await user.type(screen.getByLabelText('Resolution note'), 'Provider available again')
  await user.click(screen.getByRole('button', { name: 'Retry eligible step' }))
  await waitFor(() => expect(recoverExecution).toHaveBeenCalledWith('t', 'ex-1', expect.objectContaining({ action: 'retry', note: 'Provider available again', request_key: expect.any(String) })))
  expect(await screen.findByRole('status')).toHaveTextContent('Execution is completed')
  expect(onChanged).toHaveBeenCalledOnce()
})
it('does not offer retry for nonretryable or exhausted failures', () => {
  render(<RecoveryPanel tenant="t" execution={{ ...execution, steps: [{ ...execution.steps[0], attempt_number: 3 }] }} onChanged={vi.fn()} />)
  expect(screen.getByRole('button', { name: 'Retry eligible step' })).toBeDisabled()
  expect(screen.getByRole('button', { name: 'Record investigation' })).toBeEnabled()
})
it('reuses the recovery key after a lost response', async () => {
  vi.mocked(recoverExecution).mockRejectedValueOnce(new Error('Response lost')).mockResolvedValueOnce({ ...execution, status: 'completed' })
  const user = userEvent.setup()
  render(<RecoveryPanel tenant="t" execution={execution} onChanged={vi.fn()} />)
  await user.type(screen.getByLabelText('Resolution note'), 'Provider available again')
  await user.click(screen.getByRole('button', { name: 'Retry eligible step' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Response lost')
  await user.click(screen.getByRole('button', { name: 'Retry eligible step' }))
  await screen.findByRole('status')
  expect(vi.mocked(recoverExecution).mock.calls[0][2]).toEqual(vi.mocked(recoverExecution).mock.calls[1][2])
})
