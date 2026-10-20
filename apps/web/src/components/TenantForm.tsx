
import { useState } from 'react'
import type { FormEvent } from 'react'

import { createTenant, updateTenant } from '../api/tenants'
import type { Tenant } from '../types/tenant'

interface TenantFormProps {
  tenant?: Tenant
  onSuccess: () => void
  onCancel: () => void
}

function TenantForm({
  tenant,
  onSuccess,
  onCancel,
}: TenantFormProps) {
  const [name, setName] = useState(tenant?.name ?? '')
  const [slug, setSlug] = useState(tenant?.slug ?? '')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isEditing = Boolean(tenant)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()

    if (saving) return

    const cleanName = name.trim()
    const cleanSlug = slug.trim()

    if (!cleanName) {
      setError('Business name is required.')
      return
    }

    if (!isEditing &&
        !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(cleanSlug)) {
      setError('Use lowercase letters, numbers, and single hyphens.')
      return
    }

    setSaving(true)
    setError(null)

    try {
      if (tenant) {
        await updateTenant(tenant.id, { name: cleanName })
      } else {
        await createTenant({
          name: cleanName,
          slug: cleanSlug,
        })
      }

      onSuccess()
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Unable to save retailer.'
      )
    } finally {
      setSaving(false)
    }
  }

  return (
    <form className="tenant-form" onSubmit={handleSubmit}>
      <h3>{isEditing ? 'Edit Retailer' : 'Add Retailer'}</h3>

      <div className="form-field">
        <label htmlFor="tenant-name">Business Name</label>
        <input
          id="tenant-name"
          type="text"
          value={name}
          onChange={(event) => setName(event.target.value)}
          maxLength={150}
          required
          disabled={saving}
          placeholder="Retailer A"
        />
      </div>

      <div className="form-field">
        <label htmlFor="tenant-slug">Business Slug</label>
        <input
          id="tenant-slug"
          type="text"
          value={slug}
          onChange={(event) => setSlug(event.target.value)}
          maxLength={100}
          required
          disabled={saving || isEditing}
          placeholder="retailer-a"
        />

        {isEditing && (
          <small>Slugs cannot be changed after creation.</small>
        )}
      </div>

      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}

      <div className="form-actions">
        <button
          type="button"
          className="button-secondary"
          onClick={onCancel}
          disabled={saving}
        >
          Cancel
        </button>

        <button type="submit" disabled={saving}>
          {saving ? 'Saving...' : 'Save Retailer'}
        </button>
      </div>
    </form>
  )
}

export default TenantForm
