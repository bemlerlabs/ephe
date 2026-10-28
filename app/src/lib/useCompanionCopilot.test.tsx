/**
 * QD-005 — the live loop between the store and the countdown.
 *
 * The classifier is proven pure in `companionCopilot.test.ts`; this file pins
 * the wiring: which store shape starts a countdown, that the act happens only
 * after the full 2500 ms, that Escape and Cancel stop it, and that every
 * executed act leaves a receipt. Nothing here talks to the engine — the
 * endpoint mocks record what the co-pilot would have sent.
 *
 * QD-005B adds the two precision edges: a cancel belongs to the token it was
 * counting for (so a re-render cannot resurrect it, and a fresh token is served
 * again), and the repair pointer has to land somewhere real.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook } from '@testing-library/react'

const { approveSandbox, answerAsk, markSetupIntent, storeApprovals, state } = vi.hoisted(() => ({
  approveSandbox: vi.fn(async () => ({ status: 'ok' })),
  answerAsk: vi.fn(async () => ({ status: 'ok' as const })),
  markSetupIntent: vi.fn(),
  storeApprovals: {
    approveSandbox: vi.fn(),
    markAskAnswered: vi.fn(),
    compactSession: vi.fn(() => ({ changed: false })),
  },
  state: { currentSession: null as unknown },
}))
vi.mock('@/lib/api/endpoints', () => ({ approveSandbox, answerAsk }))
vi.mock('@/lib/setupGate', () => ({ markSetupIntent }))

vi.mock('@/store/chatStore', () => ({
  useChatStore: (selector: (s: unknown) => unknown) => selector(state),
}))

import { useChatStore } from '@/store/chatStore'
import { seedDeepSettings } from '@/lib/deepSettings'
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
Element.prototype.scrollIntoView = vi.fn() as unknown as typeof Element.prototype.scrollIntoView
const recordPreview = (event: Event) => {
  const detail = (event as CustomEvent<{ tab?: string }>).detail ?? {}
  seenEvents.push({ type: event.type, tab: detail.tab })
}

beforeEach(() => {
  vi.useFakeTimers()
  approveSandbox.mockClear()
  answerAsk.mockClear()
  markSetupIntent.mockClear()
  storeApprovals.approveSandbox.mockClear()
  storeApprovals.markAskAnswered.mockClear()
  storeApprovals.compactSession.mockClear()
  state.currentSession = null
  seenEvents = []
  window.location.hash = ''
  window.addEventListener('ephe:preview-open', recordPreview)
})

afterEach(() => {
  vi.useRealTimers()
  seedDeepSettings(null)
  window.removeEventListener('ephe:preview-open', recordPreview)
})

describe('useCompanionCopilot — the loop', () => {
  it('a safe waiting check counts down and approves after the full 2500 ms', async () => {
    state.currentSession = sessionWith([
      assistant({ id: 't1', name: 'run_shell', args: { command: 'pytest' }, status: 'waiting', description: 'token-1' }),
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

  it('acts at once when the user set the countdown to 0 s', async () => {
    seedDeepSettings([
      {
        key: 'appearance',
        fields: [
          {
            key: 'appearance.companion_countdown_seconds',
            type: 'number',
            value: 0,
            default: 2.5,
            min: 0,
            max: 10,
            step: 0.5,
            label: 'countdown',
            labelEn: 'countdown',
          },
        ],
      },
    ])
    state.currentSession = sessionWith([
      assistant({ id: 't1', name: 'run_shell', args: { command: 'pytest' }, status: 'waiting', description: 'token-0s' }),
    ])
    const { result } = renderHook(() => useCompanionCopilot(hookArgs()))
    expect(result.current.finding?.verdict).toBe('auto_act')
    // The proof is the zero-length advance: a 2500 ms countdown would not fire here.
    await vi.advanceTimersByTimeAsync(0)
    expect(approveSandbox).toHaveBeenCalledWith('token-0s', true, false)
  })

  it('a risky command never starts a countdown and never approves', () => {
    state.currentSession = sessionWith([
      assistant({ id: 't1', name: 'run_shell', args: { command: 'rm -rf .' }, status: 'waiting', description: 'token-1' }),
    ])
    const { result } = renderHook(() => useCompanionCopilot(hookArgs()))
    expect(result.current.finding?.verdict).toBe('warn_only')
    expect(result.current.countdownRemaining).toBeNull()
    vi.advanceTimersByTime(3000)
    expect(approveSandbox).not.toHaveBeenCalled()
  })

  it('Cancel stops the act and leaves no receipt', () => {
    state.currentSession = sessionWith([
      assistant({ id: 't1', name: 'run_shell', args: { command: 'pytest' }, status: 'waiting', description: 'token-1' }),
    ])
    const { result } = renderHook(() => useCompanionCopilot(hookArgs()))
    act(() => result.current.cancel())
    vi.advanceTimersByTime(3000)
    expect(approveSandbox).not.toHaveBeenCalled()
    expect(result.current.receipts).toHaveLength(0)
  })

  it('Escape stops the countdown like Cancel does', () => {
    state.currentSession = sessionWith([
      assistant({ id: 't1', name: 'run_shell', args: { command: 'pytest' }, status: 'waiting', description: 'token-1' }),
    ])
    renderHook(() => useCompanionCopilot(hookArgs()))
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    vi.advanceTimersByTime(3000)
    expect(approveSandbox).not.toHaveBeenCalled()
  })

  it('a canceled prompt stays canceled through a re-render of the same token', () => {
    state.currentSession = sessionWith([
      assistant({ id: 't1', name: 'run_shell', args: { command: 'pytest' }, status: 'waiting', description: 'tok-1' }),
    ])
    const { rerender, result } = renderHook((props) => useCompanionCopilot(props), {
      initialProps: hookArgs(),
    })
    act(() => result.current.cancel())
    expect(result.current.countdownRemaining).toBeNull()

    rerender(hookArgs({ contextPercent: 41 }))
    expect(result.current.countdownRemaining).toBeNull()
    vi.advanceTimersByTime(3000)
    expect(approveSandbox).not.toHaveBeenCalled()
    expect(result.current.receipts).toHaveLength(0)
  })

  it('Escape is sticky too: the same token never counts down twice', () => {
    state.currentSession = sessionWith([
      assistant({ id: 't1', name: 'run_shell', args: { command: 'pytest' }, status: 'waiting', description: 'tok-1' }),
    ])
    const { rerender, result } = renderHook((props) => useCompanionCopilot(props), {
      initialProps: hookArgs(),
    })
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    rerender(hookArgs({ runState: 'waiting' }))
    expect(result.current.countdownRemaining).toBeNull()
    vi.advanceTimersByTime(3000)
    expect(approveSandbox).not.toHaveBeenCalled()
  })

  it('the same command a second time has a new token and is served again', async () => {
    state.currentSession = sessionWith([
      assistant({ id: 't1', name: 'run_shell', args: { command: 'pytest' }, status: 'waiting', description: 'tok-1' }),
    ])
    const { rerender, result } = renderHook((props) => useCompanionCopilot(props), {
      initialProps: hookArgs(),
    })
    await vi.advanceTimersByTimeAsync(2500)
    expect(approveSandbox).toHaveBeenCalledWith('tok-1', true, false)

    state.currentSession = sessionWith([
      assistant({ id: 't2', name: 'run_shell', args: { command: 'pytest' }, status: 'waiting', description: 'tok-2' }),
    ])
    rerender(hookArgs())
    expect(result.current.countdownRemaining).not.toBeNull()
    await vi.advanceTimersByTimeAsync(2500)
    expect(approveSandbox).toHaveBeenLastCalledWith('tok-2', true, false)
    expect(result.current.receipts).toHaveLength(2)
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
      assistant({ id: 't1', name: 'run_shell', args: { command: 'pytest' }, status: 'waiting', description: 'token-1' }),
    ])
    const perch = renderHook(() => useCompanionCopilot(hookArgs({ mode: 'perch' })))
    expect(perch.result.current.finding).toBeNull()

    const scout = renderHook(() => useCompanionCopilot(hookArgs({ mode: 'scout' })))
    expect(scout.result.current.finding?.verdict).toBe('focus')
    vi.advanceTimersByTime(3000)
    expect(approveSandbox).not.toHaveBeenCalled()
  })

  it('a repair the chat cannot show takes the user to the screen that can', () => {
    state.currentSession = sessionWith([{ id: 'm1', role: 'user', content: 'hi', timestamp: 1 }])
    const { result } = renderHook(() => useCompanionCopilot(hookArgs({ repairVisible: true })))
    expect(result.current.finding).toMatchObject({
      target: 'error_or_setup_repair',
      verdict: 'focus',
    })
    act(() => result.current.focus())
    expect(markSetupIntent).toHaveBeenCalledTimes(1)
    expect(window.location.hash).toBe('#/setup')
  })

  it('a repair card already on screen is highlighted, not re-routed', () => {
    state.currentSession = sessionWith([{ id: 'm1', role: 'user', content: 'hi', timestamp: 1 }])
    const card = document.createElement('div')
    card.dataset.testid = 'setup-repair'
    document.body.appendChild(card)
    try {
      const { result } = renderHook(() => useCompanionCopilot(hookArgs({ repairVisible: true })))
      act(() => result.current.focus())
      expect(card.dataset.copilotHighlight).toBe('true')
      expect(markSetupIntent).not.toHaveBeenCalled()
    } finally {
      card.remove()
    }
  })

  it('the dormant surface leaves the live surface pointer alone', () => {
    state.currentSession = sessionWith([
      assistant({ id: 't1', name: 'run_shell', args: { command: 'pytest' }, status: 'waiting', description: 'tok-1' }),
    ])
    const dialog = document.createElement('div')
    dialog.setAttribute('role', 'alertdialog')
    document.body.appendChild(dialog)
    try {
      const live = renderHook(() => useCompanionCopilot(hookArgs({ mode: 'scout' })))
      expect(dialog.dataset.copilotHighlight).toBe('true')
      // The other companion surface is mounted here too and crawls nothing.
      renderHook(() => useCompanionCopilot(hookArgs({ enabled: false })))
      expect(dialog.dataset.copilotHighlight).toBe('true')
      live.unmount()
    } finally {
      dialog.remove()
    }
  })
})
