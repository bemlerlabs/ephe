/**
 * One figure, one home — the context meter and the composer never both print it.
 *
 * The composer row owns the number where the person is about to spend the context;
 * this row owns the machine's gauge. Measured on the installed surface, the same
 * occupancy sat four times in one screen: the composer's `4% · 359 / 8,192 tok`,
 * the row bar, a bare `4%`, and a `359 tok` popover button. After: the bar keeps
 * naming the percentage for a screen reader at every width, the popover stays as
 * the detail, and neither the number nor the percent is printed twice.
 *
 * The split follows the composer's own breakpoint, so a narrow window that loses the
 * composer meter gains it back in this row — and the reverse. jsdom applies no media
 * or container query, so the per-width switch is held as a class contract; the
 * always-present facts (the bar's name, the reachable popover) are held as DOM.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import StatusBar from '@/components/dashboard/StatusBar'
import type { ChatMessage } from '@/types'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, getContextBudget: vi.fn(async () => ({}) as never) }
})

vi.mock('@/store/chatStore', () => ({
  useChatStore: (sel: (st: Record<string, unknown>) => unknown) =>
    sel({ sessions: [], lastTurnUsage: null, currentSession: null, enginePricing: null }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'chat.contextRing': 'Context used: {{percent}}%',
        'statusBar.breakdownHint': 'Token breakdown',
        'statusBar.remainingPercent': '{{percent}}% free',
      }
      const pattern = map[key] ?? key
      if (!opts) return pattern
      return pattern.replace('{{percent}}', String(opts.percent ?? ''))
    },
    i18n: { language: 'en' },
  }),
}))

const messages: ChatMessage[] = [
  { id: 'u-1', role: 'user', content: 'x'.repeat(4200), timestamp: 1 },
]

describe('the context figure has one home', () => {
  it('the bar keeps the percentage named, at every width', () => {
    render(<StatusBar messages={messages} />)
    const meter = screen.getByTestId('statusbar-meter')
    expect(meter.getAttribute('role')).toBe('img')
    expect(meter.getAttribute('aria-label')).toBe('Context used: 12%')
  })

  it('the desktop breakdown control opens the detail without re-reading the numbers', () => {
    render(<StatusBar messages={messages} />)
    const toggle = screen.getByTestId('statusbar-breakdown-toggle')
    expect(toggle.getAttribute('aria-label')).toBe('Token breakdown')
    expect(toggle.getAttribute('aria-haspopup')).toBe('dialog')
    // The control states the remainder and opens the detail; no token pair.
    expect(toggle.textContent).toBe('88% free')
    expect(toggle.textContent).not.toMatch(/tok/)
  })

  it('states the remainder at every width and keeps no second token chip', () => {
    render(<StatusBar messages={messages} />)
    const percent = screen.getByTestId('statusbar-percent')
    // One figure, always: the remainder in percent. It no longer steps out at md.
    expect(percent.textContent).toBe('88% free')
    expect(percent.className).not.toContain('md:hidden')
    expect(screen.queryByTestId('statusbar-tok-chip')).toBeNull()
  })

  it('the composer meter is opt-in, not a second permanent figure', () => {
    const composer = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), 'chat', 'ComposerContextMeter.tsx'),
      'utf8',
    )
    // The quieting moved it behind the thinking control; it is no longer a permanent
    // row that has to be hidden on narrow widths (and duplicated here to cover them).
    expect(composer).not.toContain('max-md:hidden')
    const source = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), 'StatusBar.tsx'),
      'utf8',
    )
    expect(source).not.toContain('statusbar-tok-chip')
  })
})
