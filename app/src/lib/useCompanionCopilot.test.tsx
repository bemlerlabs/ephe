/**
 * QD-005 — the live loop between the store and the countdown.
 *
 * The classifier is proven pure in `companionCopilot.test.ts`; this file pins
 * the wiring: which store shape starts a countdown, that the act happens only
 * after the full 2500 ms, that Escape and Cancel stop it, and that every
 * executed act leaves a receipt. Nothing here talks to the engine — the
 * endpoint mocks record what the co-pilot would have sent.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'

const { approveSandbox, answerAsk, storeApprovals, state } = vi.hoisted(() => ({
  approveSandbox: vi.fn(async () => ({ status: 'ok' })),
  answerAsk: vi.fn(async () => ({ status: 'ok' as const })),
  storeApprovals: {
    approveSandbox: vi.fn(),
    markAskAnswered: vi.fn(),
    compactSession: vi.fn(() => ({ changed: false })),
  },
  state: { currentSession: null as unknown },
}))
vi.mock('@/lib/api/endpoints', () => ({ approveSandbox, answerAsk }))

vi.mock('@/store/chatStore', () => ({
  useChatStore: (selector: (s: unknown) => unknown) => selector(state),
}))

import { useChatStore } from '@/store/chatStore'
import { useCompanionCopilot } from './useCompanionCopilot'

// The real store object sits behind the selector; the hook reads getState()
// only for the three actions, so patch them onto the mock store.
Object.assign(useChatStore as unknown as { getState: () => unknown }, {
  getState: () => storeApprovals,
})

interface ToolStub {
  id: string
  name: string
  args?: Record<string, unknown>
  status: string
  description?: string
}

function assistant(tool: ToolStub) {
  return {
    id: 'm1',
    role: 'assistant',
    content: '',
    timestamp: 1,
    tool_calls: [tool],
  }
}

function sessionWith(messages: unknown[]): unknown {
  return { id: 's1', title: 't', messages, createdAt: 1, updatedAt: 1 }
}

function hookArgs(overrides: Partial<Parameters<typeof useCompanionCopilot>[0]> = {}) {
  return {
    enabled: true,
    mode: 'copilot' as const,
    runState: 'working' as const,
    contextPercent: null,
    repairVisible: false,
    ...overrides,
  }
}

let seenEvents: Array<{ type: string; tab?: string }> = []
const recordPreview = (event: Event) => {
  const detail = (event as CustomEvent<{ tab?: string }>).detail ?? {}
  seenEvents.push({ type: event.type, tab: detail.tab })
}

beforeEach(() => {
  vi.useFakeTimers()
  approveSandbox.mockClear()
  answerAsk.mockClear()
  storeApprovals.approveSandbox.mockClear()
  storeApprovals.markAskAnswered.mockClear()
  storeApprovals.compactSession.mockClear()
  state.currentSession = null
  seenEvents = []
  window.addEventListener('ephe:preview-open', recordPreview)
})

afterEach(() => {
  vi.useRealTimers()
  window.removeEventListener('ephe:preview-open', recordPreview)
})

describe('useCompanionCopilot — the loop', () => {
  it('a safe waiting check counts down and approves after the full 2500 ms', async () => {
    state.currentSession = sessionWith([
      assistant({ id: 't1', name: 'execute_code', args: { command: 'pytest' }, status: 'waiting', description: 'token-1' }),
    ])
    const { result } = renderHook(() => useCompanionCopilot(hookArgs()))
    expect(result.current.finding?.verdict).toBe('auto_act')
    expect(result.current.countdownRemaining).not.toBeNull()

    vi.advanceTimersByTime(2499)
    expect(approveSandbox).not.toHaveBeenCalled()

    await vi.advanceTimersByTimeAsync(1)
    expect(approveSandbox).toHaveBeenCalledWith('token-1', true, false)
    expect(storeApprovals.approveSandbox).toHaveBeenCalledTimes(1)
    expect(result.current.receipts).toHaveLength(1)
    expect(result.current.receipts[0]!.actionKey).toBe('copilot.action.approve')
    expect(result.current.countdownRemaining).toBeNull()
  })

  it('a risky command never starts a countdown and never approves', () => {
    state.currentSession = sessionWith([
      assistant({ id: 't1', name: 'execute_code', args: { command: 'rm -rf .' }, status: 'waiting', description: 'token-1' }),
    ])
    const { result } = renderHook(() => useCompanionCopilot(hookArgs()))
    expect(result.current.finding?.verdict).toBe('warn_only')
    expect(result.current.countdownRemaining).toBeNull()
    vi.advanceTimersByTime(3000)
    expect(approveSandbox).not.toHaveBeenCalled()
  })

  it('Cancel stops the act and leaves no receipt', () => {
    state.currentSession = sessionWith([
      assistant({ id: 't1', name: 'execute_code', args: { command: 'pytest' }, status: 'waiting', description: 'token-1' }),
    ])
    const { result } = renderHook(() => useCompanionCopilot(hookArgs()))
    act(() => result.current.cancel())
    vi.advanceTimersByTime(3000)
    expect(approveSandbox).not.toHaveBeenCalled()
    expect(result.current.receipts).toHaveLength(0)
  })

  it('Escape stops the countdown like Cancel does', () => {
    state.currentSession = sessionWith([
      assistant({ id: 't1', name: 'execute_code', args: { command: 'pytest' }, status: 'waiting', description: 'token-1' }),
    ])
    renderHook(() => useCompanionCopilot(hookArgs()))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    vi.advanceTimersByTime(3000)
    expect(approveSandbox).not.toHaveBeenCalled()
  })

  it('a question with one matching recommendation answers itself', async () => {
    state.currentSession = sessionWith([
      {
        id: 'm1',
        role: 'assistant',
        content: '',
        timestamp: 1,
        ask: {
          token: 'ask-1',
          question: 'Go on?',
          options: [{ label: 'Stop' }, { label: 'Continue' }],
          recommendation: 'Continue',
          status: 'waiting',
        },
      },
    ])
    const { result } = renderHook(() => useCompanionCopilot(hookArgs({ runState: 'waiting' })))
    expect(result.current.finding?.verdict).toBe('auto_act')
    await vi.advanceTimersByTimeAsync(2500)
    expect(answerAsk).toHaveBeenCalledWith('ask-1', 'Continue')
    expect(storeApprovals.markAskAnswered).toHaveBeenCalledWith('ask-1', 'Continue')
  })

  it('a full context after the turn compacts once per session', async () => {
    state.currentSession = sessionWith([{ id: 'm1', role: 'user', content: 'hi', timestamp: 1 }])
    const { result } = renderHook(() =>
      useCompanionCopilot(hookArgs({ runState: 'done', contextPercent: 93 })),
    )
    expect(result.current.finding?.target).toBe('context_compact')
    await vi.advanceTimersByTimeAsync(2500)
    expect(storeApprovals.compactSession).toHaveBeenCalledTimes(1)

    // The same session must not fire again once the once-flag is set.
    vi.advanceTimersByTime(3000)
    expect(storeApprovals.compactSession).toHaveBeenCalledTimes(1)
  })

  it('a finished turn with fresh edits opens the review pane', async () => {
    state.currentSession = sessionWith([
      assistant({
        id: 't1',
        name: 'write_file',
        args: { path: 'a.txt' },
        status: 'completed',
        description: 'ok',
      }),
    ])
    const { rerender } = renderHook((props) => useCompanionCopilot(props), {
      initialProps: hookArgs({ runState: 'working' }),
    })
    rerender(hookArgs({ runState: 'done' }))
    await vi.advanceTimersByTimeAsync(2500)
    expect(seenEvents).toContainEqual({ type: 'ephe:preview-open', tab: 'git' })
  })

  it('perch crawls nothing, scout points without acting', () => {
    state.currentSession = sessionWith([
      assistant({ id: 't1', name: 'execute_code', args: { command: 'pytest' }, status: 'waiting', description: 'token-1' }),
    ])
    const perch = renderHook(() => useCompanionCopilot(hookArgs({ mode: 'perch' })))
    expect(perch.result.current.finding).toBeNull()

    const scout = renderHook(() => useCompanionCopilot(hookArgs({ mode: 'scout' })))
    expect(scout.result.current.finding?.verdict).toBe('focus')
    vi.advanceTimersByTime(3000)
    expect(approveSandbox).not.toHaveBeenCalled()
  })
})
