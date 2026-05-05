const TIER_STYLES: Record<string, string> = {
  bronze: 'bg-amber-100 text-amber-800 border-amber-300',
  silver: 'bg-gray-100 text-gray-700 border-gray-300',
  gold: 'bg-yellow-100 text-yellow-800 border-yellow-300',
  platinum: 'bg-cyan-100 text-cyan-800 border-cyan-300',
}

interface TierBadgeProps {
  tier: string
}

export function TierBadge({ tier }: TierBadgeProps) {
  const styles = TIER_STYLES[tier] ?? 'bg-slate-100 text-slate-700 border-slate-300'
  const label = tier.charAt(0).toUpperCase() + tier.slice(1)
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${styles}`}
    >
      {label}
    </span>
  )
}
