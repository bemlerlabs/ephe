/**
 * F8 — the status bar and the composer ring read one occupancy.
 *
 * QA-0.1.11 measured both on the same window and found them disagreeing: the
 * bar used the server's mirror under the server's window, the ring estimated
 * the messages under 32 768. These cases pin the resolution order and, above
 * all, that used + free always add up to the window that the percent uses.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

const getContextBudget = vi.hoisted(() => vi.fn())
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  getContextBudget,
}))

import { useContextOccupancy } from './useContextOccupancy'
import { useChatStore } from '@/store/chatStore'

const messages = [
  {
    id: 'm1',
    role: 'user',
    content: 'word '.repeat(400),
  },
] as never

beforeEach(() => {
  getContextBudget.mockReset()
  useChatStore.setState({ lastTurnUsage: null } as never)
})

describe('useContextOccupancy', () => {
  it('reads the server mirror under its own window', async () => {
    getContextBudget.mockResolvedValue({
      window_tokens: 200000,
      estimated_tokens: 124000,
      percent: 62,
      message_count: 12,
      compaction_active: false,
    })

    const { result } = renderHook(() => useContextOccupancy(messages, 32768, 's1'))
    await waitFor(() => expect(result.current.percent).toBe(62))

    expect(result.current.window).toBe(200000)
    expect(result.current.tokens).toBe(124000)
    expect(result.current.remaining).toBe(76000)
  })

  it('falls back to the offline estimate when the mirror is empty', async () => {
    getContextBudget.mockResolvedValue({
      window_tokens: 1000,
      estimated_tokens: 0,
      percent: 0,
      message_count: 0,
      compaction_active: false,
    })

    const { result } = renderHook(() => useContextOccupancy(messages, 1000, 's1'))
    await waitFor(() => expect(result.current.budget).not.toBeNull())

    // An empty mirror contributes its window but no count — the estimate fills it.
    expect(result.current.percent).toBeGreaterThan(0)
    expect(result.current.tokens).toBe(result.current.usage.tokens.total)
  })

  it('keeps used and free on the same denominator', async () => {
    useChatStore.setState({ lastTurnUsage: { in: 500, out: 500 } } as never)
    getContextBudget.mockRejectedValue(new Error('offline'))

    const { result } = renderHook(() => useContextOccupancy(messages, 2000, 's1'))
    await waitFor(() => expect(result.current.percent).toBe(50))

    expect(result.current.tokens).toBe(1000)
    expect(result.current.tokens + result.current.remaining).toBe(result.current.window)
  })
})
