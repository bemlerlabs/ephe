/**
 * I6 P2b — turn end must push the pending persist write through.
 *
 * Regression pins against the deep-test finding 2026-09-08 ("Stop discards
 * partial text"): after stop + reload half the assistant answer was gone, because
 * the debounced persist was never flushed and the very first (empty) snapshot
 * stayed in the IndexedDB.
 *
 * Pins:
 * 1. finishTurn calls flushPendingSave (stop path → the partial text survives).
 * 2. markStreamError calls flushPendingSave (error path → text so far survives).
 * 3. initFromDb heals orphaned streaming bubbles: a reload NEVER finds a
 *    continued stream — streaming=true plus running activities must not come back
 *    as a zombie spinner; rescued text stays where it is.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const dbMock = vi.hoisted(() => ({
  flushCalls: 0,
  sessionsToReturn: [] as unknown[],
}))

vi.mock('@/lib/db', () => ({
  dbGetAllSessions: async () => dbMock.sessionsToReturn,
  dbDeleteSession: async () => {},
  debouncedSaveSession: () => {},
  flushPendingSave: () => {
    dbMock.flushCalls += 1
  },
  dbGetCheckpoints: async () => [],
  dbSaveCheckpoints: async () => {},
}))
vi.mock('@/lib/sessionSync', () => ({
  queueSessionSync: () => {},
  queueSessionDeleted: () => {},
}))

import { useChatStore } from './chatStore'

function resetStore() {
  useChatStore.setState({
    sessions: [],
    activeSessionId: null,
    isTyping: false,
    pendingToolCall: null,
    currentSession: null,
    checkpoints: {},
  })
}

function lastAssistant() {
  const cs = useChatStore.getState().currentSession!
  const msgs = cs.messages.filter((m) => m.role === 'assistant')
  if (msgs.length === 0) throw new Error('keine Assistant-Message')
  return msgs[msgs.length - 1]!
}

describe('chatStore Persist-Flush am Turn-Ende (I6 P2b)', () => {
  beforeEach(() => {
    resetStore()
    dbMock.flushCalls = 0
    dbMock.sessionsToReturn = []
    useChatStore.getState().createSession('Stop-Persist')
  })

  it('finishTurn flushed den ausstehenden Persist-Schreib (Stop-Partial bleibt erhalten)', () => {
    useChatStore.getState().addMessage('user', 'prompt')
    useChatStore.getState().startTurn()
    useChatStore.getState().appendChunk('halbe antwort, noch nicht fertig')
    dbMock.flushCalls = 0 // only the finish call counts
    useChatStore.getState().finishTurn()
    expect(dbMock.flushCalls).toBeGreaterThan(0)
    expect(lastAssistant().content).toContain('halbe antwort')
  })

  it('markStreamError flushed ebenfalls (Fehlerpfad rettet den bissherigen Text)', () => {
    useChatStore.getState().startTurn()
    useChatStore.getState().appendChunk('vor dem fehler')
    dbMock.flushCalls = 0
    useChatStore.getState().markStreamError('verbindung getrennt')
    expect(dbMock.flushCalls).toBeGreaterThan(0)
    expect(lastAssistant().content).toContain('vor dem fehler')
  })

  it('initFromDb heilt orphaned streaming-Bubbles statt Zombie-Spinner', async () => {
    dbMock.sessionsToReturn = [
      {
        id: 'z1',
        title: 'Zombie',
        createdAt: 1,
        updatedAt: 2,
        messages: [
          { id: 'u1', role: 'user', content: 'prompt', timestamp: 1 },
          {
            id: 'a1',
            role: 'assistant',
            content: 'GERETTETER PARTIAL',
            timestamp: 2,
            streaming: true,
            thinking: { start: 1, end: null },
            activities: [{ id: 'act1', label: 'x', status: 'running' }],
          },
        ],
      },
    ]
    await useChatStore.getState().initFromDb()
    const a = lastAssistant()
    expect(a.content).toBe('GERETTETER PARTIAL')
    expect(a.streaming).toBe(false)
    expect(a.thinking?.end).toBeTypeOf('number')
    expect(a.activities?.[0]?.status).toBe('done')
    expect(useChatStore.getState().isTyping).toBe(false)
  })
})
