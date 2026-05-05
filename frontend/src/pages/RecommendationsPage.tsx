import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  getDevice,
  getLatestPackage,
  getRecommendations,
  getTrainingJob,
  triggerRetrain,
  type RecommendationItem,
  type TrainingJobResponse,
} from '../api/mlApi'
import { getApiKey } from '../api/creditApi'

// ── Helpers ───────────────────────────────────────────────────────────────────

function elapsed(from: string): string {
  const s = Math.floor((Date.now() - new Date(from).getTime()) / 1000)
  if (s < 60) return `${s}s`
  return `${Math.floor(s / 60)}m ${s % 60}s`
}

function fmt(n: number | null, decimals = 3): string {
  return n == null ? '—' : n.toFixed(decimals)
}

function formatBytes(b: number | null): string {
  if (b == null) return '—'
  if (b < 1024) return `${b} B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)} KB`
  return `${(b / 1024 / 1024).toFixed(1)} MB`
}

// ── Section 1 — Model Training ────────────────────────────────────────────────

type TrainingPhase = 'idle' | 'triggering' | 'polling' | 'done'

function TrainingSection() {
  const [phase, setPhase] = useState<TrainingPhase>('idle')
  const [job, setJob] = useState<TrainingJobResponse | null>(null)
  const [startedAt, setStartedAt] = useState<string | null>(null)
  const [_tick, setTick] = useState(0)
  const [apiError, setApiError] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPoll = () => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
  }

  // Tick every second while polling to update elapsed time display
  useEffect(() => {
    if (phase !== 'polling') return
    const t = setInterval(() => setTick(n => n + 1), 1000)
    return () => clearInterval(t)
  }, [phase])

  useEffect(() => () => stopPoll(), [])

  const triggerMutation = useMutation({
    mutationFn: triggerRetrain,
    onMutate: () => { setApiError(null); setPhase('triggering') },
    onSuccess: (data) => {
      setStartedAt(data.started_at)
      setPhase('polling')
      pollRef.current = setInterval(async () => {
        try {
          const j = await getTrainingJob(data.job_id)
          setJob(j)
          if (j.status !== 'running') { stopPoll(); setPhase('done') }
        } catch {
          stopPoll(); setPhase('done')
        }
      }, 3000)
    },
    onError: (err: Error & { status?: number; data?: { detail?: unknown } }) => {
      setPhase('idle')
      if (err.status === 409) {
        setApiError('Training already in progress. Wait for it to finish before triggering again.')
      } else {
        setApiError(err.message ?? 'Failed to trigger training')
      }
    },
  })

  const succeeded = job?.status === 'succeeded'
  const failed = job?.status === 'failed'

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
      <div>
        <h2 className="text-base font-semibold text-slate-800">Step 1 — Trigger Model Training</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          Runs the full extract → feature-engineer → train → evaluate → register pipeline for
          both the re-ranker and anomaly-detector models.
        </p>
      </div>

      {/* Flow diagram */}
      <ol className="flex flex-wrap items-center gap-2 text-xs text-slate-500 select-none">
        {['Extract data', 'Feature engineering', 'Train both models', 'Evaluate (NDCG / F1)', 'Register & activate'].map(
          (label, i) => (
            <li key={label} className="flex items-center gap-2">
              {i > 0 && <span className="text-slate-300">→</span>}
              <span
                className={`px-2 py-1 rounded-full border ${
                  phase === 'polling' || phase === 'done'
                    ? 'bg-blue-50 border-blue-200 text-blue-700'
                    : 'border-slate-200 bg-slate-50'
                }`}
              >
                {label}
              </span>
            </li>
          )
        )}
      </ol>

      {/* Trigger button */}
      {phase === 'idle' && (
        <button
          onClick={() => triggerMutation.mutate()}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50"
        >
          Trigger Retraining
        </button>
      )}

      {/* Triggering spinner */}
      {phase === 'triggering' && (
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Spinner />
          Sending request…
        </div>
      )}

      {/* Polling state */}
      {phase === 'polling' && startedAt && (
        <div className="flex items-center gap-2 text-sm text-blue-600">
          <Spinner />
          Training in progress — {elapsed(startedAt)} elapsed
        </div>
      )}

      {/* Error */}
      {apiError && (
        <p className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          {apiError}
        </p>
      )}

      {/* Done — succeeded */}
      {phase === 'done' && succeeded && job && (
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm text-green-700 font-medium">
            <span className="text-base">✓</span>
            Training succeeded
            {job.started_at && job.ended_at && (
              <span className="text-slate-400 font-normal">
                in {elapsed(job.started_at)}
              </span>
            )}
          </div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <MetricCard label="Re-ranker NDCG@10" value={fmt(job.reranker_ndcg_at_10)} good={job.reranker_ndcg_at_10 != null && job.reranker_ndcg_at_10 >= 0.7} />
            <MetricCard label="Anomaly Detector F1" value={fmt(job.anomaly_detector_f1)} good={job.anomaly_detector_f1 != null && job.anomaly_detector_f1 >= 0.7} />
            <MetricCard label="Triggered by" value={job.triggered_by} />
            <MetricCard label="Job ID" value={job.job_id.slice(0, 8) + '…'} mono />
          </div>
          <button
            onClick={() => { setPhase('idle'); setJob(null); setApiError(null) }}
            className="text-xs text-slate-500 hover:text-slate-700 underline"
          >
            Trigger another run
          </button>
        </div>
      )}

      {/* Done — failed */}
      {phase === 'done' && failed && job && (
        <div className="space-y-2">
          <div className="flex items-center gap-2 text-sm text-red-700 font-medium">
            <span>✕</span> Training failed
          </div>
          {job.error_message && (
            <p className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2 font-mono">
              {job.error_message}
            </p>
          )}
          <button
            onClick={() => { setPhase('idle'); setJob(null); setApiError(null) }}
            className="text-xs text-slate-500 hover:text-slate-700 underline"
          >
            Retry
          </button>
        </div>
      )}
    </section>
  )
}

