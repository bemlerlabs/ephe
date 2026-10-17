/**
 * WS3-22 — the status row's finish pass.
 *
 * Four defects the row carried into this pass, all of them read off the rendered
 * surface rather than a change list:
 *
 *  1. The prompt-cache chip was the only figure drawn with a literal zap emoji — a
 *     glyph whose size and baseline come from the platform — while every other icon in
 *     the row is a lucide mark at `h-3 w-3`. The row also spends a zap on the token
 *     count and on the rate, so the same mark answered three questions.
 *  2. The occupancy bar had no role and no name. The composer ring got `role="img"`
 *     in F2; the row meter stayed a bare div whose number lived in a `title` — which
 *     a touch device never renders and a screen reader never reaches.
 *  3. The percent figure and the compaction marker had no handle at all, so a visual
 *     baseline has to mask the meter's whole parent to keep them out of the diff.
 *  4. Both popover openers toggle a disclosure and exposed no state; `aria-expanded`
 *     stayed absent while the row's one dialog opened and closed underneath.
 *
 * The fifth assertion is a source contract, the shape `contextDisclosure.test.tsx`
 * already uses: the meter's name has to come from the ring's own helper, because a
 * second copy of the sentence would drift from the first without a test noticing.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import StatusBar from '@/components/dashboard/StatusBar'
import { getContextBudget } from '@/lib/api'
import type { ChatMessage } from '@/types'

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return { ...actual, getContextBudget: vi.fn(async () => ({}) as never) }
})

// A measured cache share needs a last turn with a positive prompt count and cached
// tokens; a measured cost needs usage totals next to engine pricing.
const state = vi.hoisted(() => ({
  cache: { in: 1000, out: 100, cached: 500 },
}))

vi.mock('@/store/chatStore', () => ({
  useChatStore: (sel: (st: Record<string, unknown>) => unknown) =>
    sel({
      sessions: [],
      lastTurnUsage: { ...state.cache },
      currentSession: { usageTotals: { in: 1000, out: 100, cached: 500 } },
      enginePricing: { in_per_m: 0.2, out_per_m: 0.8 },
    }),
}))

const STRINGS: Record<string, string> = {
  'chat.contextRing': 'Context used: {{percent}}%',
  'statusBar.contextFree': 'free',
  'statusBar.contextFreeOf': '{{free}} free of {{window}}',
  'statusBar.cacheTitle': 'Prompt cache: {{percent}}% served from cache',
  'statusBar.compactionActive': 'compaction active',
  'statusBar.breakdownHint': 'Token breakdown',
  'statusBar.contextMeterHint': 'Context window usage',
  'statusBar.windowAssumed': 'Window {{window}} · assumed',
}

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const pattern = STRINGS[key]
      if (!pattern) return key
      let out = pattern
      for (const [k, v] of Object.entries(opts ?? {})) out = out.replace(`{{${k}}}`, String(v))
      return out
    },
    i18n: { language: 'en' },
  }),
}))

const BUDGET = {
  message_count: 3,
  char_count: 16540,
  estimated_tokens: 1000,
  window_tokens: 8192,
  window_source: 'legacy',
  percent: 12,
  compaction_threshold: 0.75,
  compaction_active: false,
}

const messages = (): ChatMessage[] => [
  { id: 'u-1', role: 'user', content: 'x'.repeat(420), timestamp: 1 },
]

beforeEach(() => {
  cleanup()
  vi.mocked(getContextBudget).mockResolvedValue(BUDGET as never)
})

describe('status row finish', () => {
  it('draws the cache share with the row icon, not with a platform emoji', async () => {
    render(<StatusBar messages={messages()} />)
    const chip = await screen.findByTestId('statusbar-cache')
    expect(chip.textContent).not.toContain('⚡')
    expect(chip.textContent).toContain('50%')
    expect(chip.querySelector('svg')).toBeTruthy()
  })

  it('names the cache chip with the sentence its tooltip already carries', async () => {
    render(<StatusBar messages={messages()} />)
    const chip = await screen.findByTestId('statusbar-cache')
    expect(chip.getAttribute('aria-label')).toBe('Prompt cache: 50% served from cache')
  })

  it('gives the occupancy bar the same sentence the ring uses as its name', async () => {
    render(<StatusBar messages={messages()} />)
    const meter = await screen.findByTestId('statusbar-meter')
    expect(meter.getAttribute('role')).toBe('img')
    expect(meter.getAttribute('aria-label')).toBe('Context used: 12%')
    expect(meter.getAttribute('title')).toBe('Window 8,192 · assumed')
  })

  it('names the meter with the ring helper, not with a second copy of the sentence', () => {
    const source = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), 'StatusBar.tsx'),
      'utf8',
    )
    expect(source).toMatch(/aria-label=\{contextRingLabel\(t, effectivePercent/)
    expect(source).toMatch(/from '\.\/chat\/contextRing'/)
  })

  it('gives the percent figure its own handle, separate from the meter', async () => {
    render(<StatusBar messages={messages()} />)
    const percent = await screen.findByTestId('statusbar-percent')
    expect(percent.textContent).toContain('12%')
    expect(screen.getByTestId('statusbar-meter')).not.toBe(percent)
  })

  it('keeps the compaction marker off until compaction runs, then explains it', async () => {
    render(<StatusBar messages={messages()} />)
    await screen.findByTestId('statusbar-meter')
    expect(screen.queryByTestId('statusbar-compaction-marker')).toBeNull()

    cleanup()
    vi.mocked(getContextBudget).mockResolvedValue({
      ...BUDGET,
      compaction_active: true,
    } as never)
    render(<StatusBar messages={messages()} />)
    const marker = await screen.findByTestId('statusbar-compaction-marker')
    expect(marker.getAttribute('title')).toBe('compaction active')
  })

  it('reports the popover’s open state on both openers', async () => {
    render(<StatusBar messages={messages()} />)
    const toggle = await screen.findByTestId('statusbar-breakdown-toggle')
    const mobileChip = screen.getByTestId('statusbar-tok-chip')
    expect(toggle.getAttribute('aria-expanded')).toBe('false')
    expect(toggle.getAttribute('aria-haspopup')).toBe('dialog')

    fireEvent.click(toggle)
    expect(toggle.getAttribute('aria-expanded')).toBe('true')
    expect(mobileChip.getAttribute('aria-expanded')).toBe('true')
  })
})
