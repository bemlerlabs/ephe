import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import ChatSkeleton from './ChatSkeleton'

describe('ChatSkeleton (P1-10)', () => {
  it('rendert den Boot-Placeholder mit aria-hidden (SR bekommt nichts vorgegaukelt)', () => {
    render(<ChatSkeleton />)
    const el = screen.getByTestId('chat-skeleton')
    expect(el).toBeTruthy()
    expect(el.getAttribute('aria-hidden')).toBe('true')
  })

  it('deutet mehrere Turns an (mehrere Skeleton-Bars vorhanden)', () => {
    const { container } = render(<ChatSkeleton />)
    // Three turn blocks of 2–3 bars each → clearly more than a single placeholder.
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThanOrEqual(6)
  })
})
