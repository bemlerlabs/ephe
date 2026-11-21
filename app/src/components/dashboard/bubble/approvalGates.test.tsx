/**
 * Audit finding 40 at the seam the person touches: the gates of one turn, rendered.
 *
 * GIVEN  an assistant turn that opened two gates for the same tool after the other
 * WHEN   the reader answers the first one on its card
 * THEN   the first card is answered and the second is still answerable
 * AND    a second click on the answered card puts no request on the wire
 *
 * The click goes through `sendSandboxDecision`, the same guarded path the bubble's
 * buttons are wired to, so what is asserted here is the request count and not a
 * stubbed callback.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { act, render, screen, fireEvent } from '@testing-library/react'
import ApprovalGates from './approvalGates'
import { sendSandboxDecision } from '@/lib/sandboxGate'
import { useChatStore } from '@/store/chatStore'
import type { ToolCall } from '@/store/chatStore'

const { send, onUnavailable } = vi.hoisted(() => ({
  send: vi.fn(async () => ({ status: 'ok' })),
  onUnavailable: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  initReactI18next: { type: '9', init: () => Promise.resolve() },
  useTranslation: (() => ({
    t: (key: string, options?: { count?: number }) => {
      const map: Record<string, string> = {
        'chat.approvalNeeded': 'Ephe wants to run a tool',
        'chat.toolApproval.headClosed': 'Approval for this tool',
        'chat.toolApproval.once': 'Allow once',
        'chat.toolApproval.deny': 'Deny',
        'chat.toolApproval.sending': 'Sending your answer…',
        'chat.toolApproval.allowedByYou': 'Allowed — by you',
        'chat.toolApproval.deniedByYou': 'Refused — by you',
        'chat.toolApproval.expiredOutcome':
          'Nobody answered before the approval window closed. Nothing ran.',
      }
      if (key === 'chat.toolApproval.multipleWaiting') {
        return `${options?.count ?? 0} waiting`
      }
      return map[key] ?? key
    },
    i18n: { language: 'en' },
  })) as never,
}))

/** The cards in the order the gates opened, which is the order of the transcript. */
function cardAt(index: number): HTMLElement {
  const node = screen.getAllByTestId('approval-card')[index]
  if (!node) throw new Error(`no approval card at ${index}`)
  return node
}

function onceOf(card: HTMLElement) {
  return card.querySelector<HTMLButtonElement>('[data-testid="approval-once"]')
}

/** The bubble's own shape: the calls come from the store, so a write to a gate
 *  re-renders its card the way the live transcript does. */
function GateHarness() {
  const sessions = useChatStore((s) => s.sessions)
  const activeId = useChatStore((s) => s.streamSessionId ?? s.activeSessionId)
  const messages = sessions.find((sess) => sess.id === activeId)?.messages ?? []
  const assistant = [...messages].reverse().find((m) => m.role === 'assistant')
  const calls = assistant?.tool_calls ?? []
  const decide = (call: ToolCall, approved: boolean) =>
    sendSandboxDecision(
      useChatStore.getState(),
      call.approval?.token ?? '',
      approved,
      'you',
      send,
      onUnavailable,
    )
  return (
    <ApprovalGates
      calls={calls}
      onApprove={(call) => void decide(call, true)}
      onDeny={(call) => void decide(call, false)}
    />
  )
}

function renderGates() {
  return render(<GateHarness />)
}

describe('ApprovalGates (finding 40)', () => {
  beforeEach(() => {
    send.mockClear()
    onUnavailable.mockClear()
    useChatStore.setState({
      sessions: [],
      activeSessionId: null,
      streamSessionId: null,
      isTyping: false,
      pendingToolCall: null,
      currentSession: null,
      checkpoints: {},
    })
    useChatStore.getState().createSession('Gate session')
    useChatStore.getState().addMessage('user', 'render the reel')
    useChatStore.getState().startTurn()
    // The audit case: the same tool asked for twice in one turn.
    useChatStore.getState().resolveSandbox('tok-a', 'film_card', { shots: 1 })
    useChatStore.getState().resolveSandbox('tok-b', 'film_card', { shots: 2 })
  })

  it('renders every gate of the turn and says how many are waiting', () => {
    renderGates()
    expect(screen.getAllByTestId('approval-card')).toHaveLength(2)
    expect(screen.getByTestId('approval-open-count').textContent).toBe('2 waiting')
    // Only the oldest open gate announces itself; the second does not steal the ask.
    expect(screen.getAllByRole('alertdialog')).toHaveLength(1)
  })

  it('answers the first gate and leaves the second one answerable', async () => {
    renderGates()
    const first = cardAt(0)
    const second = cardAt(1)

    await act(async () => {
      fireEvent.click(onceOf(first)!)
    })

    expect(send).toHaveBeenCalledTimes(1)
    expect(send).toHaveBeenCalledWith('tok-a', true)
    // The first card is inert: no action row left, and it names the hand that closed it.
    expect(onceOf(first)).toBeNull()
    expect(first.querySelector('[data-testid="approval-deny"]')).toBeNull()
    expect(first.querySelector('[data-testid="approval-outcome"]')?.textContent).toBe(
      'Allowed — by you',
    )
    // The gate that was behind it is still a question the reader can answer.
    const secondOnce = onceOf(second)
    expect(secondOnce).not.toBeNull()
    expect(secondOnce?.disabled).toBe(false)

    await act(async () => {
      fireEvent.click(secondOnce!)
    })
    expect(send).toHaveBeenCalledTimes(2)
    expect(send).toHaveBeenLastCalledWith('tok-b', true)
    expect(useChatStore.getState().sandboxGateOpen('tok-a')).toBe(false)
    expect(useChatStore.getState().sandboxGateOpen('tok-b')).toBe(false)
  })

  it('issues no request for a token that is already spent', async () => {
    renderGates()
    const first = cardAt(0)
    const once = onceOf(first)!

    // Two clicks as one gesture. The button is disabled after the first, and a click
    // that reaches the handler anyway is refused by the gate before the transport.
    await act(async () => {
      fireEvent.click(once)
      fireEvent.click(once)
    })
    expect(send).toHaveBeenCalledTimes(1)

    // Nothing is left to press, and the guarded path itself refuses the token again.
    expect(onceOf(first)).toBeNull()
    await act(async () => {
      await sendSandboxDecision(useChatStore.getState(), 'tok-a', true, 'you', send, onUnavailable)
    })
    expect(send).toHaveBeenCalledTimes(1)
    expect(onUnavailable).not.toHaveBeenCalled()
  })

  it('shows an expiry as an expiry and names no hand', () => {
    useChatStore.getState().markSandboxExpired('tok-a')
    renderGates()
    const first = cardAt(0)
    const second = cardAt(1)
    expect(onceOf(first)).toBeNull()
    expect(first.querySelector('[data-testid="approval-outcome"]')?.textContent).toBe(
      'Nobody answered before the approval window closed. Nothing ran.',
    )
    expect(first.textContent).not.toMatch(/by you|by the companion/)
    // One gate left open: the count line is for a queue, not for a single ask.
    expect(screen.queryByTestId('approval-open-count')).toBeNull()
    expect(onceOf(second)?.disabled).toBe(false)
  })
})
