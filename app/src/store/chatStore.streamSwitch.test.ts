/**
 * Live-test finding: leaving a task while its answer is still arriving sent the
 * rest of that answer into the task that was opened next, and left the first one
 * with a bubble that never stopped streaming.
 *
 * GIVEN  a turn is streaming in session A
 * WHEN   the reader switches to session B and the next chunk arrives
 * THEN   the chunk lands in A, B stays as it was, and the screen keeps showing B
 * AND    finishTurn closes A's bubble and releases the claim on the stream.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { useChatStore } from './chatStore'

function resetStore() {
  useChatStore.setState({
    sessions: [],
    activeSessionId: null,
    streamSessionId: null,
    isTyping: false,
    pendingToolCall: null,
    currentSession: null,
    checkpoints: {},
  })
}

const assistantsOf = (id: string) => {
  const session = useChatStore.getState().sessions.find((one) => one.id === id)
  return session?.messages.filter((m) => m.role === 'assistant') ?? []
}

describe('a stream keeps the session that asked (live-test round)', () => {
  beforeEach(resetStore)

  it('writes later chunks into the asking session after a switch', () => {
    useChatStore.getState().createSession()
    const a = useChatStore.getState().activeSessionId as string
    useChatStore.getState().startTurn()
    useChatStore.getState().appendChunk('first ')

    useChatStore.getState().createSession()
    const b = useChatStore.getState().activeSessionId as string
    expect(b).not.toBe(a)

    useChatStore.getState().appendChunk('second half')

    expect(assistantsOf(a).at(-1)?.content).toBe('first second half')
    expect(assistantsOf(b)).toHaveLength(0)
    expect(useChatStore.getState().currentSession?.id).toBe(b)
    expect(useChatStore.getState().streamSessionId).toBe(a)
  })

  it('closes the asking session and lets the next turn claim the stream', () => {
    useChatStore.getState().createSession()
    const a = useChatStore.getState().activeSessionId as string
    useChatStore.getState().startTurn()
    useChatStore.getState().appendChunk('text')
    useChatStore.getState().createSession()
    useChatStore.getState().finishTurn()

    expect(assistantsOf(a).at(-1)?.streaming).toBe(false)
    expect(useChatStore.getState().streamSessionId).toBeNull()

    useChatStore.getState().startTurn()
    expect(useChatStore.getState().streamSessionId).toBe(useChatStore.getState().activeSessionId)
  })

  it('an error after a switch still belongs to the asking session', () => {
    useChatStore.getState().createSession()
    const a = useChatStore.getState().activeSessionId as string
    useChatStore.getState().startTurn()
    useChatStore.getState().appendChunk('partial')
    useChatStore.getState().createSession()
    const b = useChatStore.getState().activeSessionId as string
    useChatStore.getState().markStreamError('aborted', 'engine_error')

    const failed = assistantsOf(a).at(-1)
    expect(failed?.error).toBe('aborted')
    expect(failed?.streaming).toBe(false)
    expect(assistantsOf(b)).toHaveLength(0)
    expect(useChatStore.getState().streamSessionId).toBeNull()
  })
})
