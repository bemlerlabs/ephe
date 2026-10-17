/**
 * E wave (interleaving): reasoning phases stand in their real arrival slot.
 *
 * The reference harness pattern: thinking → tool → thinking → tool → answer. For
 * that the store keeps `thinkingPhases` (arrival slots) and one `thinking` block
 * marker per phase inside the `blocks` chronology.
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

describe('chatStore Thinking-/Tool-Interleaving (E-Welle)', () => {
  beforeEach(() => {
    resetStore()
    useChatStore.getState().createSession('Interleaving')
  })

  it('denken → tool → denken: zwei Phasen, je einer an ihrer Position', () => {
    const s = useChatStore.getState()
    s.startTurn()
    s.appendThinking('ich lese zuerst die datei')
    s.appendChunk('A')
    s.upsertToolCall({ name: 'read_file', args: { path: 'a' }, status: 'completed' })
    const toolId = active().tool_calls![0]!.id
    s.appendThinking('dann fass ich zusammen')
    s.appendChunk('B')

    const a = active()
    expect(a.blocks).toEqual([
      { kind: 'thinking', index: 0 },
      { kind: 'text', text: 'A' },
      { kind: 'tool', callId: toolId },
      { kind: 'thinking', index: 1 },
      { kind: 'text', text: 'B' },
    ])
    // two separate phases, each with its own text (not into one accumulator)
    expect(a.thinkingPhases).toHaveLength(2)
    expect(a.thinkingPhases![0]!.text).toBe('ich lese zuerst die datei')
    expect(a.thinkingPhases![1]!.text).toBe('dann fass ich zusammen')
  })

  it('Chunks derselben offenen Phase waechsen nur in diese Phase', () => {
    const s = useChatStore.getState()
    s.startTurn()
    s.appendThinking('eins ')
    s.appendThinking('zwei')
    const a = active()
    expect(a.thinkingPhases).toHaveLength(1)
    expect(a.thinkingPhases![0]!.text).toBe('eins zwei')
    expect(a.blocks).toEqual([{ kind: 'thinking', index: 0 }])
  })

  it('Turn-Ende schliest alle offenen Phasen (Dauer sichtbar, kein offener Takt)', () => {
    const s = useChatStore.getState()
    s.startTurn()
    s.appendThinking('takt eins')
    s.upsertToolCall({ name: 'run_shell', args: { command: 'ls' }, status: 'completed' })
    s.appendThinking('takt zwei')
    useChatStore.getState().finishTurn()
    const a = active()
    expect(a.thinkingPhases).toHaveLength(2)
    for (const p of a.thinkingPhases!) expect(p.end).not.toBeNull()
  })

  it('legacy-Ohne-Phasen-Message rendert ueber die alte feste Folge (blocks undefined)', () => {
    const s = useChatStore.getState()
    s.addMessage('assistant', 'legacy', [
      { id: 'x', name: 'run_shell', args: {}, status: 'completed' },
    ])
    expect(active().blocks).toBeUndefined()
    expect(active().thinkingPhases).toBeUndefined()
  })
})
