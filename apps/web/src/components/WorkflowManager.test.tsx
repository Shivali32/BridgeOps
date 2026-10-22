import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import WorkflowManager, { ApprovalPanel } from './WorkflowManager'
import { decideApproval, getApprovals, getDefinitions, getExecution, getVersions, saveDefinition } from '../api/workflows'
import { getIntegrations, saveIntegration } from '../api/integrations'
import type { Definition } from '../api/workflows'
import type { Execution } from '../types/order'

vi.mock('../api/workflows', () => ({ decideApproval: vi.fn(), getApprovals: vi.fn(), getDefinitions: vi.fn(), getExecution: vi.fn(), getVersions: vi.fn(), saveDefinition: vi.fn() }))
vi.mock('../api/integrations', () => ({ getIntegrations: vi.fn(), saveIntegration: vi.fn() }))
const definition: Definition = { id: 'wf-1', tenant_id: 't', name: 'Standard', enabled: true, is_default: true, version: 1, configuration: { name: 'Standard', trigger: 'order_processing', steps: [] } }
const execution: Execution = { id: 'ex-1', tenant_id: 't', order_id: 'o', status: 'completed', started_at: null, completed_at: null, error_message: null, error_category: null, definition_snapshot: { name: 'Standard', version: 1 }, steps: [] }
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(getDefinitions).mockResolvedValue([definition])
  vi.mocked(getApprovals).mockResolvedValue([])
  vi.mocked(getIntegrations).mockResolvedValue([])
  vi.mocked(saveDefinition).mockResolvedValue(definition)
  vi.mocked(getExecution).mockResolvedValue(execution)
  vi.mocked(decideApproval).mockResolvedValue(execution)
  vi.mocked(getVersions).mockResolvedValue([{ version: 1, snapshot: {}, created_at: '' }])
})
it('creates a workflow from an approval threshold preset', async () => {
  const user = userEvent.setup()
  render(<WorkflowManager tenant="t" />)
  await user.type(screen.getByLabelText('Workflow name'), 'High value')
  await user.click(screen.getByRole('button', { name: 'Use approval steps' }))
  await user.click(screen.getByRole('button', { name: 'Save workflow' }))
  await waitFor(() => expect(saveDefinition).toHaveBeenCalledWith('t', expect.objectContaining({ name: 'High value', trigger: 'order_processing', steps: expect.arrayContaining([expect.objectContaining({ type: 'approval' })]) }), undefined))
})
it('keeps invalid configuration visible after a server error', async () => {
  vi.mocked(saveDefinition).mockRejectedValue(new Error('Include one check, reservation and fulfillment in that order'))
  const user = userEvent.setup()
  render(<WorkflowManager tenant="t" />)
  await user.type(screen.getByLabelText('Workflow name'), 'Bad workflow')
  await user.click(screen.getByRole('button', { name: 'Save workflow' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('Include one check')
})
it('views immutable workflow versions', async () => {
  const user = userEvent.setup()
  render(<WorkflowManager tenant="t" />)
  await user.click(await screen.findByRole('button', { name: 'Versions of Standard' }))
  await waitFor(() => expect(getVersions).toHaveBeenCalledWith('t', 'wf-1'))
  expect(await screen.findByText('Workflow versions')).toBeInTheDocument()
})
it('approves a pending request with development attribution', async () => {
  vi.mocked(getApprovals).mockResolvedValue([{ id: 'a-1', tenant_id: 't', execution_id: 'ex-1', step_name: 'approve', reason: 'High value order', status: 'pending', decision_note: null, development_operator: null, created_at: '2026-10-21T12:00:00Z', decided_at: null }])
  const user = userEvent.setup()
  render(<ApprovalPanel tenant="t" />)
  await user.type(screen.getByLabelText('Decision note'), 'Checked order')
  await user.click(await screen.findByRole('button', { name: 'Approve a-1' }))
  await waitFor(() => expect(decideApproval).toHaveBeenCalledWith('t', 'a-1', 'approve', 'Checked order', 'Local demo operator (unverified)'))
  expect(await screen.findByText(/Fulfillment request accepted/)).toBeInTheDocument()
})
it('shows a conflicting approval decision error', async () => {
  vi.mocked(getApprovals).mockResolvedValue([{ id: 'a-1', tenant_id: 't', execution_id: 'ex-1', step_name: 'approve', reason: 'High value order', status: 'pending', decision_note: null, development_operator: null, created_at: '', decided_at: null }])
  vi.mocked(decideApproval).mockRejectedValue(new Error('This approval already has a different decision.'))
  const user = userEvent.setup()
  render(<ApprovalPanel tenant="t" />)
  await user.click(await screen.findByRole('button', { name: 'Reject a-1' }))
  expect(await screen.findByRole('alert')).toHaveTextContent('different decision')
})
it('associates a workflow with the selected integration using its current version', async () => {
  vi.mocked(getIntegrations).mockResolvedValue([{ id: 'i-1', tenant_id: 't', name: 'CSV source', connector_type: 'csv', enabled: true, version: 2, mapping: { external_id: 'order_reference', items: 'rows', sku: 'sku', quantity: 'qty', unit_price: null, price_in_cents: false, default_quantity: null, default_price: null }, created_at: '' }])
  const user = userEvent.setup()
  render(<WorkflowManager tenant="t" />)
  await screen.findByRole('option', { name: 'CSV source (version 2)' })
  await user.selectOptions(screen.getByLabelText('Source integration'), 'i-1')
  await user.selectOptions(screen.getByLabelText('Assigned workflow'), 'wf-1')
  await user.click(screen.getByRole('button', { name: 'Save workflow assignment' }))
  await waitFor(() => expect(saveIntegration).toHaveBeenCalledWith('t', expect.objectContaining({ workflow_id: 'wf-1', expected_version: 2 }), 'i-1'))
})