// ── Section 2 — Download Model Package ───────────────────────────────────────

function ModelPackageSection() {
  const [deviceId, setDeviceId] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [downloadError, setDownloadError] = useState<string | null>(null)
  const qc = useQueryClient()

  const { data: pkg, isLoading, error, refetch } = useQuery({
    queryKey: ['ml-package-latest'],
    queryFn: getLatestPackage,
    retry: false,
  })

  const notFound = (error as Error & { status?: number })?.status === 404

  const handleDownload = async () => {
    if (!deviceId.trim() || !pkg) return
    setDownloadError(null)
    setDownloading(true)
    try {
      await getDevice(deviceId.trim())
    } catch (e) {
      const status = (e as Error & { status?: number }).status
      setDownloadError(
        status === 404
          ? `Device "${deviceId.trim()}" not found. Register it first via the Credits page.`
          : (e as Error).message ?? 'Failed to validate device'
      )
      setDownloading(false)
      return
    }

    try {
      const resp = await fetch(
        `${pkg.download_url}?device_id=${encodeURIComponent(deviceId.trim())}`,
        { headers: { 'X-API-Key': getApiKey() } }
      )
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({ detail: resp.statusText }))
        throw new Error(err.detail ?? 'Download failed')
      }

      const blob = await resp.blob()
      const disposition = resp.headers.get('content-disposition') ?? ''
      const match = disposition.match(/filename[^;=\n]*=["']?([^"';\n]+)["']?/)
      const filename = match?.[1]?.trim() ?? 'model-package.zip'

      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e) {
      setDownloadError((e as Error).message ?? 'Download failed')
    } finally {
      setDownloading(false)
    }
  }

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
      <div>
        <h2 className="text-base font-semibold text-slate-800">Step 2 — Download TFLite Model Package</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          The on-device ZIP contains both the re-ranker and anomaly-detector TFLite models
          along with a <code className="bg-slate-100 px-1 rounded text-xs">manifest.json</code> describing
          compatibility and version metadata.
        </p>
      </div>

      <div className="space-y-1">
        <label className="block text-xs font-medium text-slate-600">Device ID</label>
        <input
          type="text"
          value={deviceId}
          onChange={e => { setDeviceId(e.target.value); setDownloadError(null) }}
          placeholder="e.g. smartwatch-abc123"
          className="w-full max-w-sm px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 text-sm text-slate-400">
          <Spinner /> Loading latest package…
        </div>
      )}

      {notFound && (
        <div className="rounded-lg bg-slate-50 border border-slate-200 px-4 py-3 text-sm text-slate-500 space-y-2">
          <p>No model package available yet.</p>
          <p className="text-xs">Complete Step 1 to build the first model and auto-generate a distribution package.</p>
          <button
            onClick={() => { qc.invalidateQueries({ queryKey: ['ml-package-latest'] }); refetch() }}
            className="text-xs text-blue-600 hover:underline"
          >
            Refresh
          </button>
        </div>
      )}

      {pkg && (
        <div className="space-y-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <MetricCard label="Re-ranker version" value={`v${pkg.reranker_version}`} />
            <MetricCard label="Anomaly model version" value={`v${pkg.anomaly_detector_version}`} />
            <MetricCard label="Package size" value={formatBytes(pkg.size_bytes)} />
            <MetricCard label="Built at" value={new Date(pkg.created_at).toLocaleString()} />
          </div>

          {downloadError && (
            <p className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
              {downloadError}
            </p>
          )}

          <div className="flex flex-wrap gap-2 items-center">
            <button
              onClick={handleDownload}
              disabled={!deviceId.trim() || downloading}
              className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {downloading ? <><Spinner /> Downloading…</> : '↓ Download package'}
            </button>
            <button
              onClick={() => { qc.invalidateQueries({ queryKey: ['ml-package-latest'] }); refetch() }}
              className="px-3 py-2 text-sm text-slate-500 border border-slate-200 rounded-lg hover:bg-slate-50"
            >
              Refresh
            </button>
          </div>

          <p className="text-xs text-slate-400 font-mono">Package ID: {pkg.package_id}</p>
        </div>
      )}
    </section>
  )
}

