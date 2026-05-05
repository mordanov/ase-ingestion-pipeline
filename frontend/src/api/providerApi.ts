import { getApiKey, UnauthorizedError } from './creditApi'

const headers = () => ({
  'Content-Type': 'application/json',
  'X-API-Key': getApiKey(),
})

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, { ...init, headers: { ...headers(), ...init?.headers } })
  if (resp.status === 401) {
    window.dispatchEvent(new Event('api:unauthorized'))
    throw new UnauthorizedError()
  }
  if (resp.status === 204) return undefined as T
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw Object.assign(new Error(err.detail ?? 'API error'), { status: resp.status, data: err })
  }
  return resp.json() as Promise<T>
}

// ── Types ─────────────────────────────────────────────────────────────────────

/**
 * Field value expressions used in request_mapping.fields:
 *   $HEIGHT      — patient height in cm
 *   $HEIGHT_FT   — patient height in feet
 *   $WEIGHT      — patient weight in kg
 *   $WEIGHT_LBS  — patient weight in lbs
 *   $UUID        — random UUID generated per request
 *   $BIRTHDATE   — current Unix timestamp (seconds since epoch)
 *   $CONST:value — literal value (e.g. "$CONST:my-api-key", "$CONST:42")
 */
export interface RequestMapping {
  fields: Record<string, string>
}

export interface ResponseMapping {
  array_path: string
  text_field: string
  score_field: string
  score_multiplier: number
  detail_field: string
}

export interface ProviderSchema {
  id: string
  name: string
  endpoint_url: string
  openapi_url: string | null
  request_mapping: RequestMapping
  response_mapping: ResponseMapping
  is_active: boolean
  created_at: string
  updated_at: string
}

export interface CreateProviderSchemaRequest {
  name: string
  endpoint_url: string
  request_mapping: RequestMapping
  response_mapping: ResponseMapping
  is_active: boolean
}

// ── CRUD ──────────────────────────────────────────────────────────────────────

export const listProviderSchemas = () => apiFetch<ProviderSchema[]>('/api/v1/provider-schemas')

export const createProviderSchema = (data: CreateProviderSchemaRequest) =>
  apiFetch<ProviderSchema>('/api/v1/provider-schemas', {
    method: 'POST',
    body: JSON.stringify(data),
  })

export const updateProviderSchema = (id: string, data: Partial<CreateProviderSchemaRequest>) =>
  apiFetch<ProviderSchema>(`/api/v1/provider-schemas/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })

export const deleteProviderSchema = (id: string) =>
  apiFetch<void>(`/api/v1/provider-schemas/${id}`, { method: 'DELETE' })
