import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ChatSkeleton from './ChatSkeleton'

describe('ChatSkeleton (P1-10)', () => {
  it('renders the boot placeholder with aria-hidden (no fake state for SR)', () => {
    render(<ChatSkeleton />)
    const el = screen.getByTestId('chat-skeleton')
    expect(el).toBeTruthy()
    expect(el.getAttribute('aria-hidden')).toBe('true')
  })

  it('hints at several turns (several skeleton bars are present)', () => {
    const { container } = render(<ChatSkeleton />)
    // Three turn blocks of 2–3 bars each → clearly more than a single placeholder.
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThanOrEqual(6)
  })
})
