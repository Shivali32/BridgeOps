
import { useEffect, useState } from 'react'

import { getTenants } from '../api/tenants'
import type { Tenant } from '../types/tenant'

function TenantList() {
  const [tenants, setTenants] = useState<Tenant[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshKey, setRefreshKey] = useState(0)

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
              : 'An unexpected error occurred'
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

  return (
    <section className="tenant-section">
      <div className="section-header">
        <div>
          <h2>Registered Retailers</h2>
          <p>Businesses using the BridgOps platform.</p>
        </div>

        <button
          type="button"
          onClick={() => setRefreshKey((value) => value + 1)}
          disabled={loading}
        >
          Refresh
        </button>
      </div>

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