// ── Section 3 — Personal Recommendations ─────────────────────────────────────

function RecommendationsSection() {
  const [deviceId, setDeviceId] = useState('')
  const [submittedId, setSubmittedId] = useState<string | null>(null)

  const mutation = useMutation({
    mutationFn: () => getRecommendations(deviceId.trim()),
    onMutate: () => setSubmittedId(deviceId.trim()),
  })

  const submit = () => {
    if (!deviceId.trim()) return
    mutation.mutate()
  }

  const errStatus = (mutation.error as Error & { status?: number })?.status

  return (
    <section className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
      <div>
        <h2 className="text-base font-semibold text-slate-800">Step 3 — Personal Recommendations</h2>
        <p className="text-sm text-slate-500 mt-0.5">
          Retrieve ML-re-ranked recommendations for a device. Items show a personal relevance score
          when the device has ≥ 7 days of telemetry and an active model. Anomalous readings may
          suppress activity-intensification items.
        </p>
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          value={deviceId}
          onChange={e => setDeviceId(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && submit()}
          placeholder="Device ID"
          className="flex-1 max-w-sm px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
        <button
          onClick={submit}
          disabled={!deviceId.trim() || mutation.isPending}
          className="px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 flex items-center gap-2"
        >
          {mutation.isPending && <Spinner />}
          Get Recommendations
        </button>
      </div>

      {/* Error states */}
      {mutation.isError && (
        <ErrorBanner status={errStatus} message={(mutation.error as Error).message} deviceId={submittedId} />
      )}

      {/* Results */}
      {mutation.isSuccess && mutation.data && (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500">
            <span>Device: <span className="font-mono text-slate-700">{mutation.data.device_id}</span></span>
            <span>{mutation.data.providers_succeeded.length}/{mutation.data.providers_called.length} providers</span>
            <span>{mutation.data.duration_ms.toFixed(0)} ms</span>
            <span>{mutation.data.credits_remaining} credits remaining</span>
            <TierPill tier={mutation.data.reward_tier} />
          </div>

          {mutation.data.recommendations.length === 0 ? (
            <p className="text-sm text-slate-400 italic">No recommendations returned.</p>
          ) : (
            <ul className="space-y-2">
              {mutation.data.recommendations.map((item, i) => (
                <RecommendationCard key={i} item={item} rank={i + 1} />
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}

function ErrorBanner({ status, message, deviceId }: { status?: number; message: string; deviceId: string | null }) {
  if (status === 404) return (
    <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
      Device <code className="font-mono">{deviceId}</code> not found. Register it first via the Credits page.
    </div>
  )
  if (status === 402) return (
    <div className="text-sm text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-4 py-3">
      Insufficient credits — top up on the Credits page before requesting recommendations.
    </div>
  )
  if (status === 503) return (
    <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
      All recommendation providers failed or timed out. Try again in a moment.
    </div>
  )
  return (
    <div className="text-sm text-red-700 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
      {message}
    </div>
  )
}

function RecommendationCard({ item, rank }: { item: RecommendationItem; rank: number }) {
  const isScored = item.personal_relevance_score != null
  const score = item.personal_relevance_score

  return (
    <li className={`border rounded-lg px-4 py-3 space-y-1.5 ${item.anomaly_suppressed ? 'border-amber-200 bg-amber-50' : 'border-slate-200 bg-white'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400 font-mono w-4">#{rank}</span>
          <span className="text-sm font-medium text-slate-800">{item.short_text}</span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {item.anomaly_suppressed && (
            <span className="text-xs bg-amber-200 text-amber-800 px-2 py-0.5 rounded-full font-medium">
              anomaly suppressed
            </span>
          )}
          {isScored ? (
            <span
              className="text-xs font-mono px-2 py-0.5 rounded-full border"
              style={{ background: scoreColor(score!).bg, borderColor: scoreColor(score!).border, color: scoreColor(score!).text }}
              title="Personal relevance score"
            >
              {(score! * 100).toFixed(1)}%
            </span>
          ) : (
            <span className="text-xs text-slate-400 px-2 py-0.5 rounded-full border border-slate-200 bg-slate-50" title="Cold-start: no embedding yet">
              cold-start
            </span>
          )}
        </div>
      </div>

      {item.detail && (
        <p className="text-xs text-slate-500 ml-6">{item.detail}</p>
      )}

      <div className="flex flex-wrap gap-1 ml-6">
        {item.providers.map(p => (
          <span key={p} className="text-xs bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">
            {p}
          </span>
        ))}
      </div>
    </li>
  )
}

function scoreColor(score: number) {
  if (score >= 0.7) return { bg: '#f0fdf4', border: '#bbf7d0', text: '#15803d' }
  if (score >= 0.4) return { bg: '#fffbeb', border: '#fde68a', text: '#92400e' }
  return { bg: '#fef2f2', border: '#fecaca', text: '#991b1b' }
}

// ── Shared small components ───────────────────────────────────────────────────

function MetricCard({ label, value, good, mono }: { label: string; value: string; good?: boolean; mono?: boolean }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2.5 space-y-0.5">
      <p className="text-xs text-slate-500">{label}</p>
      <p
        className={`text-sm font-semibold truncate ${mono ? 'font-mono' : ''} ${
          good === true ? 'text-green-700' : good === false ? 'text-amber-600' : 'text-slate-800'
        }`}
      >
        {value}
      </p>
    </div>
  )
}

function TierPill({ tier }: { tier: string }) {
  const colors: Record<string, string> = {
    bronze: 'bg-amber-100 text-amber-800',
    silver: 'bg-slate-200 text-slate-700',
    gold: 'bg-yellow-100 text-yellow-800',
    platinum: 'bg-cyan-100 text-cyan-800',
  }
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium capitalize ${colors[tier] ?? 'bg-slate-100 text-slate-600'}`}>
      {tier}
    </span>
  )
}

function Spinner() {
  return (
    <svg className="animate-spin h-4 w-4 text-current" fill="none" viewBox="0 0 24 24">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function RecommendationsPage() {
  return (
    <div className="max-w-5xl mx-auto p-6 space-y-6">
      <div className="space-y-1">
        <h1 className="text-xl font-bold text-slate-800">Recommendations</h1>
        <p className="text-sm text-slate-500">
          Train ML models, download the on-device package, and test personalised recommendations.
        </p>
      </div>
      <TrainingSection />
      <ModelPackageSection />
      <RecommendationsSection />
    </div>
  )
}
