import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import IntegrationManager, { ImportPanel } from './IntegrationManager'
import { getConnectors, getIntegrations, getImports, importCsv, importPayload, saveIntegration } from '../api/integrations'
import type { Integration, ImportResult } from '../api/integrations'

vi.mock('../api/integrations', () => ({ getConnectors: vi.fn(), getIntegrations: vi.fn(), getImports: vi.fn(), importCsv: vi.fn(), importPayload: vi.fn(), saveIntegration: vi.fn() }))
const mapping = { external_id: 'reference', items: 'products', sku: 'product_code', quantity: 'count', unit_price: 'price_cents', price_in_cents: true, default_quantity: null, default_price: null }
const integration: Integration = { id: 'int-1', tenant_id: 'tenant-1', name: 'Retail source', connector_type: 'custom_rest', enabled: true, version: 1, mapping, created_at: '' }
const result: ImportResult = { id: 'import-1', integration_id: 'int-1', order_id: 'order-1', source_reference: 'REST-1', status: 'succeeded', duplicate: false, row_numbers: [], error_message: null, created_at: '' }
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(getConnectors).mockResolvedValue([{ type: 'custom_rest', default_mapping: mapping }, { type: 'csv', default_mapping: { ...mapping, items: 'rows' } }])
  vi.mocked(getIntegrations).mockResolvedValue([integration])
  vi.mocked(getImports).mockResolvedValue([])
  vi.mocked(saveIntegration).mockResolvedValue(integration)
  vi.mocked(importPayload).mockResolvedValue(result)
  vi.mocked(importCsv).mockResolvedValue([result])
})

describe('Tenant integrations', () => {
  it('saves a configuration with a controlled mapping', async () => {
    const user = userEvent.setup()
    render(<IntegrationManager tenant="tenant-1" />)
    await user.type(await screen.findByLabelText('Integration name'), 'New source')
    await user.click(screen.getByRole('button', { name: 'Save integration' }))
    await waitFor(() => expect(saveIntegration).toHaveBeenCalledWith('tenant-1', { name: 'New source', connector_type: 'custom_rest', enabled: true, mapping }, undefined))
  })
  it('edits enabled state with the expected version', async () => {
    const user = userEvent.setup()
    render(<IntegrationManager tenant="tenant-1" />)
    await user.click(await screen.findByRole('button', { name: 'Edit Retail source' }))
    await user.click(screen.getByLabelText('Integration enabled'))
    await user.click(screen.getByRole('button', { name: 'Save integration' }))
    await waitFor(() => expect(saveIntegration).toHaveBeenCalledWith('tenant-1', expect.objectContaining({ enabled: false, expected_version: 1 }), 'int-1'))
  })
  it('shows server validation errors while preserving the editor', async () => {
    vi.mocked(saveIntegration).mockRejectedValue(new Error('Configuration changed. Refresh before saving.'))
    const user = userEvent.setup()
    render(<IntegrationManager tenant="tenant-1" />)
    await user.type(await screen.findByLabelText('Integration name'), 'New source')
    await user.click(screen.getByRole('button', { name: 'Save integration' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Configuration changed')
    expect(screen.getByLabelText('Integration name')).toHaveValue('New source')
  })
  it('submits provider JSON with the development token and shows results', async () => {
    const user = userEvent.setup()
    const onImported = vi.fn()
    render(<ImportPanel tenant="tenant-1" integration={integration} onImported={onImported} />)
    await user.type(screen.getByLabelText('Development ingestion token'), 'token')
    await user.click(screen.getByRole('button', { name: 'Import orders' }))
    await waitFor(() => expect(importPayload).toHaveBeenCalledWith('tenant-1', 'int-1', { reference: 'REST-1', products: [{ product_code: 'A', count: 2, price_cents: 1250 }] }, 'token'))
    expect(await screen.findByText('succeeded')).toBeInTheDocument()
    expect(onImported).toHaveBeenCalledOnce()
  })
  it('uploads CSV and surfaces a failed row', async () => {
    const user = userEvent.setup()
    const csv = 'order_reference,product_code,qty\nCSV-1,A,0'
    const file = new File([csv], 'orders.csv', { type: 'text/csv' })
    Object.defineProperty(file, 'text', { value: () => Promise.resolve(csv) })
    vi.mocked(importCsv).mockResolvedValue([{ ...result, status: 'failed', error_message: 'quantity must be positive', row_numbers: [2] }])
    render(<ImportPanel tenant="tenant-1" integration={{ ...integration, connector_type: 'csv' }} onImported={vi.fn()} />)
    await user.upload(screen.getByLabelText('Upload CSV'), file)
    await waitFor(() => expect(screen.getByLabelText('CSV content')).toHaveValue(csv))
    await user.type(screen.getByLabelText('Development ingestion token'), 'token')
    await user.click(screen.getByRole('button', { name: 'Import orders' }))
    await waitFor(() => expect(importCsv).toHaveBeenCalledWith('tenant-1', 'int-1', csv, 'token'))
    expect(await screen.findByRole('alert')).toHaveTextContent('quantity must be positive')
  })
  it('prevents importing through a disabled integration', () => {
    render(<ImportPanel tenant="tenant-1" integration={{ ...integration, enabled: false }} onImported={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'Import orders' })).toBeDisabled()
  })
})
