/**
 * Ephe — PWA chat UX plan, task A5: store in-place streaming actions
 *
 * GIVEN  chatStore with the new streaming actions (startTurn, appendChunk, …)
 * WHEN   an SSE turn runs event by event
 * THEN   exactly ONE assistant message per turn (no addMessage-per-chunk duplicate)
 * AND    thinking/activities/tool_calls are updated in place
 * AND    sandbox flow: waiting → approved/denied (token from sandbox_confirm)
 * AND    finishTurn ends the turn (streaming=false, thinking.end set)
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from './chatStore'
import { THINKING_MAX_CHARS } from '@/lib/thinking'

/** Last active assistant message (the streaming message) of the active session */
function active() {
  const cs = useChatStore.getState().currentSession!
  const msgs = cs.messages
  for (let i = msgs.length - 1; i >= 0; i--) {
    if (msgs[i]!.role === 'assistant') return msgs[i]!
  }
  throw new Error('keine Assistant-Message')
}

/** Store reset before every test (fresh state) */
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

describe('chatStore streaming-Actions (A5)', () => {
  beforeEach(() => {
    resetStore()
    useChatStore.getState().createSession('Test-Sitzung')
  })

  it('startTurn erstellt exakt EINE Assistant-Message mit streaming=true + thinking', () => {
    useChatStore.getState().addMessage('user', 'Hallo')
    useChatStore.getState().startTurn()

    const msgs = useChatStore.getState().currentSession!.messages
    expect(msgs).toHaveLength(2)
    const a = active()
    expect(a.role).toBe('assistant')
    expect(a.content).toBe('')
    expect(a.streaming).toBe(true)
    expect(a.thinking).not.toBeNull()
    expect(a.thinking!.start).toBeTypeOf('number')
    expect(a.thinking!.end).toBeNull()
    expect(a.activities).toEqual([])
  })

  it('appendChunk hängt an der aktiven Message an (keine Duplikate über 50 Chunks)', () => {
    useChatStore.getState().startTurn()
    const store = useChatStore.getState()
    for (let i = 0; i < 50; i++) store.appendChunk(`chunk${i}`)

    const assistantMsgs = useChatStore
      .getState()
      .currentSession!.messages.filter((m) => m.role === 'assistant')
    expect(assistantMsgs).toHaveLength(1)
    expect(assistantMsgs[0]!.content).toContain('chunk49')
    expect(assistantMsgs[0]!.content).toContain('chunk0')
    // order preserved
    expect(assistantMsgs[0]!.content.indexOf('chunk0')).toBeLessThan(
      assistantMsgs[0]!.content.indexOf('chunk49'),
    )
  })

  it('replaceText ersetzt den kompletten Content (quality_fix)', () => {
    useChatStore.getState().startTurn()
    useChatStore.getState().appendChunk('alt')
    useChatStore.getState().replaceText('neu und sauber')
    expect(active().content).toBe('neu und sauber')
  })

  it('appendThinking hängt Reasoning an thinking.text an (nicht in content)', () => {
    useChatStore.getState().startTurn()
    const s = useChatStore.getState()
    s.appendThinking('Ich überlege,')
    s.appendThinking(' was zu tun ist.')
    const a = active()
    expect(a.thinking!.text).toBe('Ich überlege, was zu tun ist.')
    // Thinking text must NOT end up in the visible content
    expect(a.content).toBe('')
    // thinking.end stays null until a content chunk arrives
    expect(a.thinking!.end).toBeNull()
  })

  it('appendChunk schließt die Thinking-Phase (end gesetzt beim 1. Content-Chunk)', () => {
    useChatStore.getState().startTurn()
    useChatStore.getState().appendThinking('Überlegung')
    const before = active().thinking!.end
    expect(before).toBeNull()
    useChatStore.getState().appendChunk('Antwort')
    const a = active()
    expect(a.thinking!.end).not.toBeNull()
    expect(a.thinking!.text).toBe('Überlegung') // the reasoning stays
    expect(a.content).toBe('Antwort')
  })

  it('appendThinking trimmt thinking.text auf THINKING_MAX_CHARS (Tail)', () => {
    useChatStore.getState().startTurn()
    const s = useChatStore.getState()
    s.appendThinking('x'.repeat(THINKING_MAX_CHARS + 1000))
    const t = active().thinking!.text!
    expect(t.length).toBe(THINKING_MAX_CHARS)
    // Tail trim: the last character survives
    expect(t.endsWith('x'.repeat(THINKING_MAX_CHARS))).toBe(true)
  })

  it('setReflecting/setRevising/setQualityCheck setzen die streamMeta-Flags (transient)', () => {
    useChatStore.getState().startTurn()
    useChatStore.getState().setReflecting(true)
    expect(active().streamMeta?.reflecting).toBe(true)

    useChatStore.getState().setReflecting(false)
    useChatStore.getState().setRevising(true)
    expect(active().streamMeta?.reflecting).toBe(false)
    expect(active().streamMeta?.revising).toBe(true)

    useChatStore.getState().setRevising(false)
    useChatStore.getState().setQualityCheck(true)
    expect(active().streamMeta?.qualityCheck).toBe(true)
  })

  it('upsertToolCall: tool_start (ohne id) erzeugt Entry, tool_done (mit id) füllt result', () => {
    useChatStore.getState().startTurn()
    const s = useChatStore.getState()

    s.upsertToolCall({ name: 'run_shell', args: { command: 'ls' }, status: 'pending' })
    let a = active()
    expect(a.tool_calls).toHaveLength(1)
    expect(a.tool_calls![0]!.name).toBe('run_shell')
    expect(a.tool_calls![0]!.status).toBe('pending')
    const id = a.tool_calls![0]!.id

    s.upsertToolCall({ id, name: 'run_shell', result: 'ok', status: 'completed' })
    a = active()
    expect(a.tool_calls).toHaveLength(1) // upserted, not duplicated
    expect(a.tool_calls![0]!.result).toBe('ok')
    expect(a.tool_calls![0]!.status).toBe('completed')
  })

  it('upsertToolCall K3: stdout-Chunks haengen an, durationMs uebersteht duration_ms', () => {
    useChatStore.getState().startTurn()
    const s = useChatStore.getState()

    s.upsertToolCall({ name: 'run_shell', args: { command: 'ls' }, status: 'pending' })
    s.upsertToolCall({ name: 'run_shell', stdout: 'out-1', status: 'pending' })
    s.upsertToolCall({ name: 'run_shell', result: 'out-1', status: 'completed', durationMs: 0.8 })
    const call = active().tool_calls![0]!
    expect(call.stdout).toBe('out-1')
    expect(call.duration_ms).toBe(0.8)
    expect(call.status).toBe('completed')
  })

  it('upsertActivity: running → done (in-place, 1 Entry pro Label)', () => {
    useChatStore.getState().startTurn()
    const s = useChatStore.getState()

    s.upsertActivity({ label: 'git status', status: 'running' })
    expect(active().activities).toHaveLength(1)

    s.upsertActivity({ label: 'git status', status: 'done' })
    const acts = active().activities!
    expect(acts).toHaveLength(1)
    expect(acts[0]!.status).toBe('done')
  })

  it('resolveSandbox erzeugt einen Tool-Call im Status waiting + speichert den Token', () => {
    useChatStore.getState().startTurn()
    useChatStore.getState().resolveSandbox('token-123', 'run_shell', { command: 'rm -rf /tmp/x' })

    const a = active()
    expect(a.tool_calls).toHaveLength(1)
    expect(a.tool_calls![0]!.name).toBe('run_shell')
    expect(a.tool_calls![0]!.status).toBe('waiting')
    expect(a.tool_calls![0]!.description).toBe('token-123') // the token (for /sandbox/approve)
    expect(a.tool_calls![0]!.args).toEqual({ command: 'rm -rf /tmp/x' })
  })

  it('approveSandbox/denySandbox setzen approved/denied (am letzten waiting-Tool-Call)', () => {
    useChatStore.getState().startTurn()
    useChatStore.getState().resolveSandbox('t', 'run_shell', { command: 'ls' })

    useChatStore.getState().approveSandbox()
    expect(active().tool_calls![0]!.status).toBe('approved')

    useChatStore.getState().resolveSandbox('t2', 'run_shell', { command: 'rm' })
    useChatStore.getState().denySandbox()
    expect(active().tool_calls![0]!.status).toBe('denied')
  })

  it('markStreamError setzt error-Text + beendet den Stream-Zustand', () => {
    useChatStore.getState().startTurn()
    useChatStore.getState().appendChunk('halb')
    useChatStore.getState().markStreamError('Ollama nicht erreichbar')

    const a = active()
    expect(a.error).toBe('Ollama nicht erreichbar')
    expect(a.streaming).toBe(false)
    expect(a.content).toBe('halb') // the partial content stays visible
  })

  it('finishTurn schließt den Turn: streaming=false, thinking.end gesetzt', () => {
    useChatStore.getState().startTurn()
    useChatStore.getState().appendChunk('fertig')
    useChatStore.getState().finishTurn()

    const a = active()
    expect(a.streaming).toBe(false)
    expect(a.thinking!.end).not.toBeNull()
    expect(a.content).toBe('fertig')
  })

  it('startTurn ohne aktive Session ist ein no-op (kein Crash)', () => {
    useChatStore.setState({ activeSessionId: null, currentSession: null, sessions: [] })
    expect(() => useChatStore.getState().startTurn()).not.toThrow()
  })
})
