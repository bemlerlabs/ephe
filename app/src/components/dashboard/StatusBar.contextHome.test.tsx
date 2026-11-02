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
    // No token figure is printed in the control any more — it is only the opener.
    expect(toggle.textContent).not.toMatch(/tok/)
    expect(toggle.textContent).not.toMatch(/\d/)
  })

  it('the row percent and the compact chip are the phone home, gated below the composer', () => {
    render(<StatusBar messages={messages} />)
    const percent = screen.getByTestId('statusbar-percent')
    const chip = screen.getByTestId('statusbar-tok-chip')
    expect(percent.className).toContain('md:hidden')
    expect(chip.className).toContain('md:hidden')
    // The figure is still there for the width that needs it (jsdom keeps the text).
    expect(percent.textContent).toContain('12%')
    expect(chip.textContent).toMatch(/\d[\d,.]* tok/)
  })

  it('the composer meter hides exactly where the row figures appear — complementary', () => {
    const composer = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), 'chat', 'ComposerContextMeter.tsx'),
      'utf8',
    )
    // The composer prints the number from md up and steps out below it; this row prints
    // its figures only below md. Read together, the two cover every width once.
    expect(composer).toContain('max-md:hidden')
    const source = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), 'StatusBar.tsx'),
      'utf8',
    )
    expect(source).toContain('md:hidden')
  })
})
