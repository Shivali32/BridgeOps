
export interface Tenant {
  id: string
  name: string
  slug: string
  is_active: boolean
  created_at: string
}

export interface TenantCreate {
  name: string
  slug: string
}

export interface TenantUpdate {
  name: string
}
