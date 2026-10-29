/**
 * applyStreamEvent — the ask gate's two frames.
 *
 * GIVEN  an ask_user frame, and the ask_timeout frame that ends a wait
 * WHEN   applyStreamEvent maps them onto the store
 * THEN   the question reaches resolveAsk with its token, options and default, and a
 *        timeout reaches markAskTimedOut for that one token
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
    markSolInsight: vi.fn(),
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

describe('applyStreamEvent ask gate', () => {
  let store: ReturnType<typeof mockStore>

  beforeEach(() => {
    store = mockStore()
  })

  it('ask_user → resolveAsk (token, question, options, default, timeout)', () => {
    applyStreamEvent(
      {
        type: 'ask_user',
        token: 'ask-9',
        question: 'Welcher Branch?',
        options: ['main', 'wt/n1-ask'],
        recommendation: 'main',
        default: 'main',
        multiSelect: false,
        timeout_s: 180,
      },
      store,
    )
    expect(store.resolveAsk).toHaveBeenCalledWith({
      token: 'ask-9',
      question: 'Welcher Branch?',
      options: ['main', 'wt/n1-ask'],
      recommendation: 'main',
      multiSelect: false,
      timeoutS: 180,
      defaultAnswer: 'main',
    })
  })

  it('ask_timeout → markAskTimedOut (that run went on with its default)', () => {
    applyStreamEvent(
      { type: 'ask_timeout', token: 'ask-9', timeout_s: 180, default: 'main' },
      store,
    )
    expect(store.markAskTimedOut).toHaveBeenCalledWith('ask-9')
  })
})
