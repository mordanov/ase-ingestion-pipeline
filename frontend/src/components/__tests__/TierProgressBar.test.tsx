import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { TierProgressBar } from '../TierProgressBar'

describe('TierProgressBar', () => {
  it('shows credits to next tier label', () => {
    render(
      <TierProgressBar
        cumulativeEarned={500}
        nextTier="silver"
        creditsToNextTier={500}
        nextTierThreshold={1000}
      />
    )
    expect(screen.getByText(/500 credits to Silver/i)).toBeTruthy()
  })

  it('calculates correct progress width at 50%', () => {
    const { container } = render(
      <TierProgressBar
        cumulativeEarned={500}
        nextTier="silver"
        creditsToNextTier={500}
        nextTierThreshold={1000}
      />
    )
    const progressBar = container.querySelector('[role="progressbar"]') as HTMLElement
    expect(progressBar).toBeTruthy()
    // 500/1000 = 50%
    expect(progressBar.style.width).toBe('50%')
  })

  it('shows MAX TIER for platinum', () => {
    render(
      <TierProgressBar
        cumulativeEarned={25000}
        nextTier="platinum"
        creditsToNextTier={0}
        nextTierThreshold={20000}
      />
    )
    expect(screen.getByText(/MAX TIER/i)).toBeTruthy()
  })

  it('caps progress bar at 100% even if earned exceeds threshold', () => {
    const { container } = render(
      <TierProgressBar
        cumulativeEarned={6000}
        nextTier="gold"
        creditsToNextTier={100}
        nextTierThreshold={5000}
      />
    )
    const progressBar = container.querySelector('[role="progressbar"]') as HTMLElement
    expect(progressBar).toBeTruthy()
    const widthValue = parseFloat(progressBar.style.width)
    expect(widthValue).toBeLessThanOrEqual(100)
  })
})
