/**
 * Ephe — P6-Timeline (ref-01): the measured turn wall-time.
 *
 * GIVEN  a running assistant turn
 * WHEN   the stream ends (finishTurn) or fails (markStreamError)
 * THEN   the message carries durationMs (stream end − turn start) — the "Worked
 *        for" header shows real wall time, never an invented default.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from './chatStore'

function active() {
  const cs = useChatStore.getState().currentSession!
  const msgs = cs.messages
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i]!.role === 'assistant') return msgs[i]!
  }
  throw new Error('keine Assistant-Message')
}

describe('chatStore Turn-Dauer (P6-Timeline, ref-01)', () => {
  beforeEach(() => {
    useChatStore.setState({
      sessions: [],
      activeSessionId: null,
      isTyping: false,
      pendingToolCall: null,
      currentSession: null,
      checkpoints: {},
    })
    useChatStore.getState().createSession('Timeline-Sitzung')
  })

  it('finishTurn setzt durationMs an der Assistant-Message', () => {
    useChatStore.getState().addMessage('user', 'Hallo')
    useChatStore.getState().startTurn()
    useChatStore.getState().appendChunk('antwort')
    useChatStore.getState().finishTurn()
    const m = active()
    expect(m.streaming).toBe(false)
    expect(typeof m.durationMs).toBe('number')
    expect(m.durationMs!).toBeGreaterThanOrEqual(0)
  })

  it('markStreamError setzt durationMs ebenfalls (gescheiterte Turns zählen)', () => {
    useChatStore.getState().addMessage('user', 'Hallo')
    useChatStore.getState().startTurn()
    useChatStore.getState().markStreamError('boom')
    const m = active()
    expect(m.streaming).toBe(false)
    expect(m.error).toBe('boom')
    expect(typeof m.durationMs).toBe('number')
  })
})
