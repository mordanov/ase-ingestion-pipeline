interface TierProgressBarProps {
  cumulativeEarned: number
  nextTier: string | null
  creditsToNextTier: number | null
  nextTierThreshold: number
}

export function TierProgressBar({
  cumulativeEarned,
  nextTier,
  creditsToNextTier,
  nextTierThreshold,
}: TierProgressBarProps) {
  if (!nextTier || creditsToNextTier === null || creditsToNextTier === 0) {
    return (
      <div className="space-y-1">
        <div className="h-2 rounded-full bg-cyan-400 w-full" />
        <p className="text-xs text-cyan-600 font-semibold">MAX TIER</p>
      </div>
    )
  }

  const pct = Math.min(100, (cumulativeEarned / nextTierThreshold) * 100)
  const nextLabel = nextTier.charAt(0).toUpperCase() + nextTier.slice(1)

  return (
    <div className="space-y-1">
      <div className="h-2 rounded-full bg-slate-200 overflow-hidden">
        <div
          role="progressbar"
          aria-valuenow={pct}
          aria-valuemin={0}
          aria-valuemax={100}
          className="h-full rounded-full bg-blue-500 transition-all duration-300"
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-slate-500">
        {creditsToNextTier} credits to {nextLabel}
      </p>
    </div>
  )
}
