import { getApiKey } from './creditApi'

const headers = () => ({
  'Content-Type': 'application/json',
  'X-API-Key': getApiKey(),
})

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(url, { ...init, headers: { ...headers(), ...init?.headers } })
  if (resp.status === 401) {
    window.dispatchEvent(new Event('api:unauthorized'))
    throw Object.assign(new Error('Invalid API key'), { status: 401 })
  }
  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }))
    throw Object.assign(new Error(err.detail ?? 'API error'), { status: resp.status, data: err })
  }
  return resp.json() as Promise<T>
}

// ── Training ──────────────────────────────────────────────────────────────────

export interface RetrainResponse {
  job_id: string
  status: string
  triggered_by: string
  started_at: string
}

export interface TrainingJobResponse {
  job_id: string
  status: 'running' | 'succeeded' | 'failed'
  triggered_by: string
  started_at: string
  ended_at: string | null
  reranker_ndcg_at_10: number | null
  anomaly_detector_f1: number | null
  error_message: string | null
}

export const triggerRetrain = () =>
  apiFetch<RetrainResponse>('/admin/ml/retrain', { method: 'POST' })

export const getTrainingJob = (jobId: string) =>
  apiFetch<TrainingJobResponse>(`/admin/ml/training-jobs/${jobId}`)

// ── Model package ─────────────────────────────────────────────────────────────

export interface PackageMeta {
  package_id: string
  reranker_version: number
  anomaly_detector_version: number
  created_at: string
  download_url: string
  size_bytes: number | null
}

export const getLatestPackage = () => apiFetch<PackageMeta>('/admin/ml/model-package/latest')

export const getDevice = (deviceId: string) =>
  apiFetch<{ device_id: string }>(`/api/v1/devices/${encodeURIComponent(deviceId)}`)

// ── Recommendations ───────────────────────────────────────────────────────────

export interface RecommendationItem {
  short_text: string
  max_score: number
  providers: string[]
  detail: string | null
  personal_relevance_score: number | null
  anomaly_suppressed: boolean
}

export interface RecommendationResponse {
  device_id: string
  trace_id: string
  recommendations: RecommendationItem[]
  providers_called: string[]
  providers_succeeded: string[]
  duration_ms: number
  credits_remaining: number
  reward_tier: string
}

export const getRecommendations = (deviceId: string) =>
  apiFetch<RecommendationResponse>(`/api/v1/devices/${deviceId}/recommendations`, {
    method: 'POST',
  })
