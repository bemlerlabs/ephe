import { describe, it, expect, vi } from 'vitest'
import { applyStreamEvent } from './streamActions'

/**
 * D2: a direction change that landed must be readable where the run is read.
 * The frame was emitted and dropped before this; the agent case keys the line
 * to its card, the run-level case stands on its own.
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

describe('applyStreamEvent — steering and gate lines', () => {
  it('keys a landed agent steer to that agent', () => {
    const store = mockStore()
    applyStreamEvent(
      {
        type: 'steer',
        status: 'landed',
        actor: 'user',
        msg: 'Direction changed by the user',
        text: 'focus on tests',
        agent_id: 'a1',
        round: 4,
      },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'Steer a1',
      status: 'done',
      detail: 'focus on tests',
    })
  })

  it('says when a run-level steer never landed', () => {
    const store = mockStore()
    applyStreamEvent(
      {
        type: 'steer',
        status: 'unlanded',
        actor: 'user',
        msg: 'Direction change missed',
        text: 'too late',
      },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'Direction change missed',
      status: 'failed',
      detail: 'too late',
    })
  })

  it('shows the gate verdict on the helper tool line', () => {
    const store = mockStore()
    applyStreamEvent(
      {
        type: 'subagent_tool',
        agent_id: 'h1',
        tool: 'write_file',
        args_preview: 'docs/x.md',
        gate: '[gate] outside this helper whitelist',
      },
      store,
    )
    expect(store.upsertActivity).toHaveBeenLastCalledWith({
      label: 'SubAgent h1',
      status: 'running',
      detail: '[gate] outside this helper whitelist · write_file: docs/x.md',
    })
  })
})
