
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import TenantList from './TenantList'
import {
  getTenants,
  deactivateTenant,
} from '../api/tenants'

import type { Tenant } from '../types/tenant'

vi.mock('../api/tenants', () => ({
  getTenants: vi.fn(),
  createTenant: vi.fn(),
  updateTenant: vi.fn(),
  deactivateTenant: vi.fn(),
}))

const tenant: Tenant = {
  id: 'tenant-123',
  name: 'Retailer A',
  slug: 'retailer-a',
  is_active: true,
  created_at: '2026-10-20T12:00:00Z',
}

describe('TenantList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('displays retailers returned by the API', async () => {
    vi.mocked(getTenants).mockResolvedValue([tenant])

    render(<TenantList />)

    expect(
      screen.getByText('Loading retailers...')
    ).toBeInTheDocument()

    expect(
      await screen.findByText('Retailer A')
    ).toBeInTheDocument()

    expect(screen.getByText('retailer-a')).toBeInTheDocument()
  })

  it('displays an API error', async () => {
    vi.mocked(getTenants).mockRejectedValue(
      new Error('Unable to load tenants')
    )

    render(<TenantList />)

    expect(
      await screen.findByRole('alert')
    ).toHaveTextContent('Unable to load tenants')
  })

  it('deactivates a retailer after confirmation', async () => {
    const user = userEvent.setup()

    vi.mocked(getTenants).mockResolvedValue([tenant])
    vi.mocked(deactivateTenant).mockResolvedValue(undefined)

    const confirmSpy = vi.spyOn(window, 'confirm')
      .mockReturnValue(true)

    render(<TenantList />)

    await screen.findByText('Retailer A')

    await user.click(
      screen.getByRole('button', { name: 'Deactivate' })
    )

    await waitFor(() => {
      expect(deactivateTenant).toHaveBeenCalledWith('tenant-123')
    })

    expect(confirmSpy).toHaveBeenCalled()
  })
})
