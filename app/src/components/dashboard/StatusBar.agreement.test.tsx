/**
 * W3-52: the meter, the popover and the row numbers have to be one reading.
 *
 * The row (percent chip, tok chip, "N free of W") and the popover (tokens / window
 * with percent) each derived their figures on their own: the popover read
 * `budget.estimated_tokens` and `budget.window_tokens` directly, the row used the
 * effective values (mirror-live gate, `windowTokens` prop fallback). With a budget
 * whose mirror is empty, or a window that only the prop carries, the two surfaces
 * printed two different pairs for the same session.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import StatusBar from '@/components/dashboard/StatusBar'
import { getContextBudget } from '@/lib/api'
import type { ChatMessage } from '@/types'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, getContextBudget: vi.fn(async () => ({}) as never) }
})

vi.mock('@/store/chatStore', () => ({
  useChatStore: (sel: (st: Record<string, unknown>) => unknown) =>
    sel({
      sessions: [],
      lastTurnUsage: null,
      currentSession: null,
      enginePricing: null,
    }),
}))

const STRINGS: Record<string, string> = {
  'statusBar.contextFree': 'free',
  'statusBar.contextFreeOf': '{{free}} free of {{window}}',
  'statusBar.windowAssumed': 'Window {{window}} assumed',
  'statusBar.windowEngine': 'Window {{window}} from the engine',
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const pattern = STRINGS[key]
      if (!pattern) return key
      return pattern
        .replace('{{free}}', String(opts?.free ?? ''))
        .replace('{{window}}', String(opts?.window ?? ''))
    },
    i18n: { language: 'en' },
  }),
}))

const msg = (n: number): ChatMessage[] => [
  { id: 'u-1', role: 'user', content: 'x'.repeat(n), timestamp: Date.now() },
]

const openPopover = () => fireEvent.click(screen.getByTestId('statusbar-breakdown-toggle'))

beforeEach(() => {
  cleanup()
  vi.mocked(getContextBudget).mockResolvedValue({} as never)
})

describe('W3-52 — meter, popover and row numbers are one reading', () => {
  it('the popover window equals the window the free figure is counted against', async () => {
    // The prop carries the real window; the budget window is 0. The row already
    // shows the prop's 16,384 — the popover has to show the same one.
    vi.mocked(getContextBudget).mockResolvedValue({
      message_count: 5,
      estimated_tokens: 4000,
      window_tokens: 0,
      window_source: 'legacy',
      percent: 24,
      compaction_active: false,
    } as never)
    render(<StatusBar messages={msg(4200)} windowTokens={16384} />)
    await screen.findByText('12,384 free of 16,384')
    // The meter's own disclosure names the same window as the free figure.
    const meterTitle = screen.getByTestId('statusbar-meter').getAttribute('title')
    openPopover()
    const popover = screen.getByTestId('context-popover')
    expect(popover.textContent).toContain('16,384')
    expect(popover.textContent).toContain('4,000')
    // Meter title and popover source line are the same sentence about the same window.
    expect(screen.getByTestId('statusbar-window-source').textContent).toBe(meterTitle)
  })

  it('the popover token count matches the row chip while the mirror is empty', async () => {
    // message_count 0 → the mirror is not live, so the row counts the estimate
    // (420 chars → 100 tok). The popover may not print the mirror's stale 9,999.
    vi.mocked(getContextBudget).mockResolvedValue({
      message_count: 0,
      estimated_tokens: 9999,
      window_tokens: 8192,
      window_source: 'legacy',
      percent: 5,
      compaction_active: false,
    } as never)
    render(<StatusBar messages={msg(420)} />)
    const chip = await screen.findByTestId('statusbar-tok-chip')
    expect(chip.textContent).toBe('100 tok')
    openPopover()
    const popover = screen.getByTestId('context-popover')
    expect(popover.textContent).toContain('100 /')
    expect(popover.textContent).not.toContain('9,999')
  })

  it('the popover percent is the percent the row meter draws', async () => {
    vi.mocked(getContextBudget).mockResolvedValue({
      message_count: 3,
      estimated_tokens: 4135,
      window_tokens: 8192,
      window_source: 'legacy',
      percent: 48,
      compaction_active: false,
    } as never)
    render(<StatusBar messages={msg(20000)} />)
    const rowPercent = await screen.findByTestId('statusbar-percent')
    openPopover()
    const popover = screen.getByTestId('context-popover')
    expect(rowPercent.textContent).toContain('48%')
    expect(popover.textContent).toContain('48%')
  })
})
