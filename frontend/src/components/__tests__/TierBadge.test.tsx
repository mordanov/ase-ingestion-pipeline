import { render, screen } from '@testing-library/react'
import { describe, it, expect } from 'vitest'
import { TierBadge } from '../TierBadge'

describe('TierBadge', () => {
  it('renders bronze tier with correct label', () => {
    render(<TierBadge tier="bronze" />)
    expect(screen.getByText('Bronze')).toBeTruthy()
  })

  it('renders silver tier with correct label', () => {
    render(<TierBadge tier="silver" />)
    expect(screen.getByText('Silver')).toBeTruthy()
  })

  it('renders gold tier with correct label', () => {
    render(<TierBadge tier="gold" />)
    expect(screen.getByText('Gold')).toBeTruthy()
  })

  it('renders platinum tier with correct label', () => {
    render(<TierBadge tier="platinum" />)
    expect(screen.getByText('Platinum')).toBeTruthy()
  })

  it('applies amber color class for bronze', () => {
    const { container } = render(<TierBadge tier="bronze" />)
    const badge = container.firstChild as HTMLElement
    expect(badge.className).toMatch(/amber/)
  })

  it('applies cyan color class for platinum', () => {
    const { container } = render(<TierBadge tier="platinum" />)
    const badge = container.firstChild as HTMLElement
    expect(badge.className).toMatch(/cyan/)
  })
})
