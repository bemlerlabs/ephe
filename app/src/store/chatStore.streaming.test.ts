/**
 * Ephe — PWA chat UX plan, task A5: store in-place streaming actions
 *
 * GIVEN  chatStore with the new streaming actions (startTurn, appendChunk, …)
 * WHEN   an SSE turn runs event by event
 * THEN   exactly ONE assistant message per turn (no addMessage-per-chunk duplicate)
 * AND    thinking/activities/tool_calls are updated in place
 * AND    sandbox flow: a gate closes by the token of its sandbox_confirm frame, never
 *        by the position of a waiting row (audit finding 40)
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

  it('startTurn creates exactly one assistant message with streaming=true plus thinking', () => {
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

  it('appendChunk appends to the active message (no duplicates over 50 chunks)', () => {
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

  it('replaceText replaces the whole content (quality_fix)', () => {
    useChatStore.getState().startTurn()
    useChatStore.getState().appendChunk('alt')
    useChatStore.getState().replaceText('neu und sauber')
    expect(active().content).toBe('neu und sauber')
  })

  it('appendThinking appends reasoning to thinking.text and never into content', () => {
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

  it('appendChunk closes the thinking phase (end set on the first content chunk)', () => {
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

  it('appendThinking trims thinking.text to THINKING_MAX_CHARS (the tail)', () => {
    useChatStore.getState().startTurn()
    const s = useChatStore.getState()
    s.appendThinking('x'.repeat(THINKING_MAX_CHARS + 1000))
    const t = active().thinking!.text!
    expect(t.length).toBe(THINKING_MAX_CHARS)
    // Tail trim: the last character survives
    expect(t.endsWith('x'.repeat(THINKING_MAX_CHARS))).toBe(true)
  })

  it('the reflecting, revising and quality setters set streamMeta flags (transient)', () => {
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

  it('upsertToolCall: tool_start without an id creates the entry, tool_done fills result', () => {
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

  it('upsertActivity: running to done, in place, one entry per label', () => {
    useChatStore.getState().startTurn()
    const s = useChatStore.getState()

    s.upsertActivity({ label: 'git status', status: 'running' })
    expect(active().activities).toHaveLength(1)

    s.upsertActivity({ label: 'git status', status: 'done' })
    const acts = active().activities!
    expect(acts).toHaveLength(1)
    expect(acts[0]!.status).toBe('done')
  })

  it('resolveSandbox creates a tool call in waiting status and stores the token', () => {
    useChatStore.getState().startTurn()
    useChatStore.getState().resolveSandbox('token-123', 'run_shell', { command: 'rm -rf /tmp/x' })

    const a = active()
    expect(a.tool_calls).toHaveLength(1)
    expect(a.tool_calls![0]!.name).toBe('run_shell')
    expect(a.tool_calls![0]!.status).toBe('waiting')
    expect(a.tool_calls![0]!.description).toBe('token-123') // the token (for /sandbox/approve)
    expect(a.tool_calls![0]!.args).toEqual({ command: 'rm -rf /tmp/x' })
  })

  it('approve and deny close the gate of the token they name', () => {
    useChatStore.getState().startTurn()
    useChatStore.getState().resolveSandbox('t', 'run_shell', { command: 'ls' })

    useChatStore.getState().approveSandbox('t')
    expect(active().tool_calls![0]!.status).toBe('approved')

    useChatStore.getState().resolveSandbox('t2', 'run_shell', { command: 'rm' })
    useChatStore.getState().denySandbox('t2')
    expect(active().tool_calls![1]!.status).toBe('denied')
    // The gate that was answered first stays answered.
    expect(active().tool_calls![0]!.status).toBe('approved')
  })

  it('markStreamError sets the error text and ends the stream state', () => {
    useChatStore.getState().startTurn()
    useChatStore.getState().appendChunk('halb')
    useChatStore.getState().markStreamError('Ollama nicht erreichbar')

    const a = active()
    expect(a.error).toBe('Ollama nicht erreichbar')
    expect(a.streaming).toBe(false)
    expect(a.content).toBe('halb') // the partial content stays visible
  })

  it('finishTurn closes the turn: streaming=false with thinking.end set', () => {
    useChatStore.getState().startTurn()
    useChatStore.getState().appendChunk('fertig')
    useChatStore.getState().finishTurn()

    const a = active()
    expect(a.streaming).toBe(false)
    expect(a.thinking!.end).not.toBeNull()
    expect(a.content).toBe('fertig')
  })

  it('startTurn without an active session is a no-op (no crash)', () => {
    useChatStore.setState({ activeSessionId: null, currentSession: null, sessions: [] })
    expect(() => useChatStore.getState().startTurn()).not.toThrow()
  })
})
