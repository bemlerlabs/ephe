/**
 * Round 1 (parity): the ordered block chronology of an assistant message.
 *
 * The reference harness renders to the beat of the events: text → tool → text. For
 * that the store keeps a `blocks` list per message in arrival order (text and tool
 * blocks), alongside the content projection and the tool_calls array.
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

describe('chatStore Block-Chronologie (Runde 1)', () => {
  beforeEach(() => {
    resetStore()
    useChatStore.getState().createSession('Test-Sitzung')
  })

  it('chunk → tool → chunk: blocks = [text, tool, text] in Ankunftsreihenfolge', () => {
    const s = useChatStore.getState()
    s.startTurn()
    s.appendChunk('A')
    s.upsertToolCall({ name: 'run_shell', args: { command: 'ls' }, status: 'pending' })
    const id = active().tool_calls![0]!.id
    s.upsertToolCall({ id, name: 'run_shell', result: 'ok', status: 'completed' })
    s.appendChunk('B')

    const a = active()
    expect(a.blocks).toEqual([
      { kind: 'text', text: 'A' },
      { kind: 'tool', callId: id },
      { kind: 'text', text: 'B' },
    ])
    // content projection = the concatenated text of the text blocks
    expect(a.content).toBe('AB')
    expect(a.tool_calls).toHaveLength(1)
  })

  it('mehrere tool-Frames desselben Calls erzeugen genau EINEN tool-Block', () => {
    const s = useChatStore.getState()
    s.startTurn()
    s.upsertToolCall({ name: 'run_shell', args: { command: 'ls' }, status: 'pending' })
    s.upsertToolCall({ name: 'run_shell', stdout: 'out', status: 'pending' }) // stdout frame (no id)
    s.appendChunk('Z')
    const a = active()
    const toolBlocks = (a.blocks ?? []).filter((b) => b.kind === 'tool')
    expect(toolBlocks).toHaveLength(1)
    expect(a.blocks).toEqual([
      { kind: 'tool', callId: a.tool_calls![0]!.id },
      { kind: 'text', text: 'Z' },
    ])
  })

  it('aufeinanderfolgende tool-Blocke bleiben einzelne Eintraege (Gruppe bildt der Renderer)', () => {
    const s = useChatStore.getState()
    s.startTurn()
    s.upsertToolCall({ name: 'run_shell', args: { command: 'ls' }, status: 'pending' })
    const id1 = active().tool_calls![0]!.id
    s.upsertToolCall({ id: id1, name: 'run_shell', result: 'ok', status: 'completed' })
    s.upsertToolCall({ name: 'run_shell', args: { command: 'pwd' }, status: 'pending' })
    s.appendChunk('Z')
    const ids = active().tool_calls!.map((c) => c.id)
    expect(ids).toHaveLength(2)
    expect(active().blocks).toEqual([
      { kind: 'tool', callId: ids[0] },
      { kind: 'tool', callId: ids[1] },
      { kind: 'text', text: 'Z' },
    ])
    expect(active().blocks).toEqual(expect.arrayContaining([{ kind: 'tool', callId: ids[1] }]))
  })

  it('replaceText ueberschreibt den letzten text-Block (Revision), nicht die tool-Blocke', () => {
    const s = useChatStore.getState()
    s.startTurn()
    s.appendChunk('alt')
    s.upsertToolCall({ name: 'read_file', args: { path: 'a' }, status: 'completed' })
    s.appendChunk('fort')
    s.replaceText('neu und sauber')
    const a = active()
    expect(a.content).toBe('neu und sauber')
    expect(a.blocks).toEqual([
      { kind: 'text', text: 'alt' },
      { kind: 'tool', callId: a.tool_calls![0]!.id },
      { kind: 'text', text: 'neu und sauber' },
    ]) // the last text block carries the revision, the tool block keeps its position
  })

  it('ohne blocks (legacy-Seed) bleibt die alte Reihenfolge nutzbar: content + tool_calls gesetzt', () => {
    const s = useChatStore.getState()
    s.addMessage('assistant', 'legacy text', [
      { id: 'x', name: 'run_shell', args: {}, status: 'completed' },
    ])
    const a = active()
    expect(a.blocks).toBeUndefined()
    expect(a.content).toBe('legacy text')
    expect(a.tool_calls).toHaveLength(1)
  })
})
