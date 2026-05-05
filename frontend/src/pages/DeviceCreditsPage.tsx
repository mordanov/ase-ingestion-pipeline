import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getDeviceCredits, getDeviceEvents, type MeasurementEvent } from '../api/creditApi'
import { TierBadge } from '../components/TierBadge'
import { TierProgressBar } from '../components/TierProgressBar'
import { TransactionTable } from '../components/TransactionTable'

const SCENARIO_LABEL: Record<string, string> = {
  workout: 'Workout',
  sleep: 'Sleep',
  rest: 'Rest',
  default: 'General',
}

const STATUS_CLASSES: Record<string, string> = {
  valid: 'bg-green-100 text-green-700',
  stale: 'bg-yellow-100 text-yellow-700',
  invalid: 'bg-red-100 text-red-700',
}

function MeasurementsTable({ deviceId }: { deviceId: string }) {
  const [offset, setOffset] = useState(0)
  const limit = 10

  const { data, isLoading } = useQuery({
    queryKey: ['deviceEvents', deviceId, offset],
    queryFn: () => getDeviceEvents(deviceId, { limit, offset }),
  })

  if (isLoading) return <p className="text-slate-400 text-sm">Loading measurements…</p>
  if (!data?.items.length) return <p className="text-slate-400 text-sm">No measurements recorded yet.</p>

  const totalPages = Math.ceil(data.total / limit)
  const page = Math.floor(offset / limit) + 1

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
            <tr>
              <th className="px-3 py-2 text-left">Time</th>
              <th className="px-3 py-2 text-left">Scenario</th>
              <th className="px-3 py-2 text-right">HR (bpm)</th>
              <th className="px-3 py-2 text-right">SpO2 (%)</th>
              <th className="px-3 py-2 text-left">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.items.map((ev: MeasurementEvent) => (
              <tr key={ev.event_id} className="hover:bg-slate-50">
                <td className="px-3 py-2 text-slate-500 whitespace-nowrap">
                  {new Date(ev.event_timestamp).toLocaleString()}
                </td>
                <td className="px-3 py-2 capitalize text-slate-700">
                  {SCENARIO_LABEL[ev.scenario ?? ''] ?? ev.scenario ?? '—'}
                </td>
                <td className="px-3 py-2 text-right font-mono text-slate-700">
                  {ev.heart_rate_bpm ?? '—'}
                </td>
                <td className="px-3 py-2 text-right font-mono text-slate-700">
                  {ev.spo2_pct != null ? ev.spo2_pct.toFixed(1) : '—'}
                </td>
                <td className="px-3 py-2">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_CLASSES[ev.validation_status] ?? ''}`}>
                    {ev.is_anomaly ? '⚠ anomaly' : ev.validation_status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>Page {page} of {totalPages} ({data.total} total)</span>
          <div className="flex gap-2">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - limit))}
              className="px-2 py-1 rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-40"
            >
              Prev
            </button>
            <button
              disabled={offset + limit >= data.total}
              onClick={() => setOffset(offset + limit)}
              className="px-2 py-1 rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

export function DeviceCreditsPage() {
  const [inputId, setInputId] = useState('')
  const [deviceId, setDeviceId] = useState<string | null>(null)

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ['deviceCredits', deviceId],
    queryFn: () => getDeviceCredits(deviceId!),
    enabled: !!deviceId,
    retry: false,
  })

  const apiError = error as (Error & { status?: number }) | null
  const notFound = apiError?.status === 404

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setDeviceId(inputId.trim() || null)
  }

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold text-slate-800">Device Credits Dashboard</h1>

      <form onSubmit={handleSearch} className="flex gap-2">
        <input
          type="text"
          value={inputId}
          onChange={(e) => setInputId(e.target.value)}
          placeholder="Enter device ID…"
          className="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
        />
        <button
          type="submit"
          className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700"
        >
          Look up
        </button>
      </form>

      {isLoading && <p className="text-slate-400 text-sm">Loading…</p>}
      {notFound && (
        <p className="text-red-500 text-sm">Device not found: {deviceId}</p>
      )}
      {isError && !notFound && (
        <p className="text-red-500 text-sm">Failed to load device data.</p>
      )}

      {data && (
        <div className="space-y-4">
          {/* Balance card */}
          <div className="rounded-xl border border-slate-200 p-5 bg-white shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold text-slate-700">{data.device_id}</h2>
              <TierBadge tier={data.reward_tier} />
            </div>
            <div className="grid grid-cols-3 gap-4 text-center">
              <div>
                <p className="text-2xl font-bold text-blue-600">{data.credit_balance}</p>
                <p className="text-xs text-slate-500">Balance</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-green-600">{data.cumulative_credits_earned}</p>
                <p className="text-xs text-slate-500">Earned</p>
              </div>
              <div>
                <p className="text-2xl font-bold text-orange-500">🔥 {data.streak_days}</p>
                <p className="text-xs text-slate-500">Day streak</p>
              </div>
            </div>
            <TierProgressBar
              cumulativeEarned={data.cumulative_credits_earned}
              nextTier={data.next_tier}
              creditsToNextTier={data.credits_to_next_tier}
              nextTierThreshold={
                (data.credits_to_next_tier ?? 0) + data.cumulative_credits_earned
              }
            />
            <p className="text-xs text-slate-400">
              Multiplier: {data.tier_multiplier}× | Discount: {(data.tier_discount * 100).toFixed(0)}%
            </p>
          </div>

          {/* Measurement history */}
          <div>
            <h3 className="text-base font-semibold text-slate-700 mb-2">Recent Measurements</h3>
            <MeasurementsTable deviceId={data.device_id} />
          </div>

          {/* Transaction history */}
          <div>
            <h3 className="text-base font-semibold text-slate-700 mb-2">Transaction History</h3>
            <TransactionTable deviceId={data.device_id} />
          </div>
        </div>
      )}
    </div>
  )
}
