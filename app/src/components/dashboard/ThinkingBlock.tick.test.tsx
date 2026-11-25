/**
 * P3: the thinking phase ticks live (the locale's word, then the seconds).
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

describe('ThinkingBlock: the live thinking timer (P3 Ephe norm)', () => {
  beforeAll(async () => {
    await i18n.changeLanguage('en')
  })

  it('ticks live: from 7s to 8s after one more second', () => {
    vi.useFakeTimers()
    const t0 = Date.now()
    render(<ThinkingBlock thinking={{ start: t0 - 7000, end: null }} />)
    // The word belongs to the locale bundle, so this file never quotes it: it pins
    // that the line beside the timer does not move while the seconds run.
    const statusText = screen.getByTestId('thinking-status').textContent
    expect(statusText).toBeTruthy()
    expect(screen.getByTestId('thinking-timer').textContent).toContain('7s')
    act(() => {
      vi.advanceTimersByTime(1000)
    })
    expect(screen.getByTestId('thinking-timer').textContent).toContain('8s')
    // the live label sitting next to it stays unchanged
    expect(screen.getByTestId('thinking-status').textContent).toBe(statusText)
  })

  it('freezes after the phase ends: a static Thought for Ns with no timer', () => {
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
  it('without the loader the block stays busy and only the line is gone', () => {
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
    expect(screen.queryByTestId('thinking-status')).toBeNull()
    expect(screen.queryByTestId('thinking-mark')).toBeNull()
    // the block itself and its reasoning text stay (a different field covers that)
    expect(screen.getByTestId('thinking-block').getAttribute('aria-busy')).toBe('true')
    expect(screen.getByText('zwischengedacht')).toBeTruthy()
  })
})
