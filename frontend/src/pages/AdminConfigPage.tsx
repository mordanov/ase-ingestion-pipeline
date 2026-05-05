import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { getCreditConfig, updateCreditConfig, type CreditConfig } from '../api/creditApi'

function KVEditor({
  label,
  value,
  onChange,
}: {
  label: string
  value: Record<string, number>
  onChange: (v: Record<string, number>) => void
}) {
  return (
    <div>
      <p className="text-sm font-medium text-slate-700 mb-1">{label}</p>
      <div className="space-y-1">
        {Object.entries(value).map(([k, v]) => (
          <div key={k} className="flex gap-2 items-center">
            <input
              className="flex-1 px-2 py-1 border border-slate-300 rounded text-sm"
              value={k}
              onChange={(e) => {
                const next = { ...value }
                delete next[k]
                next[e.target.value] = v
                onChange(next)
              }}
            />
            <input
              type="number"
              className="w-24 px-2 py-1 border border-slate-300 rounded text-sm"
              value={v}
              onChange={(e) => onChange({ ...value, [k]: Number(e.target.value) })}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

export function AdminConfigPage() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: ['creditConfig'],
    queryFn: getCreditConfig,
  })

  const [form, setForm] = useState<Partial<CreditConfig>>({})
  const [toast, setToast] = useState<string | null>(null)

  useEffect(() => {
    if (data) setForm(data)
  }, [data])

  const mutation = useMutation({
    mutationFn: (d: Partial<CreditConfig>) => updateCreditConfig(d),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['creditConfig'] })
      setToast('Configuration updated successfully!')
      setTimeout(() => setToast(null), 3000)
    },
    onError: (e: Error) => {
      setToast(`Error: ${e.message}`)
      setTimeout(() => setToast(null), 4000)
    },
  })

  if (isLoading) return <p className="p-6 text-slate-400 text-sm">Loading config…</p>

  const field = (key: keyof CreditConfig) => ({
    value: (form[key] as number) ?? 0,
    onChange: (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm((f) => ({ ...f, [key]: Number(e.target.value) })),
  })

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <h1 className="text-2xl font-bold text-slate-800">Admin — Credit Configuration</h1>
      <p className="text-sm text-slate-500">Version {data?.version} (active)</p>

      {toast && (
        <div className="px-4 py-2 rounded bg-green-50 border border-green-200 text-green-700 text-sm">
          {toast}
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault()
          mutation.mutate(form)
        }}
        className="space-y-6"
      >
        {/* Default balance */}
        <div>
          <label className="text-sm font-medium text-slate-700">Default Initial Balance</label>
          <input type="number" {...field('default_initial_balance')} className="mt-1 block w-32 px-2 py-1 border border-slate-300 rounded text-sm" />
        </div>

        {/* Earning rules */}
        {form.activity_earning_rules && (
          <KVEditor
            label="Activity Earning Rules (credits per scenario)"
            value={form.activity_earning_rules}
            onChange={(v) => setForm((f) => ({ ...f, activity_earning_rules: v }))}
          />
        )}

        {/* Service costs */}
        {form.service_costs && (
          <KVEditor
            label="Service Costs (credits per service)"
            value={form.service_costs}
            onChange={(v) => setForm((f) => ({ ...f, service_costs: v }))}
          />
        )}

        {/* Streak bonuses */}
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-sm font-medium text-slate-700">7-Day Streak Bonus</label>
            <input type="number" {...field('streak_bonus_7d')} className="mt-1 block w-32 px-2 py-1 border border-slate-300 rounded text-sm" />
          </div>
          <div>
            <label className="text-sm font-medium text-slate-700">30-Day Streak Bonus</label>
            <input type="number" {...field('streak_bonus_30d')} className="mt-1 block w-32 px-2 py-1 border border-slate-300 rounded text-sm" />
          </div>
        </div>

        {/* Tier thresholds */}
        {form.tier_thresholds && (
          <KVEditor
            label="Tier Thresholds (cumulative earned)"
            value={form.tier_thresholds}
            onChange={(v) => setForm((f) => ({ ...f, tier_thresholds: v }))}
          />
        )}

        {/* Tier multipliers */}
        {form.tier_multipliers && (
          <KVEditor
            label="Tier Multipliers"
            value={form.tier_multipliers}
            onChange={(v) => setForm((f) => ({ ...f, tier_multipliers: v as Record<string, number> }))}
          />
        )}

        {/* Tier discounts */}
        {form.tier_discounts && (
          <KVEditor
            label="Tier Discounts (0.0–1.0)"
            value={form.tier_discounts}
            onChange={(v) => setForm((f) => ({ ...f, tier_discounts: v as Record<string, number> }))}
          />
        )}

        <button
          type="submit"
          disabled={mutation.isPending}
          className="px-6 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {mutation.isPending ? 'Saving…' : 'Save Configuration'}
        </button>
      </form>
    </div>
  )
}
