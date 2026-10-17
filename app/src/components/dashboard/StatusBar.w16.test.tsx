import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import StatusBar from '@/components/dashboard/StatusBar'
import { getContextBudget } from '@/lib/api'
import type { ChatMessage } from '@/types'

// W16/P1: the frontend meter mirrors the backend tokenizer's exactness —
// tiktoken BPE ('tiktoken-bpe') shows a ·bpe chip, the calibrated
// 4.2 CJK fallback ('calibrated-4.2') shows none.

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
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: 'en' } }),
}))

const msgs = (n: number): ChatMessage[] => [
  { id: 'u-1', role: 'user', content: 'x'.repeat(n), timestamp: 1 },
]

const baseBudget = {
  message_count: 1,
  char_count: 4200,
  estimated_tokens: 1000,
  window_tokens: 8192,
  percent: 12.2,
  compaction_threshold: 28,
  compaction_active: false,
}

describe('StatusBar W16 — Tokenizer-Exaktheit im Meter', () => {
  it('zeigt den ·bpe-Chip, wenn das Backend mit tiktoken zählt', async () => {
    vi.mocked(getContextBudget).mockResolvedValueOnce({
      ...baseBudget,
      tokenizer: 'tiktoken-bpe',
    } as never)
    render(<StatusBar messages={msgs(4200)} />)
    expect(await screen.findByTestId('statusbar-tokenizer-chip')).toBeTruthy()
  })

  it('zeigt keinen Chip beim kalibrierten Fallback (ehrliche Schätzung)', async () => {
    vi.mocked(getContextBudget).mockResolvedValueOnce({
      ...baseBudget,
      tokenizer: 'calibrated-4.2',
    } as never)
    render(<StatusBar messages={msgs(4200)} />)
    await screen.findByText(/12[.,]?2/)
    expect(screen.queryByTestId('statusbar-tokenizer-chip')).toBeNull()
  })
})
