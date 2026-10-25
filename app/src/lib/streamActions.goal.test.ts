import { describe, it, expect, vi, beforeEach } from 'vitest'
import { applyStreamEvent } from './streamActions'

/**
 * The `goal_*` frames (the goal loop of core/goal_loop.py, reached as `/goal`) —
 * their own file because the shared mock store lives in streamActions.test.ts,
 * which sits at the 400-line architecture cap.
 *
 * The contract these frames carry: goal_start names the loop's own three values,
 * goal_turn moves the round, goal_check adds that round's verdict. The store merges
 * them (beginGoal/advanceGoal); the dispatcher only has to pass them through intact.
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

describe('applyStreamEvent — goal frames', () => {
  let store: ReturnType<typeof mockStore>

  beforeEach(() => {
    store = mockStore()
  })

  it('goal_start → beginGoal with the loop’s goal, its check command and its budget', () => {
    applyStreamEvent(
      {
        type: 'goal_start',
        goal: 'Fix the login bug',
        check: 'npm test',
        max_turns: 4,
      },
      store,
    )
    expect(store.beginGoal).toHaveBeenCalledWith('Fix the login bug', 'npm test', 4)
  })

  it('goal_turn → advanceGoal with the round and no verdict of its own', () => {
    applyStreamEvent({ type: 'goal_turn', turn: 2 }, store)
    expect(store.advanceGoal).toHaveBeenCalledWith(2)
  })

  it('goal_check → advanceGoal with the round and that round’s verdict', () => {
    applyStreamEvent({ type: 'goal_check', turn: 2, ok: false, output: '1 failed' }, store)
    expect(store.advanceGoal).toHaveBeenCalledWith(2, false)
  })

  it('a goal frame touches neither the plan nor the content stream', () => {
    applyStreamEvent({ type: 'goal_start', goal: 'g', check: 'pytest -q', max_turns: 10 }, store)
    expect(store.setPlan).not.toHaveBeenCalled()
    expect(store.appendChunk).not.toHaveBeenCalled()
    expect(store.upsertActivity).not.toHaveBeenCalled()
  })
})
