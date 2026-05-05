export const getApiKey = () => sessionStorage.getItem('apiKey') ?? ''

const headers = () => ({
  'Content-Type': 'application/json',
  'X-API-Key': getApiKey(),
})

export class UnauthorizedError extends Error {
  status = 401
  constructor() {
    super('Invalid API key — please update it and try again.')
  }
}

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, { ...init, headers: { ...headers(), ...init?.headers } })
  if (resp.status === 401) {
    window.dispatchEvent(new Event('api:unauthorized'))
    throw new UnauthorizedError()
  }
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw Object.assign(new Error(err.detail ?? 'API error'), { status: resp.status, data: err })
  }
  return resp.json() as Promise<T>
}

export interface CreditConfig {
  version: number
  is_active: boolean
  default_initial_balance: number
  activity_earning_rules: Record<string, number>
  service_costs: Record<string, number>
  streak_bonus_7d: number
  streak_bonus_30d: number
  tier_thresholds: Record<string, number>
  tier_multipliers: Record<string, number>
  tier_discounts: Record<string, number>
  created_by: string
}

export interface DeviceCredits {
  device_id: string
  credit_balance: number
  reward_tier: string
  streak_days: number
  cumulative_credits_earned: number
  cumulative_credits_spent: number
  next_tier: string | null
  credits_to_next_tier: number | null
  tier_multiplier: number
  tier_discount: number
}

export interface TransactionItem {
  id: string
  amount: number
  action_type: string
  reason: string
  resulting_balance: number
  created_at: string
  event_id: string | null
}

export interface TransactionHistory {
  total: number
  items: TransactionItem[]
}

export const getCreditConfig = () => apiFetch<CreditConfig>('/api/v1/credit-config')

export const updateCreditConfig = (data: Partial<CreditConfig>) =>
  apiFetch<CreditConfig>('/api/v1/credit-config', {
    method: 'PUT',
    body: JSON.stringify(data),
  })

export const getDeviceCredits = (deviceId: string) =>
  apiFetch<DeviceCredits>(`/api/v1/devices/${deviceId}/credits`)

export const getDeviceTransactions = (
  deviceId: string,
  params: { limit?: number; offset?: number; action_type?: string } = {},
) => {
  const qs = new URLSearchParams()
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.offset) qs.set('offset', String(params.offset))
  if (params.action_type) qs.set('action_type', params.action_type)
  return apiFetch<TransactionHistory>(`/api/v1/devices/${deviceId}/credits/transactions?${qs}`)
}

export const topUpCredits = (deviceId: string, amount: number, reason: string) =>
  apiFetch(`/api/v1/devices/${deviceId}/credits`, {
    method: 'POST',
    body: JSON.stringify({ amount, reason }),
  })

export interface DeviceListItem {
  device_id: string
  credit_balance: number
  reward_tier: string
  streak_days: number
  cumulative_credits_earned: number
  cumulative_credits_spent: number
}

export interface DeviceListResponse {
  total: number
  items: DeviceListItem[]
}

export const listDevices = (params: { search?: string; limit?: number; offset?: number } = {}) => {
  const qs = new URLSearchParams()
  if (params.search) qs.set('search', params.search)
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.offset) qs.set('offset', String(params.offset))
  const q = qs.toString()
  return apiFetch<DeviceListResponse>(`/api/v1/devices${q ? `?${q}` : ''}`)
}

export const adjustCredits = (deviceId: string, delta: number) =>
  apiFetch(`/api/v1/devices/${deviceId}/credits`, {
    method: 'POST',
    body: JSON.stringify({ amount: delta, reason: 'manual adjustment' }),
  })

export interface MeasurementEvent {
  event_id: string
  event_timestamp: string
  received_at: string
  scenario: string | null
  heart_rate_bpm: number | null
  spo2_pct: number | null
  validation_status: string
  is_anomaly: boolean
  source_protocol: string
}

export interface MeasurementHistory {
  total: number
  items: MeasurementEvent[]
}

export const getDeviceEvents = (
  deviceId: string,
  params: { limit?: number; offset?: number } = {},
) => {
  const qs = new URLSearchParams()
  if (params.limit) qs.set('limit', String(params.limit))
  if (params.offset) qs.set('offset', String(params.offset))
  return apiFetch<MeasurementHistory>(`/api/v1/devices/${deviceId}/events?${qs}`)
}
