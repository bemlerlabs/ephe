/**
 * F1: the status row has to say what a number is measured against.
 *
 * The row printed "2,242 free" beside a meter at 72% and never named the window —
 * a fact the component already holds: the window from `/api/context/budget`.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, cleanup, fireEvent } from '@testing-library/react'
import StatusBar from '@/components/dashboard/StatusBar'
import { getContextBudget } from '@/lib/api'
import type { ChatMessage } from '@/types'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, getContextBudget: vi.fn(async () => ({}) as never) }
})

const state = vi.hoisted(() => ({
  enginePricing: null as { in_per_m?: number; out_per_m?: number } | null,
  usageTotals: { in: 5000, out: 950, cached: 0 },
  lastTurnUsage: { in: 5000, out: 950, cached: 0 },
}))

vi.mock('@/store/chatStore', () => ({
  useChatStore: (sel: (st: Record<string, unknown>) => unknown) =>
    sel({
      sessions: [],
      lastTurnUsage: state.lastTurnUsage,
      currentSession: { usageTotals: state.usageTotals },
      enginePricing: state.enginePricing,
    }),
}))

const STRINGS: Record<string, string> = {
  'statusBar.contextFree': 'free',
  'statusBar.contextFreeOf': '{{free}} free of {{window}}',
  'statusBar.storage': '{{count}} tasks · ~{{mb}} MB',
  'statusBar.storageHint': 'browser cache — {{count}} tasks',
  'statusBar.remainingPercent': '{{percent}}% free',
  'statusBar.detailsTitle': 'Usage and storage',
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const pattern = STRINGS[key]
      if (!pattern) return key
      return pattern
        .replace('{{free}}', String(opts?.free ?? ''))
        .replace('{{window}}', String(opts?.window ?? ''))
        .replace('{{count}}', String(opts?.count ?? ''))
        .replace('{{mb}}', String(opts?.mb ?? ''))
        .replace('{{percent}}', String(opts?.percent ?? ''))
    },
    i18n: { language: 'en' },
  }),
}))

const messages = (): ChatMessage[] => [
  { id: 'u-1', role: 'user', content: 'x'.repeat(420), timestamp: Date.now() },
]

const BUDGET = {
  message_count: 12,
  char_count: 25_000,
  estimated_tokens: 5950,
  window_tokens: 8192,
  window_source: 'legacy',
  tokenizer: 'calibrated-4.2',
  percent: 73,
  compaction_threshold: 0.75,
  compaction_active: false,
}

beforeEach(() => {
  cleanup()
  state.enginePricing = null
  vi.mocked(getContextBudget).mockResolvedValue(BUDGET as never)
})

describe('the free figure', () => {
  it('carries the window it is counted against', async () => {
    render(<StatusBar messages={messages()} />)
    fireEvent.click(screen.getByTestId('agent-status-pill'))
    await waitFor(() => expect(screen.getByText('2,242 free of 8,192')).toBeTruthy())
    // The row states the complement in percent, from the same reading.
    expect(screen.getByTestId('statusbar-percent').textContent).toBe('27% free')
  })

  it('stays a bare remainder when no window is known', async () => {
    vi.mocked(getContextBudget).mockResolvedValue({} as never)
    render(<StatusBar messages={messages()} />)
    fireEvent.click(screen.getByTestId('agent-status-pill'))
    const details = await screen.findByTestId('status-details')
    expect(details.textContent).toContain('free')
    expect(details.textContent).not.toContain('free of')
  })
})

describe('the cost of a run whose engine carries no price', () => {
  // Owner decision 2026-11-15: the row states no missing-price claim. A quiet cost
  // chip is the absence; the agent-status panel names the missing setting.
  it('shows neither a cost figure nor a missing-price chip', async () => {
    render(<StatusBar messages={messages()} />)
    await screen.findByTestId('statusbar-percent')
    expect(screen.queryByTestId('statusbar-cost')).toBeNull()
    expect(screen.queryByTestId('statusbar-no-pricing')).toBeNull()
  })

  it('shows the cost figure as soon as the engine carries a price', async () => {
    state.enginePricing = { in_per_m: 0.2, out_per_m: 0.8 }
    render(<StatusBar messages={messages()} />)
    await waitFor(() => expect(screen.getByTestId('statusbar-cost')).toBeTruthy())
    expect(screen.queryByTestId('statusbar-no-pricing')).toBeNull()
  })
})
