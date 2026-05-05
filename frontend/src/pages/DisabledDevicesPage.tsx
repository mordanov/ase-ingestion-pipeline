import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { listDisabledDevices, addDisabledDevice, removeDisabledDevice } from '../api/rulesApi'

export function DisabledDevicesPage() {
  const qc = useQueryClient()
  const [input, setInput] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const { data = [], isLoading, error } = useQuery({
    queryKey: ['disabled-devices'],
    queryFn: listDisabledDevices,
  })

  const addMutation = useMutation({
    mutationFn: addDisabledDevice,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['disabled-devices'] })
      setInput('')
      setFormError(null)
    },
    onError: (err: Error & { status?: number }) => {
      if (err.status === 404) setFormError('Device not found — register it first.')
      else if (err.status === 409) setFormError('Device is already disabled.')
      else setFormError(err.message)
    },
  })

  const removeMutation = useMutation({
    mutationFn: removeDisabledDevice,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['disabled-devices'] }),
  })

  const handleDisable = () => {
    const id = input.trim()
    if (!id) { setFormError('Device ID is required'); return }
    setFormError(null)
    addMutation.mutate(id)
  }

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-800">Disabled Devices</h1>
        <p className="text-sm text-slate-500 mt-1">
          Devices on this list are blocked from sending events and getting recommendations.
        </p>
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
        <h2 className="text-sm font-semibold text-slate-700">Disable a device</h2>
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleDisable()}
            placeholder="device_id"
            className="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-sm font-mono"
          />
          <button
            onClick={handleDisable}
            disabled={addMutation.isPending}
            className="px-4 py-2 bg-red-600 text-white rounded-lg text-sm font-medium hover:bg-red-700 disabled:opacity-50"
          >
            {addMutation.isPending ? 'Disabling…' : 'Disable Device'}
          </button>
        </div>
        {formError && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded px-3 py-2">
            {formError}
          </p>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl overflow-hidden">
        {isLoading && (
          <p className="p-4 text-sm text-slate-500">Loading…</p>
        )}
        {error && (
          <p className="p-4 text-sm text-red-600">Failed to load: {(error as Error).message}</p>
        )}
        {!isLoading && !error && data.length === 0 && (
          <p className="p-4 text-sm text-slate-400">No devices are currently disabled.</p>
        )}
        {data.length > 0 && (
          <table className="w-full text-sm">
            <thead className="bg-slate-50 border-b border-slate-200">
              <tr>
                <th className="text-left px-4 py-2.5 font-medium text-slate-600">Device ID</th>
                <th className="text-left px-4 py-2.5 font-medium text-slate-600">Type</th>
                <th className="text-left px-4 py-2.5 font-medium text-slate-600">Disabled At</th>
                <th className="px-4 py-2.5" />
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {data.map((row) => (
                <tr key={row.device_id} className="hover:bg-slate-50">
                  <td className="px-4 py-2.5 font-mono text-slate-800">{row.device_id}</td>
                  <td className="px-4 py-2.5 text-slate-600 capitalize">{row.device_type}</td>
                  <td className="px-4 py-2.5 text-slate-500">
                    {new Date(row.disabled_at).toLocaleString()}
                  </td>
                  <td className="px-4 py-2.5 text-right">
                    <button
                      onClick={() => removeMutation.mutate(row.device_id)}
                      disabled={removeMutation.isPending}
                      className="text-xs px-2.5 py-1 border border-slate-200 rounded hover:bg-red-50 hover:border-red-200 hover:text-red-700 text-slate-500 disabled:opacity-50"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
