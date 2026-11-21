/**
 * Audit finding 40 — one gate, one token, one answer.
 *
 * GIVEN  an assistant turn that opens two approval gates after the other
 * WHEN   the store closes one of them by its token
 * THEN   that gate closes and the other one keeps waiting
 * AND    an expiry records no decision, and a closed gate is not open a second time
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from './chatStore'

/** Last assistant message of the active session (the turn under test) */
function active() {
  const msgs = useChatStore.getState().currentSession!.messages
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i]!.role === 'assistant') return msgs[i]!
  }
  throw new Error('no assistant message')
}

function callByToken(token: string) {
  const call = (active().tool_calls ?? []).find(
    (c) => c.approval?.token === token || c.description === token,
  )
  if (!call) throw new Error(`no gate carries ${token}`)
  return call
}

function openGate(token: string, command: string) {
  useChatStore.getState().resolveSandbox(token, 'run_shell', { command })
}

describe('chatStore approval gates (finding 40)', () => {
  beforeEach(() => {
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
    useChatStore.getState().addMessage('user', 'clean the cache')
    useChatStore.getState().startTurn()
  })

  it('opens one gate per token, in the order they arrived', () => {
    openGate('tok-a', 'rm -rf /tmp/cache')
    openGate('tok-b', 'rm -rf /tmp/logs')

    const calls = active().tool_calls!
    expect(calls).toHaveLength(2)
    expect(calls.map((c) => c.approval?.token)).toEqual(['tok-a', 'tok-b'])
    expect(calls.every((c) => c.status === 'waiting')).toBe(true)
  })

  it('a frame that arrives twice for one token opens nothing twice', () => {
    openGate('tok-a', 'ls')
    openGate('tok-a', 'ls')

    expect(active().tool_calls).toHaveLength(1)
    expect(useChatStore.getState().sandboxGateOpen('tok-a')).toBe(true)
  })

  it('closes the gate that was answered and leaves the other one waiting', () => {
    openGate('tok-a', 'rm -rf /tmp/cache')
    openGate('tok-b', 'rm -rf /tmp/logs')

    useChatStore.getState().approveSandbox('tok-b')

    const answered = callByToken('tok-b')
    expect(answered.status).toBe('approved')
    expect(answered.approval).toMatchObject({
      state: 'answered',
      outcome: 'allowed',
      closedBy: 'you',
    })
    const stillOpen = callByToken('tok-a')
    expect(stillOpen.status).toBe('waiting')
    expect(stillOpen.approval?.state).toBe('waiting')
    expect(useChatStore.getState().sandboxGateOpen('tok-a')).toBe(true)
    expect(useChatStore.getState().sandboxGateOpen('tok-b')).toBe(false)
  })

  it('keeps both records when a turn answers both gates', () => {
    openGate('tok-a', 'rm -rf /tmp/cache')
    openGate('tok-b', 'rm -rf /tmp/logs')

    useChatStore.getState().approveSandbox('tok-a')
    useChatStore.getState().denySandbox('tok-b')

    const calls = active().tool_calls!
    expect(calls.map((c) => c.status)).toEqual(['approved', 'denied'])
    expect(calls.map((c) => c.approval?.outcome)).toEqual(['allowed', 'denied'])
  })

  it('names the companion when it is the companion that answered', () => {
    openGate('tok-a', 'ls')
    useChatStore.getState().approveSandbox('tok-a', 'companion')
    expect(callByToken('tok-a').approval).toMatchObject({
      state: 'answered',
      outcome: 'allowed',
      closedBy: 'companion',
    })
  })

  it('closes a gate whose request is on its way, and opens it again when that failed', () => {
    openGate('tok-a', 'ls')
    useChatStore.getState().markSandboxSubmitting('tok-a')
    expect(useChatStore.getState().sandboxGateOpen('tok-a')).toBe(false)

    useChatStore.getState().reopenSandbox('tok-a')
    expect(callByToken('tok-a').approval?.state).toBe('waiting')
    expect(useChatStore.getState().sandboxGateOpen('tok-a')).toBe(true)
  })

  it('writes an expiry as an expiry: no outcome, no hand of the reader', () => {
    openGate('tok-a', 'rm -rf /tmp/cache')
    openGate('tok-b', 'rm -rf /tmp/logs')

    useChatStore.getState().markSandboxExpired('tok-a')

    const expired = callByToken('tok-a')
    expect(expired.status).toBe('expired')
    expect(expired.approval?.state).toBe('expired')
    expect(expired.approval?.outcome).toBeUndefined()
    expect(expired.approval?.closedBy).toBe('server')
    expect(useChatStore.getState().sandboxGateOpen('tok-a')).toBe(false)
    // The gate the reader never saw answered stays answerable.
    expect(useChatStore.getState().sandboxGateOpen('tok-b')).toBe(true)
  })

  it('takes no second decision on a closed gate', () => {
    openGate('tok-a', 'ls')
    useChatStore.getState().approveSandbox('tok-a')
    useChatStore.getState().denySandbox('tok-a')
    expect(callByToken('tok-a').status).toBe('approved')

    useChatStore.getState().markSandboxExpired('tok-a')
    expect(callByToken('tok-a').status).toBe('approved')
    expect(callByToken('tok-a').approval?.state).toBe('answered')
  })

  it('still closes a gate whose click lands after the stream ended', () => {
    openGate('tok-a', 'ls')
    useChatStore.getState().finishTurn()

    useChatStore.getState().approveSandbox('tok-a')
    expect(callByToken('tok-a').status).toBe('approved')
  })
})
