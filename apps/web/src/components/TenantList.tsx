
import { useEffect, useState } from 'react'

import {
  deactivateTenant,
  getTenants,
} from '../api/tenants'

import type { Tenant } from '../types/tenant'
import TenantForm from './TenantForm'

function TenantList() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [showForm, setShowForm] = useState(false)
  const [editingTenant, setEditingTenant] = useState<Tenant | null>(null)
  const [deactivatingId, setDeactivatingId] = useState<string | null>(null)

  useEffect(() => {
    const controller = new AbortController()

    async function loadTenants() {
      setLoading(true)
      setError(null)

      try {
        const data = await getTenants(controller.signal)

        if (!controller.signal.aborted) {
          setTenants(data)
        }
      } catch (err) {
        if (!controller.signal.aborted) {
          setError(
            err instanceof Error
              ? err.message
              : 'Unable to load retailers.'
          )
        }
      } finally {
        if (!controller.signal.aborted) {
          setLoading(false)
        }
      }
    }

    void loadTenants()

    return () => controller.abort()
  }, [refreshKey])

  function refreshTenants() {
    setRefreshKey((value) => value + 1)
  }

  function handleFormSuccess() {
    setShowForm(false)
    setEditingTenant(null)
    setActionError(null)
    refreshTenants()
  }

  function handleCancel() {
    setShowForm(false)
    setEditingTenant(null)
  }

  function handleEdit(tenant: Tenant) {
    setEditingTenant(tenant)
    setShowForm(true)
    setActionError(null)
  }

  async function handleDeactivate(tenant: Tenant) {
    const confirmed = window.confirm(
      `Are you sure you want to deactivate ${tenant.name}?`
    )

    if (!confirmed) return

    setDeactivatingId(tenant.id)
    setActionError(null)

    try {
      await deactivateTenant(tenant.id)
      refreshTenants()
    } catch (err) {
      setActionError(
        err instanceof Error
          ? err.message
          : 'Unable to deactivate retailer.'
      )
    } finally {
      setDeactivatingId(null)
    }
  }

  return (
    <section className="tenant-section">
      <div className="section-header">
        <div>
          <h2>Registered Retailers</h2>
          <p>Manage businesses using BridgOps.</p>
        </div>

        <div className="section-actions">
          <button
            type="button"
            className="button-secondary"
            onClick={refreshTenants}
            disabled={loading}
          >
            Refresh
          </button>

          <button
            type="button"
            onClick={() => {
              setEditingTenant(null)
              setShowForm(true)
              setActionError(null)
            }}
            disabled={showForm}
          >
            Add Retailer
          </button>
        </div>
      </div>

      {showForm && (
        <TenantForm
          key={editingTenant?.id ?? 'new'}
          tenant={editingTenant ?? undefined}
          onSuccess={handleFormSuccess}
          onCancel={handleCancel}
        />
      )}

      {actionError && (
        <p role="alert" className="error-message">
          {actionError}
        </p>
      )}

      {loading && <p>Loading retailers...</p>}

      {!loading && error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}

      {!loading && !error && tenants.length === 0 && (
        <p>No retailers registered yet.</p>
      )}

      {!loading && !error && tenants.length > 0 && (
        <div className="table-container">
          <table className="tenant-table">
            <thead>
              <tr>
                <th>Business Name</th>
                <th>Slug</th>
                <th>Status</th>
                <th>Created</th>
                <th>Actions</th>
              </tr>
            </thead>

            <tbody>
              {tenants.map((tenant) => (
                <tr key={tenant.id}>
                  <td>{tenant.name}</td>
                  <td>{tenant.slug}</td>
                  <td>
                    <span
                      className={
                        tenant.is_active
                          ? 'status-active'
                          : 'status-inactive'
                      }
                    >
                      {tenant.is_active ? 'Active' : 'Inactive'}
                    </span>
                  </td>
                  <td>
                    {new Date(
                      tenant.created_at
                    ).toLocaleDateString()}
                  </td>
                  <td>
                    <div className="table-actions">
                      <button
                        type="button"
                        className="button-secondary"
                        onClick={() => handleEdit(tenant)}
                        disabled={!tenant.is_active || showForm || deactivatingId !== null}
                      >
                        Edit
                      </button>

                      <button
                        type="button"
                        className="button-danger"
                        onClick={() => void handleDeactivate(tenant)}
                        disabled={!tenant.is_active || showForm || deactivatingId !== null}
                      >
                        {deactivatingId === tenant.id
                          ? 'Deactivating...'
                          : 'Deactivate'}
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}

export default TenantList
