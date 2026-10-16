import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import '@/i18n'
import ChatInput from '@/components/dashboard/ChatInput'

// P1 [F4 reference "Keep typing to queue follow-up changes"]: during a
// running turn the composer shows the queue hint as the placeholder and
// the queue counter as a badge right on the stop button.

vi.mock('@/lib/api', () => ({
  getModelProviders: () => Promise.reject(new Error('offline')),
  getSetupStatus: () => Promise.reject(new Error('offline')),
  getSettings: () => Promise.resolve({ workspace_dir: '/tmp/ws' }),
  listFs: () =>
    Promise.resolve({
      path: '/tmp/ws',
      parent: null,
      home: '/tmp',
      workspace: '/tmp/ws',
      entries: [],
    }),
  listSkills: () => Promise.resolve({ skills: [] }),
}))

const ta = () => screen.getByRole('textbox') as HTMLTextAreaElement

describe('ChatInput Queue-Hinweis (P1, Referenz-Parität)', () => {
  it('Placeholder wechselt im Stream zum Queue-Hinweis, danach zurück', () => {
    const onSend = vi.fn()
    const { rerender } = render(<ChatInput onSend={onSend} streaming={false} />)
    const idle = ta().getAttribute('placeholder') ?? ''

    rerender(<ChatInput onSend={onSend} streaming={true} />)
    const queued = ta().getAttribute('placeholder') ?? ''
    expect(queued).not.toBe(idle)
    expect(queued.toLowerCase()).toContain('queue')

    rerender(<ChatInput onSend={onSend} streaming={false} />)
    expect(ta().getAttribute('placeholder')).toBe(idle)
  })

  it('Queue-Badge zählt am Stop-Knopf mit und verschwindet nach dem Flush', () => {
    const onSend = vi.fn()
    const { rerender } = render(<ChatInput onSend={onSend} streaming={false} />)
    rerender(<ChatInput onSend={onSend} streaming={true} />)
    expect(screen.queryByTestId('composer-queue-badge')).toBeNull()

    fireEvent.change(ta(), { target: { value: 'erste Queue-Nachricht' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })
    fireEvent.change(ta(), { target: { value: 'zweite Queue-Nachricht' } })
    fireEvent.keyDown(ta(), { key: 'Enter' })

    const badge = screen.getByTestId('composer-queue-badge')
    expect(badge.textContent).toBe('2')

    // Stream settles → FIFO flush; the badge counts down and disappears.
    rerender(<ChatInput onSend={onSend} streaming={false} />)
    expect(onSend).toHaveBeenCalledTimes(1)
    expect(screen.queryByTestId('composer-queue-badge')).toBeNull()
  })
})

// D2: the placeholder promised the queue whenever the deep setting allowed
// typing, ignoring a disabled composer — where handleSend returns before it can
// enqueue anything. The wording now follows what the composer can do.
describe('the composer placeholder tells the truth', () => {
  it('a disabled composer reads as busy, and the queue wording returns once it can run', () => {
    const onSend = vi.fn()
    const { rerender } = render(<ChatInput onSend={onSend} streaming={false} />)
    const idle = ta().getAttribute('placeholder') ?? ''

    rerender(<ChatInput onSend={onSend} streaming disabled />)
    const blocked = ta().getAttribute('placeholder') ?? ''
    expect(blocked).not.toBe(idle)
    expect(blocked.toLowerCase()).not.toContain('queue')
    expect(blocked).toBe('Ephe is working — typing is disabled during the answer')

    rerender(<ChatInput onSend={onSend} streaming />)
    expect(ta().getAttribute('placeholder')).toBe(
      'Queue your next task — Ephe works through it after the current one',
    )
  })
})
