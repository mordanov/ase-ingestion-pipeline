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
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw Object.assign(new Error(err.detail ?? 'API error'), { status: resp.status, data: err })
  }
  if (resp.status === 204) return undefined as T
  return resp.json() as Promise<T>
}

export interface DisabledDevice {
  device_id: string
  device_type: string
  disabled_at: string
}

export const listDisabledDevices = (): Promise<DisabledDevice[]> =>
  apiFetch('/api/v1/rules/disabled-devices')

export const addDisabledDevice = (device_id: string): Promise<DisabledDevice> =>
  apiFetch('/api/v1/rules/disabled-devices', {
    method: 'POST',
    body: JSON.stringify({ device_id }),
  })

export const removeDisabledDevice = (device_id: string): Promise<void> =>
  apiFetch(`/api/v1/rules/disabled-devices/${encodeURIComponent(device_id)}`, { method: 'DELETE' })
