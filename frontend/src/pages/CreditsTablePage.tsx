import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listDevices, adjustCredits, type DeviceListItem } from '../api/creditApi'
import { TierBadge } from '../components/TierBadge'

const LIMIT = 50

function EditableBalance({
  deviceId,
  currentBalance,
  onSaved,
}: {
  deviceId: string
  currentBalance: number
  onSaved: () => void
}) {
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState(String(currentBalance))
  const inputRef = useRef<HTMLInputElement>(null)
  const qc = useQueryClient()

  useEffect(() => {
    if (editing) {
      setValue(String(currentBalance))
      inputRef.current?.select()
    }
  }, [editing, currentBalance])

  const mutation = useMutation({
    mutationFn: (newBalance: number) => {
      const delta = newBalance - currentBalance
      return adjustCredits(deviceId, delta)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['devices'] })
      setEditing(false)
      onSaved()
    },
  })

  if (!editing) {
    return (
      <button
        onClick={() => setEditing(true)}
        className="font-mono font-semibold text-blue-700 hover:underline focus:outline-none"
        title="Click to edit"
      >
        {currentBalance}
      </button>
    )
  }

  const commit = () => {
    const n = parseInt(value, 10)
    if (isNaN(n) || n === currentBalance) { setEditing(false); return }
    mutation.mutate(n)
  }

  return (
    <input
      ref={inputRef}
      type="number"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      onBlur={commit}
      onKeyDown={(e) => {
        if (e.key === 'Enter') commit()
        if (e.key === 'Escape') setEditing(false)
      }}
      className="w-24 px-2 py-0.5 border border-blue-400 rounded font-mono text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
      disabled={mutation.isPending}
    />
  )
}

export function CreditsTablePage() {
  const [search, setSearch] = useState('')
  const [debouncedSearch, setDebouncedSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const qc = useQueryClient()

  useEffect(() => {
    const t = setTimeout(() => { setDebouncedSearch(search); setOffset(0) }, 300)
    return () => clearTimeout(t)
  }, [search])

  const { data, isLoading } = useQuery({
    queryKey: ['devices', debouncedSearch, offset],
    queryFn: () => listDevices({ search: debouncedSearch || undefined, limit: LIMIT, offset }),
  })

  const totalPages = data ? Math.ceil(data.total / LIMIT) : 0
  const page = Math.floor(offset / LIMIT) + 1

  return (
    <div className="p-6 space-y-4 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-800">Credits Dashboard</h1>

      <input
        type="search"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search by device ID…"
        className="w-full max-w-sm px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
      />

      {isLoading && <p className="text-slate-400 text-sm">Loading…</p>}

      {data && (
        <>
          <div className="overflow-x-auto rounded-xl border border-slate-200 shadow-sm">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                <tr>
                  <th className="px-4 py-3 text-left">Device ID</th>
                  <th className="px-4 py-3 text-left">Tier</th>
                  <th className="px-4 py-3 text-right">Credits</th>
                  <th className="px-4 py-3 text-right">Earned</th>
                  <th className="px-4 py-3 text-right">Streak</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((d: DeviceListItem) => (
                  <tr key={d.device_id} className="hover:bg-slate-50 transition-colors">
                    <td className="px-4 py-3 font-mono text-slate-700 text-xs">{d.device_id}</td>
                    <td className="px-4 py-3">
                      <TierBadge tier={d.reward_tier} />
                    </td>
                    <td className="px-4 py-3 text-right">
                      <EditableBalance
                        deviceId={d.device_id}
                        currentBalance={d.credit_balance}
                        onSaved={() => qc.invalidateQueries({ queryKey: ['devices'] })}
                      />
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-slate-500">{d.cumulative_credits_earned}</td>
                    <td className="px-4 py-3 text-right text-slate-500">🔥 {d.streak_days}d</td>
                  </tr>
                ))}
                {data.items.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-slate-400 text-sm">
                      No devices found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="flex items-center justify-between text-xs text-slate-500">
              <span>Page {page} of {totalPages} ({data.total} total)</span>
              <div className="flex gap-2">
                <button
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - LIMIT))}
                  className="px-3 py-1 rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-40"
                >
                  Prev
                </button>
                <button
                  disabled={offset + LIMIT >= data.total}
                  onClick={() => setOffset(offset + LIMIT)}
                  className="px-3 py-1 rounded border border-slate-200 hover:bg-slate-50 disabled:opacity-40"
                >
                  Next
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
