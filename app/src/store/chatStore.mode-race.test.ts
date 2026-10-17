/**
 * Race proof: the asynchronous initFromDb hydrate must not reset a composer mode
 * set by a click JUST NOW back to the older persisted snapshot.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const dbMock = vi.hoisted(() => ({ sessionsToReturn: [] as unknown[] }))

vi.mock('@/lib/db', () => ({
  dbGetAllSessions: async () => dbMock.sessionsToReturn,
  dbDeleteSession: async () => {},
  dbSaveSession: async () => {},
  debouncedSaveSession: () => {},
  flushPendingSave: () => {},
  dbGetCheckpoints: async () => [],
  dbSaveCheckpoints: async () => {},
}))
vi.mock('@/lib/restore', () => ({ restoreFromServer: async () => [] }))
vi.mock('@/lib/sessionSync', () => ({
  queueSessionSync: () => {},
  queueSessionDeleted: () => {},
  isTombstoned: () => false,
}))

import { useChatStore } from './chatStore'

beforeEach(() => {
  dbMock.sessionsToReturn = []
  useChatStore.setState({
    sessions: [],
    activeSessionId: null,
    currentSession: null,
    isTyping: false,
    pendingToolCall: null,
    checkpoints: {},
  } as never)
})

describe('initFromDb bewahrt den frisch gewaehlten Modus (Race-Fix)', () => {
  it('In-Memory full-access bleibt nach spaeter eintreffender Hydrate (DB=ask)', async () => {
    // Persist snapshot: mode 'ask'.
    dbMock.sessionsToReturn = [
      { id: 's', title: 'S', messages: [], createdAt: 1000, updatedAt: 1000, mode: 'ask' },
    ]
    // In memory already active with a freshly chosen full-access (click before the hydrate finished).
    useChatStore.setState({
      sessions: [{ id: 's', title: 'S', messages: [], createdAt: 1000, mode: 'full-access' }],
      activeSessionId: 's',
      currentSession: { id: 's', title: 'S', messages: [], createdAt: 1000, mode: 'full-access' },
    } as never)
    await useChatStore.getState().initFromDb()
    const s = useChatStore.getState()
    expect(s.sessions.find((x) => x.id === 's')?.mode).toBe('full-access')
    expect(s.currentSession?.mode).toBe('full-access')
    expect(s.activeSessionId).toBe('s')
  })

  it('ohne in-memory Modus gilt der Persist-Snapshot (ask)', async () => {
    dbMock.sessionsToReturn = [
      { id: 's', title: 'S', messages: [], createdAt: 1000, updatedAt: 1000, mode: 'ask' },
    ]
    await useChatStore.getState().initFromDb()
    expect(useChatStore.getState().sessions.find((x) => x.id === 's')?.mode).toBe('ask')
  })
})
