import { describe, it, expect, vi, beforeEach } from 'vitest'
import { applyStreamEvent } from './streamActions'

/**
 * The `plan` frame of #92 — its own file because the shared mock store lives in
 * streamActions.test.ts, which sits at 386 of the 400-line architecture cap.
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

describe('applyStreamEvent — plan frame', () => {
  let store: ReturnType<typeof mockStore>

  beforeEach(() => {
    store = mockStore()
  })

  it('maps the frame steps onto the card statuses and derives the counts', () => {
    applyStreamEvent(
      {
        type: 'plan',
        state: 'running',
        done: 1,
        total: 3,
        steps: [
          { title: 'Read routes', status: 'done' },
          { title: 'Add case', status: 'running' },
          { title: 'Run tests', status: 'pending' },
        ],
      },
      store,
    )
    expect(store.setPlan).toHaveBeenCalledWith({
      done: 1,
      total: 3,
      items: [
        { status: 'done', text: 'Read routes' },
        { status: 'active', text: 'Add case' },
        { status: 'pending', text: 'Run tests' },
      ],
    })
  })

  it('fires no action for a frame with no steps: an empty list is no plan', () => {
    applyStreamEvent({ type: 'plan', state: 'draft', done: 0, total: 0, steps: [] }, store)
    expect(store.setPlan).not.toHaveBeenCalled()
  })
})
