import { describe, it, expect, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, vars?: Record<string, unknown>) =>
      vars && 'n' in vars ? `${key}:${String(vars.n)}` : key,
  }),
}))
import { render, screen, fireEvent } from '@testing-library/react'
import TimelineRail from '@/components/dashboard/TimelineRail'
import type { ChatMessage } from '@/types'

function makeMsgs(count: number, role: 'user' | 'assistant' = 'user'): ChatMessage[] {
  return Array.from({ length: count }, (_, i) => ({
    id: `${role}-${i}`,
    role,
    content: `msg ${i}`,
    timestamp: Date.now() + i,
  }))
}

describe('TimelineRail', () => {
  it('renders one marker per message', () => {
    render(<TimelineRail messages={makeMsgs(5)} activeIndex={0} onSelect={vi.fn()} />)
    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(5)
  })

  it('renders nothing for an empty conversation', () => {
    const { container } = render(<TimelineRail messages={[]} activeIndex={-1} onSelect={vi.fn()} />)
    expect(container.querySelector('[aria-label="Timeline"]')).toBeNull()
  })

  it('fires onSelect with the message index on click', () => {
    const onSelect = vi.fn()
    render(<TimelineRail messages={makeMsgs(3)} activeIndex={0} onSelect={onSelect} />)
    fireEvent.click(screen.getByTitle('chat.goToMessage:3'))
    expect(onSelect).toHaveBeenCalledWith(2)
  })

  it('highlights the active message marker', () => {
    const { container } = render(
      <TimelineRail messages={makeMsgs(4)} activeIndex={2} onSelect={vi.fn()} />,
    )
    // the active marker carries the chat.activeMarker suffix in its title
    const active = container.querySelector('[title*="chat.goToMessage:3"]')
    expect(active).toBeTruthy()
    // B-8: the tap-target wrapper (button) carries the hit box, the inner span
    // the active ring — the marking sits on the span, not on the button.
    const dot = active?.querySelector('span')
    expect(dot?.getAttribute('class')).toContain('ring')
  })
})
