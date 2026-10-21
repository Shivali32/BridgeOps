export interface OrderItemInput { sku: string; quantity: number; unit_price?: string | null }
export interface OrderInput { external_order_id: string; items: OrderItemInput[] }
export interface Order extends OrderInput {
  id: string; tenant_id: string; status: string; created_at: string; updated_at: string
}
export interface Step {
  id: string; step_name: string; status: string; attempt_number: number
  started_at: string | null; completed_at: string | null; error_message: string | null
  error_category: string | null; retryable: boolean; external_reference: string | null
  input_summary: Record<string, unknown>; output_summary: Record<string, unknown>
}
export interface Execution {
  id: string; tenant_id: string; order_id: string; status: string
  started_at: string | null; completed_at: string | null; error_message: string | null
  error_category: string | null; definition_snapshot: Record<string, unknown>; steps: Step[]
}
