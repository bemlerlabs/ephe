/**
 * Visibility wave: the helper is its own session in the store.
 *
 * A `spawn_agent` run gets a chat Renate can open and watch — built from the live
 * events while the mother task carries on undisturbed. Pins:
 *
 * 1. begin: a helper session with its own id, parentId = the mother task, title
 *    from the short label, the task as a user line, an open assistant bubble. The
 *    ACTIVE session does not switch (otherwise the chat jumps away mid-turn).
 * 2. tool: every tool step becomes a row in the helper chat.
 * 3. done: report + duration, bubble closed, running rows finished.
 * 4. Idempotency: a second begin of the same session duplicates nothing; late
 *    events for an unknown session invent it (a reload in mid-run).
 * 5. restore: the ledger record yields the same session id with
 *    task/rows/report — the click from the history opens the very same chat.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from './chatStore'
import { HELPER_PREFIX } from '@/lib/helperSession'
import type { HelperChat } from '@/lib/helperSession'

function reset() {
  useChatStore.setState({
    sessions: [],
    activeSessionId: null,
    isTyping: false,
    pendingToolCall: null,
    currentSession: null,
    checkpoints: {},
  })
}

const START = {
  chatSessionId: `${HELPER_PREFIX}abc12345`,
  agentId: 'subagent-1',
  role: 'scout',
  task: 'Finde die Timeout-Werte der Referenz',
  description: 'Research HTTP timeouts',
  parentSession: 'mutter-1',
}

function helper() {
  return useChatStore.getState().sessions.find((s) => s.id === START.chatSessionId)
}

function parentSessionId() {
  return useChatStore.getState().activeSessionId
}

describe('chatStore: the helper session from live events', () => {
  beforeEach(() => {
    reset()
    useChatStore.getState().createSession('Mutteraufgabe')
    useChatStore.getState().addMessage('user', 'Baue mir einen Bericht')
    // the mother task is running a turn right now
    useChatStore.getState().startTurn()
  })

  it('begin plants the helper session on the parent branch without moving the cursor', () => {
    const before = parentSessionId()
    useChatStore.getState().beginHelperChat(START)

    const h = helper()
    expect(h).toBeTruthy()
    // the event names the mother task — that beats wherever the cursor happens to be
    expect(h!.parentId).toBe('mutter-1')
    expect(h!.title).toBe('Research HTTP timeouts')
    expect(h!.messages).toHaveLength(2)
    expect(h!.messages[0]!.role).toBe('user')
    expect(h!.messages[0]!.content).toBe(START.task)
    expect(h!.messages[1]!.role).toBe('assistant')
    expect(h!.messages[1]!.streaming).toBe(true)
    // the cursor stays on the mother task, whose bubble keeps growing undisturbed
    expect(parentSessionId()).toBe(before)
    expect(useChatStore.getState().currentSession!.id).toBe(before)
  })

  it('without a mother in the event the running job is the mother', () => {
    const before = parentSessionId()
    useChatStore.getState().beginHelperChat({ ...START, parentSession: '', agentId: 'subagent-8' })
    expect(helper()!.parentId).toBe(before)
  })

  it('without a short label the role carries the title', () => {
    useChatStore.getState().beginHelperChat({ ...START, description: '', agentId: 'subagent-9' })
    expect(helper()!.title).toBe('scout')
  })

  it('two begins of the same session do not plant it twice', () => {
    useChatStore.getState().beginHelperChat(START)
    useChatStore.getState().beginHelperChat(START)
    const ids = useChatStore.getState().sessions.filter((s) => s.id === START.chatSessionId)
    expect(ids).toHaveLength(1)
  })

  it('tool writes a line into the running helper bubble', () => {
    useChatStore.getState().beginHelperChat(START)
    useChatStore.getState().stepHelperChat({
      chatSessionId: START.chatSessionId,
      agentId: START.agentId,
      tool: 'web_search',
      argsPreview: '{"query":"timeout"}',
    })
    const calls = helper()!.messages[1]!.tool_calls ?? []
    expect(calls).toHaveLength(1)
    expect(calls[0]!.name).toBe('web_search')
    expect(calls[0]!.args).toEqual({ query: 'timeout' })
    expect(calls[0]!.status).toBe('pending')
  })

  it('done closes the bubble and sets report and duration', () => {
    useChatStore.getState().beginHelperChat(START)
    useChatStore.getState().stepHelperChat({
      chatSessionId: START.chatSessionId,
      agentId: START.agentId,
      tool: 'read_file',
      argsPreview: '{"path":"a"}',
    })
    useChatStore.getState().endHelperChat({
      chatSessionId: START.chatSessionId,
      agentId: START.agentId,
      status: 'ok',
      report: 'Bericht: 30 Sekunden, Quelle x.',
      parentSession: 'mutter-1',
    })

    const m = helper()!.messages[1]!
    expect(m.streaming).toBe(false)
    expect(m.content).toBe('Bericht: 30 Sekunden, Quelle x.')
    expect(m.durationMs).toBeGreaterThanOrEqual(0)
    expect((m.tool_calls ?? []).every((c) => c.status === 'completed')).toBe(true)
  })

  it('two lines: the first is finished when the second begins', () => {
    useChatStore.getState().beginHelperChat(START)
    useChatStore.getState().stepHelperChat({
      chatSessionId: START.chatSessionId,
      agentId: START.agentId,
      tool: 'web_search',
      argsPreview: '{"q":"a"}',
    })
    useChatStore.getState().stepHelperChat({
      chatSessionId: START.chatSessionId,
      agentId: START.agentId,
      tool: 'read_file',
      argsPreview: '{"path":"b"}',
    })
    const calls = helper()!.messages[1]!.tool_calls ?? []
    expect(calls.map((c) => c.status)).toEqual(['completed', 'pending'])
  })

  it('a later tool without begin invents the session (reload mid-run)', () => {
    useChatStore.getState().stepHelperChat({
      chatSessionId: `${HELPER_PREFIX}ff00ff00`,
      agentId: 'subagent-3',
      tool: 'fetch_url',
      argsPreview: '{"url":"https://example.test"}',
    })
    const h = useChatStore.getState().sessions.find((s) => s.id === `${HELPER_PREFIX}ff00ff00`)
    expect(h).toBeTruthy()
    expect(h!.parentId).toBe(parentSessionId())
    expect(h!.messages[1]!.tool_calls).toHaveLength(1)
  })

  it('a restore from the ledger yields the same session with lines and report', () => {
    const chat: HelperChat = {
      chatSessionId: `${HELPER_PREFIX}9e8d7c6b`,
      agentId: 'subagent-2',
      parentSession: parentSessionId()!,
      title: 'Research HTTP timeouts',
      task: 'Finde Timeout-Werte',
      status: 'ok',
      report: 'Bericht fertig.',
      durationMs: 7234,
      startedTs: Date.now() - 7_234,
      steps: [{ tool: 'web_search', argsPreview: '{"q":"x"}', ms: 850 }],
    }
    useChatStore.getState().restoreHelperChat(chat)
    const h = useChatStore.getState().sessions.find((s) => s.id === chat.chatSessionId)
    expect(h!.parentId).toBe(chat.parentSession)
    expect(h!.title).toBe('Research HTTP timeouts')
    expect(h!.messages[0]!.content).toBe('Finde Timeout-Werte')
    const last = h!.messages[h!.messages.length - 1]!
    expect(last.streaming).toBe(false)
    expect(last.content).toBe('Bericht fertig.')
    expect(last.durationMs).toBe(7234)
    expect(last.tool_calls).toHaveLength(1)
    expect(last.tool_calls![0]!.name).toBe('web_search')
    expect(last.tool_calls![0]!.duration_ms).toBe(850)
  })

  it('helper sessions stay child-ordered in the sidebar tree', () => {
    useChatStore.getState().beginHelperChat(START)
    const tree = useChatStore.getState().sessions
    expect(tree.some((s) => s.id === START.chatSessionId && !!s.parentId)).toBe(true)
  })
})
