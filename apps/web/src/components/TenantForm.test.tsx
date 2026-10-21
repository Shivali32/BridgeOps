
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import TenantForm from './TenantForm'
import { createTenant, updateTenant } from '../api/tenants'
import type { Tenant } from '../types/tenant'

vi.mock('../api/tenants', () => ({
  createTenant: vi.fn(),
  updateTenant: vi.fn(),
}))

describe('TenantForm', () => {
  const onSuccess = vi.fn()
  const onCancel = vi.fn()

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the create retailer form', () => {
    render(
      <TenantForm
        onSuccess={onSuccess}
        onCancel={onCancel}
      />
    )

    expect(screen.getByText('Add Retailer')).toBeInTheDocument()
    expect(screen.getByLabelText('Business Name')).toBeInTheDocument()
    expect(screen.getByLabelText('Business Slug')).toBeInTheDocument()
  })

  it('creates a retailer with valid input', async () => {
    const user = userEvent.setup()

    vi.mocked(createTenant).mockResolvedValue({} as Tenant)

    render(
      <TenantForm
        onSuccess={onSuccess}
        onCancel={onCancel}
      />
    )

    await user.type(
      screen.getByLabelText('Business Name'),
      'Retailer C'
    )

    await user.type(
      screen.getByLabelText('Business Slug'),
      'retailer-c'
    )

    await user.click(
      screen.getByRole('button', { name: 'Save Retailer' })
    )

    await waitFor(() => {
      expect(createTenant).toHaveBeenCalledWith({
        name: 'Retailer C',
        slug: 'retailer-c',
      })
    })

    expect(onSuccess).toHaveBeenCalledOnce()
  })

  it('displays an API error', async () => {
    const user = userEvent.setup()

    vi.mocked(createTenant).mockRejectedValue(
      new Error('A retailer with this slug already exists.')
    )

    render(
      <TenantForm
        onSuccess={onSuccess}
        onCancel={onCancel}
      />
    )

    await user.type(
      screen.getByLabelText('Business Name'),
      'Retailer C'
    )

    await user.type(
      screen.getByLabelText('Business Slug'),
      'retailer-c'
    )

    await user.click(
      screen.getByRole('button', { name: 'Save Retailer' })
    )

    expect(
      await screen.findByRole('alert')
    ).toHaveTextContent('already exists')

    expect(onSuccess).not.toHaveBeenCalled()
  })

  it('updates the name of an existing retailer', async () => {
    const user = userEvent.setup()

    const tenant: Tenant = {
      id: 'tenant-123',
      name: 'Retailer A',
      slug: 'retailer-a',
      is_active: true,
      created_at: '2026-10-20T12:00:00Z',
    }

    vi.mocked(updateTenant).mockResolvedValue(tenant)

    render(
      <TenantForm
        tenant={tenant}
        onSuccess={onSuccess}
        onCancel={onCancel}
      />
    )

    const nameInput = screen.getByLabelText('Business Name')

    await user.clear(nameInput)
    await user.type(nameInput, 'Retailer A Group')

    await user.click(
      screen.getByRole('button', { name: 'Save Retailer' })
    )

    await waitFor(() => {
      expect(updateTenant).toHaveBeenCalledWith(
        'tenant-123',
        { name: 'Retailer A Group' }
      )
    })

    expect(onSuccess).toHaveBeenCalledOnce()
  })
})
