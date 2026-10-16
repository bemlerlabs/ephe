import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import StatusBar from '@/components/dashboard/StatusBar'
import { getContextBudget } from '@/lib/api'
import type { ChatMessage } from '@/types'

// W14/P0-1: the budget response carries the active window — the meter has to
// follow it (262k-DGX) instead of staying on the hard frontend default 8192.
vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>()
  return {
    ...actual,
    getContextBudget: vi.fn(async () => ({}) as never),
  }
})

vi.mock('@/store/chatStore', () => ({
  useChatStore: (sel: (st: { sessions: unknown[] }) => unknown) =>
    sel({ sessions: [{ id: 'a', messages: [] }] }),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => {
      const map: Record<string, string> = {
        'statusBar.breakdownHint': 'Token breakdown',
        'statusBar.ttftHint': 'time to first token',
        'statusBar.contextFree': 'free',
        'statusBar.contextFreeOf': '{{free}} free of {{window}}',
      }
      const pattern = map[key] ?? key
      if (!opts) return pattern
      return pattern
        .replace('{{free}}', String(opts.free ?? ''))
        .replace('{{window}}', String(opts.window ?? ''))
    },
    i18n: { language: 'en' },
  }),
}))

const msgs = (n: number): ChatMessage[] => [
  { id: 'u-1', role: 'user', content: 'x'.repeat(n), timestamp: 1 },
]

describe('StatusBar W14 — dynamisches Fenster + TTFT', () => {
  it('P0-1: das Budget-Fenster schlaegt den Frontend-Default (262144)', async () => {
    vi.mocked(getContextBudget).mockResolvedValueOnce({
      message_count: 1,
      char_count: 42000,
      estimated_tokens: 10000,
      window_tokens: 262144,
      window_source: 'engine',
      percent: 3.82,
      compaction_threshold: 28,
      compaction_active: false,
    } as never)
    render(<StatusBar messages={msgs(42000)} />)
    // 262144 - 10000 = 252144 → the "free" line tracks the real window.
    expect(await screen.findByText(/252[.,]?144/)).toBeTruthy()
  })

  it('P0-1: ohne Budget-Feld gilt der Prop, sonst der 8192er-Default', async () => {
    vi.mocked(getContextBudget).mockResolvedValueOnce({} as never)
    render(<StatusBar messages={msgs(4200)} windowTokens={16384} />)
    // 16384 - 1000 = 15384
    expect(await screen.findByText(/15[.,]?384/)).toBeTruthy()
  })

  it('P1-7: TTFT-Chip zeigt die Zeit bis zum ersten Content-Chunk (W19 F5: im Popover)', () => {
    const streaming: ChatMessage[] = [
      {
        id: 'a-1',
        role: 'assistant',
        content: 'x'.repeat(4200),
        timestamp: Date.now() - 2000,
        ttftMs: 800,
        streaming: true,
      },
    ]
    render(<StatusBar messages={streaming} />)
    fireEvent.click(screen.getByTestId('statusbar-breakdown-toggle'))
    const chip = screen.getByText(/TTFT 0\.8s/)
    expect(chip.getAttribute('title')).toBe('time to first token')
  })

  it('P1-7: ohne ttftMs-Feld kein Chip (Legacy-Messages bleiben still)', () => {
    const legacy: ChatMessage[] = [
      {
        id: 'a-2',
        role: 'assistant',
        content: 'x'.repeat(4200),
        timestamp: Date.now() - 1000,
        streaming: true,
      },
    ]
    render(<StatusBar messages={legacy} />)
    fireEvent.click(screen.getByTestId('statusbar-breakdown-toggle'))
    expect(screen.queryByText(/TTFT/)).toBeNull()
  })
})
