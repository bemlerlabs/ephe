import { readFileSync } from 'node:fs'
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatusBar from '@/components/dashboard/StatusBar'
import type { ChatMessage } from '@/types'

// QD-015 V1: the status row is one line at every width. The collision came from
// `max-lg:flex-wrap` — a wrapped second line painted while the right panel
// squeezed the column — and from two unbounded `shrink-0` figures that could not
// give way. These assertions pin the hierarchy that replaced it.

vi.mock('@/store/chatStore', () => ({
  useChatStore: (
    sel: (st: {
      lastTurnUsage: unknown
      currentSession: unknown
      enginePricing: unknown
    }) => unknown,
  ) =>
    sel({
      lastTurnUsage: { in: 120, out: 30 },
      currentSession: { usageTotals: { in: 900, out: 300 } },
      enginePricing: null,
    }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'statusBar.contextFreeOf': '{{free}} free of {{window}}',
        'statusBar.contextFree': 'free',
        'statusBar.noPricing': 'pricing not set',
        'statusBar.remainingPercent': '{{percent}}% free',
      }
      const pattern = map[key] ?? key
      if (!opts) return pattern
      return pattern
        .replace('{{free}}', String(opts.free ?? ''))
        .replace('{{window}}', String(opts.window ?? ''))
        .replace('{{percent}}', String(opts.percent ?? ''))
    },
    i18n: { language: 'en' },
  }),
}))

const messages: ChatMessage[] = [{ id: 'u-1', role: 'user', content: 'hello', timestamp: 1 }]

describe('StatusBar QD-015 V1 — width hierarchy', () => {
  it('keeps the row on one line instead of wrapping under a squeeze', () => {
    render(<StatusBar messages={messages} windowTokens={16384} />)
    const row = screen.getByTestId('status-bar')
    expect(row.className).toContain('overflow-hidden')
    expect(row.className).toContain('whitespace-nowrap')
    expect(row.className).not.toContain('flex-wrap')
  })

  it('states one remainder figure instead of a free-of pair the row must shrink', () => {
    render(<StatusBar messages={messages} windowTokens={16384} />)
    const percent = screen.getByTestId('statusbar-percent')
    expect(percent.textContent).toMatch(/free$/)
    expect(screen.queryByText(/free of/)).toBeNull()
    // The row still never wraps; the percent is `shrink-0` and the meter yields.
    expect(screen.getByTestId('statusbar-meter').parentElement?.className).toContain('flex-1')
  })

  it('moves "pricing not set" behind lg with a truncation ceiling', () => {
    render(<StatusBar messages={messages} windowTokens={16384} />)
    const chip = screen.getByTestId('statusbar-no-pricing')
    expect(chip.className).toContain('hidden')
    expect(chip.className).toContain('lg:inline-block')
    expect(chip.className).toContain('truncate')
    expect(chip.className).toMatch(/max-w-/)
  })

  it('gives the transcript a top buffer under the fixed header', () => {
    const source = readFileSync('src/components/dashboard/chat/index.tsx', 'utf8')
    expect(source).toContain('overflow-y-auto px-4 pt-4')
  })
})
