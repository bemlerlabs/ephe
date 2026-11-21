/**
 * Poll discipline of the status-task poll (finding of the 2026-10-02 deep test).
 *
 * AgentStatusButton asked getTasks every 10s — even while its tab was hidden.
 * The guard: visible = the 10s poll runs, hidden = it stops, visible again =
 * an immediate reload and resume.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, act, cleanup } from '@testing-library/react'
import AgentStatusButton from '@/components/dashboard/AgentStatusButton'
import type { ChatMessage } from '@/types'

let calls = 0
function setHidden(v: boolean) {
  Object.defineProperty(document, 'hidden', { configurable: true, get: () => v })
}

vi.mock('@/lib/api', () => ({
  getTasks: vi.fn(async () => {
    calls++
    return [{ id: 't1', title: 'a', status: 'pending', project: null }]
  }),
  getSky: vi.fn(async () => {
    throw new Error('offline')
  }),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '3rdParty', init: vi.fn() },
  useTranslation: () => ({ t: (key: string) => key }),
}))

const IDLE: ChatMessage[] = [
  { id: 'm1', role: 'assistant', content: 'fertig', timestamp: Date.now() - 60_000 },
]

describe('AgentStatusButton — visibility-gated task poll', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    calls = 0
    setHidden(false)
    localStorage.clear()
  })
  afterEach(() => {
    cleanup()
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  it('loads at once and polls every 10s while visible', () => {
    render(<AgentStatusButton messages={IDLE} />)
    act(() => void Promise.resolve())
    expect(calls).toBe(1)
    act(() => {
      vi.advanceTimersByTime(10_000)
    })
    expect(calls).toBe(2)
  })

  it('stops the poll on a hidden tab and resumes when visible', () => {
    render(<AgentStatusButton messages={IDLE} />)
    act(() => void Promise.resolve())
    expect(calls).toBe(1)
    setHidden(true)
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    act(() => {
      vi.advanceTimersByTime(30_000)
    })
    expect(calls).toBe(1)
    setHidden(false)
    act(() => document.dispatchEvent(new Event('visibilitychange')))
    expect(calls).toBe(2)
  })
})
