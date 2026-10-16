/**
 * Ephe — W14/P1-7: TTFT on a streaming turn.
 *
 * GIVEN  a turn with a thinking phase and two content chunks
 * WHEN   the first content chunk arrives
 * THEN   the time to the first token (ttftMs) sits on the message —
 *        and the chunks that follow do NOT overwrite it.
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

describe('chatStore TTFT (W14/P1-7)', () => {
  beforeEach(() => {
    useChatStore.setState({
      sessions: [],
      activeSessionId: null,
      isTyping: false,
      pendingToolCall: null,
      currentSession: null,
      checkpoints: {},
    })
    useChatStore.getState().createSession('TTFT-Sitzung')
  })

  it('setzt ttftMs beim ersten Content-Chunk und haelt ihn danach', () => {
    useChatStore.getState().addMessage('user', 'Hallo')
    useChatStore.getState().startTurn()
    useChatStore.getState().appendThinking('think ')
    useChatStore.getState().appendChunk('eins')
    const first = active().ttftMs
    expect(typeof first).toBe('number')
    useChatStore.getState().appendChunk(' zwei')
    expect(active().ttftMs).toBe(first)
    expect(active().content).toBe('eins zwei')
  })

  it('laesst ttftMs bei Legacy-Messages ohne Messung ungesetzt', () => {
    useChatStore.getState().addMessage('user', 'Hallo')
    useChatStore.getState().startTurn()
    useChatStore.getState().appendChunk('a')
    expect(active().ttftMs).toBeDefined()
  })
})
