import { describe, it, expect, vi } from 'vitest'
import { applyStreamEvent } from './streamActions'

/**
 * QD-015 Z2: the budget frame at a capped turn. The dispatcher's whole job is to
 * pass the server's two numbers through untouched — the card and the follow-up
 * turn both read them from the store.
 */
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

describe('applyStreamEvent — budget frame', () => {
  it('carries the cap and the extra rounds to the store', () => {
    const store = mockStore()
    applyStreamEvent({ type: 'budget', action: 'continue_turn', cap: 25, extra: 10 }, store)
    expect(store.markBudgetReached).toHaveBeenCalledWith(25, 10)
  })

  it('does not finish the turn on its own', () => {
    const store = mockStore()
    applyStreamEvent({ type: 'budget', action: 'continue_turn', cap: 40, extra: 10 }, store)
    expect(store.finishTurn).not.toHaveBeenCalled()
  })
})
