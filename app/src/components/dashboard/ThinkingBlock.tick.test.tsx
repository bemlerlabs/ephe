/**
 * P3: the thinking phase ticks live ("Thinking… · Ns").
 *
 * GIVEN  a ThinkingBlock with an open phase (end === null)
 * WHEN   time runs forward (fake timers, 1s interval)
 * THEN   the seconds readout ticks up; once end is set the readout freezes
 *        (collapsed "Thought for Ns", no timer left in the DOM).
 */
import { describe, it, expect, vi, beforeAll, afterEach } from 'vitest'
import { render, screen, cleanup, act } from '@testing-library/react'
import i18n from '@/i18n'
import { seedDeepSettings } from '@/lib/deepSettings'
import ThinkingBlock from './ThinkingBlock'

afterEach(() => {
  cleanup()
  vi.useRealTimers()
  seedDeepSettings(null)
})

describe('ThinkingBlock — live Thinking-Timer (P3 Ephe-Norm)', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  it('tickt live: · 7s → · 8s nach einer weiteren Sekunde', () => {
    vi.useFakeTimers()
    const t0 = Date.now()
    render(<ThinkingBlock thinking={{ start: t0 - 7000, end: null }} />)
    expect(screen.getByTestId('thinking-timer').textContent).toContain('7s')
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(screen.getByTestId('thinking-timer').textContent).toContain('8s')
    // the live label sitting next to it stays unchanged
    expect(screen.getByText('Thinking…')).toBeTruthy()
  })

  it('friert nach Phase-Ende ein: statisches „Thought for Ns", kein Timer', () => {
    vi.useFakeTimers()
    const t0 = Date.now()
    const { rerender } = render(<ThinkingBlock thinking={{ start: t0 - 7000, end: null }} />)
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    // the phase ends (the store closes it on the first visible chunk)
    rerender(<ThinkingBlock thinking={{ start: t0 - 7000, end: t0 + 1000 }} />)
    expect(screen.queryByTestId('thinking-timer')).toBeNull()
    expect(screen.getByText('Thought for 8s')).toBeTruthy()
    // no ticking interval left: time may keep running without a re-render
    const label = screen.getByText('Thought for 8s')
    act(() => {
      vi.advanceTimersByTime(3000)
    })
    expect(screen.getByText('Thought for 8s')).toBe(label)
  })

  // I6-3: `chat.show_thinking_loader` — off removes only the loader line.
  it('ohne Loader bleibt der Block busy, nur die Zeile fehlt', () => {
    vi.useFakeTimers()
    seedDeepSettings([
      {
        key: 'chat',
        fields: [
          {
            key: 'chat.show_thinking_loader',
            type: 'bool',
            label: 'Loader der Denkphase',
            labelEn: 'Thinking loader',
            default: true,
            value: false,
          },
        ],
      },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ] as any)
    const t0 = Date.now()
    render(<ThinkingBlock thinking={{ start: t0 - 7000, end: null, text: 'zwischengedacht' }} />)
    expect(screen.queryByTestId('thinking-timer')).toBeNull()
    expect(screen.queryByText('Thinking…')).toBeNull()
    // the block itself and its reasoning text stay (a different field covers that)
    expect(screen.getByTestId('thinking-block').getAttribute('aria-busy')).toBe('true')
    expect(screen.getByText('zwischengedacht')).toBeTruthy()
  })
})
