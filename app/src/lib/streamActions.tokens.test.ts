// C3: the token counts the engine reports belong on the line the reader sees.
// Split out of streamActions.test.ts, which crossed the 400-line wall.
import { describe, it, expect, vi } from 'vitest'
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

describe('applyStreamEvent token accounting on the activity lines', () => {
  it('C3: the done line carries the tokens the engine reported', () => {
    const store = mockStore()
    applyStreamEvent(
      {
        type: 'swarm_agent_done',
        swarm_id: 'sw-1',
        agent_id: 'a1',
        summary: 'Y',
        tokens_in: 1200,
        tokens_out: 240,
      },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'Agent a1',
      status: 'done',
      detail: 'Y · 1.2k in / 240 out tok',
    })
  })

  it('C3: an engine that reported no usage adds nothing to the line', () => {
    const store = mockStore()
    applyStreamEvent(
      { type: 'swarm_agent_done', swarm_id: 'sw-1', agent_id: 'a1', summary: 'Y' },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'Agent a1',
      status: 'done',
      detail: 'Y',
    })
  })

  it('C3: a swarm_done with measured tokens states the merge ratio', () => {
    const store = mockStore()
    applyStreamEvent(
      {
        type: 'swarm_done',
        swarm_id: 'sw-1',
        agent_count: 2,
        final: 'fertig',
        tokens: { agent_in: 12000, agent_out: 3000, merge_in: 1200, merge_out: 300 },
      },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'Swarm envelope',
      status: 'done',
      detail: '12.0k → 1.2k tok (−90%)',
    })
  })
})
