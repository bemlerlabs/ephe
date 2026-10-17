/**
 * R46 hygiene (owner live audit 28.09.) — empty assistant bubbles
 *
 * GIVEN  the stream dies BEFORE any chunk/tool/thinking arrives
 * WHEN   finishTurn() ends the turn
 * THEN   the empty assistant bubble is removed instead of persisted
 * AND    a bubble with any content at all (text/tool/activity/thinking/error)
 *        stays — the hygiene never eats something real.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from './chatStore'

function resetStore() {
  useChatStore.setState({
    sessions: [],
    activeSessionId: null,
    isTyping: false,
    pendingToolCall: null,
    currentSession: null,
    checkpoints: {},
  })
}

describe('finishTurn entfernt leere Assistant-Bubbles (R46-Hygiene)', () => {
  beforeEach(resetStore)

  it('komplett leere Bubble (kein Chunk angekommen) verschwindet', () => {
    const store = useChatStore.getState()
    store.createSession()
    store.startTurn()
    // no appendChunk, no activity — the stream died immediately.
    useChatStore.getState().finishTurn()
    const assistants = useChatStore
      .getState()
      .currentSession!.messages.filter((m) => m.role === 'assistant')
    expect(assistants.length).toBe(0)
  })

  it('Bubble mit Text bleibt (Hygiene frisst nichts Reales)', () => {
    const store = useChatStore.getState()
    store.createSession()
    store.startTurn()
    store.appendChunk('echte Antwort')
    useChatStore.getState().finishTurn()
    const assistants = useChatStore
      .getState()
      .currentSession!.messages.filter((m) => m.role === 'assistant')
    expect(assistants.length).toBe(1)
    expect(assistants[0]!.content).toBe('echte Antwort')
  })

  it('Bubble mit Activity-Spur bleibt (Tool-Trace ist Inhalt)', () => {
    const store = useChatStore.getState()
    store.createSession()
    store.startTurn()
    store.upsertActivity({ label: 'run_shell', status: 'running' })
    useChatStore.getState().finishTurn()
    const assistants = useChatStore
      .getState()
      .currentSession!.messages.filter((m) => m.role === 'assistant')
    expect(assistants.length).toBe(1)
  })

  it('Bubble mit Fehler bleibt (Fehlermeldung ist Inhalt)', () => {
    const store = useChatStore.getState()
    store.createSession()
    store.startTurn()
    store.markStreamError('Verbindung verloren')
    // markStreamError already sets streaming=false; finishTurn then runs normally.
    useChatStore.getState().finishTurn()
    const assistants = useChatStore
      .getState()
      .currentSession!.messages.filter((m) => m.role === 'assistant')
    expect(assistants.length).toBe(1)
    expect(assistants[0]!.error).toBe('Verbindung verloren')
  })
})
