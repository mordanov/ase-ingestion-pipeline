import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { getDeviceTransactions, type TransactionItem } from '../api/creditApi'

const ACTION_TYPE_LABELS: Record<string, string> = {
  recommendation: 'Recommendation',
  registration_bonus: 'Registration',
  top_up: 'Top-Up',
  activity_reward: 'Activity',
  streak_bonus: 'Streak',
  adjustment: 'Adjustment',
  tier_discount: 'Tier Discount',
}

interface TransactionTableProps {
  deviceId: string
}

export function TransactionTable({ deviceId }: TransactionTableProps) {
  const [offset, setOffset] = useState(0)
  const limit = 20

  const { data, isLoading, isError } = useQuery({
    queryKey: ['transactions', deviceId, offset],
    queryFn: () => getDeviceTransactions(deviceId, { limit, offset }),
  })

  if (isLoading) return <p className="text-sm text-slate-400">Loading transactions…</p>
  if (isError) return <p className="text-sm text-red-500">Failed to load transactions.</p>
  if (!data || data.items.length === 0)
    return <p className="text-sm text-slate-400">No transactions yet.</p>

  const totalPages = Math.ceil(data.total / limit)
  const currentPage = Math.floor(offset / limit) + 1

  return (
    <div className="space-y-2">
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <table className="min-w-full text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-3 py-2 text-left">Date</th>
              <th className="px-3 py-2 text-left">Type</th>
              <th className="px-3 py-2 text-right">Amount</th>
              <th className="px-3 py-2 text-left">Reason</th>
              <th className="px-3 py-2 text-right">Balance After</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {data.items.map((tx: TransactionItem) => (
              <tr key={tx.id} className="hover:bg-slate-50">
                <td className="px-3 py-2 text-slate-500 whitespace-nowrap">
                  {new Date(tx.created_at).toLocaleString()}
                </td>
                <td className="px-3 py-2">
                  <span className="inline-block px-2 py-0.5 rounded text-xs bg-slate-100 text-slate-600">
                    {ACTION_TYPE_LABELS[tx.action_type] ?? tx.action_type}
                  </span>
                </td>
                <td className={`px-3 py-2 text-right font-mono font-medium ${tx.amount >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                  {tx.amount >= 0 ? `+${tx.amount}` : tx.amount}
                </td>
                <td className="px-3 py-2 text-slate-600 max-w-xs truncate">{tx.reason}</td>
                <td className="px-3 py-2 text-right font-mono text-slate-700">{tx.resulting_balance}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>
            Page {currentPage} of {totalPages} ({data.total} total)
          </span>
          <div className="flex gap-2">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - limit))}
              className="px-2 py-1 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
            >
              Previous
            </button>
            <button
              disabled={offset + limit >= data.total}
              onClick={() => setOffset(offset + limit)}
              className="px-2 py-1 rounded border border-slate-200 disabled:opacity-40 hover:bg-slate-50"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
