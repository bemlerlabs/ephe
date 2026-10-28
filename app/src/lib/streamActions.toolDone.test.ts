/**
 * applyStreamEvent — tool_done outcome mapping.
 *
 * GIVEN  a tool_done frame that carries a status
 * WHEN   applyStreamEvent maps it onto the store
 * THEN   "failed" becomes a denied tool call and "completed" a completed one,
 *        so a refused call can never read as a success
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
    markBudgetReached: vi.fn(),
    setReflecting: vi.fn(),
    setRevising: vi.fn(),
    setQualityCheck: vi.fn(),
    finishTurn: vi.fn(),
    beginHelperChat: vi.fn(),
    stepHelperChat: vi.fn(),
    setProgress: vi.fn(),
    endHelperChat: vi.fn(),
  }
}

describe('applyStreamEvent tool_done outcome', () => {
  let store: ReturnType<typeof mockStore>

  beforeEach(() => {
    store = mockStore()
  })

  it('tool_done with status "failed" → upsertToolCall(denied), never completed', () => {
    applyStreamEvent(
      {
        type: 'tool_done',
        tool: 'run_shell',
        result: '[TOOL-DENIED] run_shell was not executed: the user did not approve the run.',
        status: 'failed',
        reason_code: 'not_approved_by_user',
      },
      store,
    )
    expect(store.upsertToolCall).toHaveBeenLastCalledWith({
      name: 'run_shell',
      result: '[TOOL-DENIED] run_shell was not executed: the user did not approve the run.',
      status: 'denied',
      reasonCode: 'not_approved_by_user',
    })
  })

  it('forwards the frame digest so the proof ledger can show it', () => {
    applyStreamEvent(
      {
        type: 'tool_done',
        tool: 'run_shell',
        result: 'ok',
        sha256: '9f86d0818c0f2f4d',
      },
      store,
    )
    expect(store.upsertToolCall).toHaveBeenLastCalledWith({
      name: 'run_shell',
      result: 'ok',
      status: 'completed',
      sha256: '9f86d0818c0f2f4d',
    })
  })

  it('a failed fetch becomes failed with its reason, not denied', () => {
    applyStreamEvent(
      {
        type: 'tool_done',
        tool: 'fetch_url',
        result: '[fetch failed] HTTP 404 for https://example.test/missing',
        status: 'failed',
        reason_code: 'fetch_http_error',
        reason_params: { status: '404' },
      },
      store,
    )
    expect(store.upsertToolCall).toHaveBeenLastCalledWith({
      name: 'fetch_url',
      result: '[fetch failed] HTTP 404 for https://example.test/missing',
      status: 'failed',
      reasonCode: 'fetch_http_error',
      reasonParams: { status: '404' },
    })
  })

  it('tool_done with status "completed" → upsertToolCall(completed)', () => {
    applyStreamEvent(
      { type: 'tool_done', tool: 'read_file', result: 'body', status: 'completed' },
      store,
    )
    expect(store.upsertToolCall).toHaveBeenLastCalledWith({
      name: 'read_file',
      result: 'body',
      status: 'completed',
    })
  })
})
