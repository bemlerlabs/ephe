/**
 * Visibility wave: from the subagent events applyStreamEvent also builds the
 * helper's own session — the activity line in the parent task is untouched by
 * it (existing pins in streamActions.test.ts).
 *
 * A second file, because the parent file with its 25 events would otherwise
 * break its 400-line limit; the mock-store pattern is identical.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { applyStreamEvent } from './streamActions'

function mockStore() {
  return {
    startTurn: vi.fn(),
    appendChunk: vi.fn(),
    appendThinking: vi.fn(),
    replaceText: vi.fn(),
    upsertToolCall: vi.fn(),
    upsertActivity: vi.fn(),
    setTurnId: vi.fn(),
    attachArtifact: vi.fn(),
    setPlan: vi.fn(),
    beginGoal: vi.fn(),
    advanceGoal: vi.fn(),
    resolveSandbox: vi.fn(),
    resolveAsk: vi.fn(),
    markAskTimedOut: vi.fn(),
    markStreamError: vi.fn(),
    markLastUsage: vi.fn(),
    setReflecting: vi.fn(),
    setRevising: vi.fn(),
    setQualityCheck: vi.fn(),
    finishTurn: vi.fn(),
    beginHelperChat: vi.fn(),
    stepHelperChat: vi.fn(),
    endHelperChat: vi.fn(),
  }
}

describe('applyStreamEvent — Helfer-Chat aus den Live-Ereignissen', () => {
  let store: ReturnType<typeof mockStore>

  beforeEach(() => {
    store = mockStore()
  })

  it('started → beginHelperChat mit Sitzungs- und Mutter-Id', () => {
    applyStreamEvent(
      {
        type: 'subagent_started',
        agent_id: 'subagent-9',
        role: 'scout',
        task: 'Find numbers',
        model: 'm',
        description: 'Research HTTP timeouts',
        chat_session_id: 'helper-abc12345',
        parent_session: 'mutter-1',
      },
      store,
    )
    expect(store.beginHelperChat).toHaveBeenCalledWith({
      chatSessionId: 'helper-abc12345',
      agentId: 'subagent-9',
      parentSession: 'mutter-1',
      role: 'scout',
      description: 'Research HTTP timeouts',
      task: 'Find numbers',
    })
  })

  it('tool → stepHelperChat, done → endHelperChat mit voller Berichtslänge', () => {
    applyStreamEvent(
      {
        type: 'subagent_tool',
        agent_id: 'subagent-9',
        tool: 'web_search',
        args_preview: '{"query":…}',
        chat_session_id: 'helper-abc12345',
      },
      store,
    )
    expect(store.stepHelperChat).toHaveBeenCalledWith({
      chatSessionId: 'helper-abc12345',
      agentId: 'subagent-9',
      tool: 'web_search',
      argsPreview: '{"query":…}',
    })

    applyStreamEvent(
      {
        type: 'subagent_done',
        agent_id: 'subagent-9',
        status: 'ok',
        summary: 'Kurzfassung',
        report: 'Volle Berichtslänge.',
        chat_session_id: 'helper-abc12345',
        parent_session: 'mutter-1',
      },
      store,
    )
    expect(store.endHelperChat).toHaveBeenCalledWith({
      chatSessionId: 'helper-abc12345',
      agentId: 'subagent-9',
      status: 'ok',
      report: 'Volle Berichtslänge.',
      summary: 'Kurzfassung',
      parentSession: 'mutter-1',
    })
  })

  it('aelterer Server ohne chat_session_id erfindet keine Sitzung', () => {
    applyStreamEvent(
      {
        type: 'subagent_started',
        agent_id: 'subagent-1',
        role: 'researcher',
        task: 'Find numbers',
        model: 'm',
      },
      store,
    )
    applyStreamEvent(
      { type: 'subagent_tool', agent_id: 'subagent-1', tool: 'x', args_preview: '{}' },
      store,
    )
    applyStreamEvent(
      { type: 'subagent_done', agent_id: 'subagent-1', status: 'ok', summary: 'Report ready' },
      store,
    )
    expect(store.beginHelperChat).not.toHaveBeenCalled()
    expect(store.stepHelperChat).not.toHaveBeenCalled()
    expect(store.endHelperChat).not.toHaveBeenCalled()
    // the parent task's activity axis stays in force unchanged
    expect(store.upsertActivity).toHaveBeenCalledTimes(3)
  })
})
