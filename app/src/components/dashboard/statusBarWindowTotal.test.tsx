/**
 * F1: the status row has to say what a number is measured against.
 *
 * The row printed "2,242 free" beside a meter at 72% and never named the window, and
 * the cost chip went quiet when the engine carries no price — which reads the same as
 * a session that cost nothing. Both are facts the component already holds: the window
 * from `/api/context/budget`, the pricing state from the store.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, cleanup } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
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
  'statusBar.noPricing': 'pricing not set',
  'statusBar.noPricingTitle': 'needs pricing in engine.json',
  'statusBar.storage': '{{count}} tasks · ~{{mb}} MB',
  'statusBar.storageHint': 'browser cache — {{count}} tasks',
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
    await waitFor(() => expect(screen.getByText('2,242 free of 8,192')).toBeTruthy())
  })

  it('stays a bare remainder when no window is known', async () => {
    vi.mocked(getContextBudget).mockResolvedValue({} as never)
    render(<StatusBar messages={messages()} />)
    await waitFor(() => expect(screen.getByTestId('status-bar').textContent).toContain('free'))
    expect(screen.getByTestId('status-bar').textContent).not.toContain('free of')
  })
})

describe('the cost of a run whose engine carries no price', () => {
  it('says the price is missing instead of showing nothing', async () => {
    render(<StatusBar messages={messages()} />)
    const chip = await screen.findByTestId('statusbar-no-pricing')
    expect(chip.textContent).toBe('pricing not set')
    expect(chip.textContent).not.toContain('file')
    expect(chip.getAttribute('title')).toContain('engine.json')
    expect(screen.queryByTestId('statusbar-cost')).toBeNull()
  })

  it('gives the chip back as soon as the engine carries a price', async () => {
    state.enginePricing = { in_per_m: 0.2, out_per_m: 0.8 }
    render(<StatusBar messages={messages()} />)
    await waitFor(() => expect(screen.getByTestId('statusbar-cost')).toBeTruthy())
    expect(screen.queryByTestId('statusbar-no-pricing')).toBeNull()
  })
})

describe('the shipped copy of the missing-price chip', () => {
  it('names the setting, not a file, in both locales', () => {
    const en = JSON.parse(readFileSync(join(process.cwd(), 'src/locales/en.json'), 'utf8'))
    const de = JSON.parse(readFileSync(join(process.cwd(), 'src/locales/de.json'), 'utf8'))
    expect(en.statusBar.noPricing).toBe('pricing not set')
    expect(de.statusBar.noPricing).toBe('Preis nicht gesetzt') // language-gate: ignore — the German product string, asserted as shipped
    expect(en.statusBar.noPricing).not.toMatch(/file/i)
  })
})
