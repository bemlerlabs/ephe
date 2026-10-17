/**
 * Restore-on-empty — P0 fix from the power-user live test 2026-09-11.
 *
 * Finding: after a reload with a lost browser cache (storage eviction, a fresh
 * browser) the sidebar read "No sessions yet", although every session lay on the
 * machine's own disk as pwa-*.json (the sync mirror). The store loaded from
 * IndexedDB only — no server fallback.
 *
 * W19: the server copy (~/.ephe/sessions/) is the primary store per device, the
 * browser is only a cache — so initFromDb ALWAYS merges with the mirror.
 *
 * Pins:
 * 1. Empty IndexedDB → everything from the mirror comes in and is mirrored back.
 * 2. Local sessions stay; only mirror sessions that are MISSING locally are added
 *    (no overwriting, no duplicates) and re-mirrored.
 * 3. A failed merge (offline) stays silent — the local state is enough.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const dbMock = vi.hoisted(() => ({
  sessionsToReturn: [] as unknown[],
  saved: [] as unknown[],
}))
const restoreMock = vi.hoisted(() => ({
  sessions: [] as unknown[],
  calls: 0,
  shouldThrow: false,
}))
const tombstonesMock = vi.hoisted(() => ({
  list: [] as string[],
}))

vi.mock('@/lib/db', () => ({
  dbGetAllSessions: async () => dbMock.sessionsToReturn,
  dbDeleteSession: async () => {},
  dbSaveSession: async (d: unknown) => {
    dbMock.saved.push(d)
  },
  debouncedSaveSession: () => {},
  flushPendingSave: () => {},
  dbGetCheckpoints: async () => [],
  dbSaveCheckpoints: async () => {},
}))
vi.mock('@/lib/restore', () => ({
  restoreFromServer: async () => {
    restoreMock.calls += 1
    if (restoreMock.shouldThrow) throw new Error('offline')
    return restoreMock.sessions
  },
}))
vi.mock('@/lib/sessionSync', () => ({
  queueSessionSync: () => {},
  queueSessionDeleted: () => {},
  isTombstoned: (id: string) => (tombstonesMock.list ?? []).includes(id),
}))

import { useChatStore } from './chatStore'

function dbSession(id: string, title: string, updatedAt = 2000) {
  return {
    id,
    title,
    messages: [{ role: 'user', content: `msg-${id}`, timestamp: 1 }],
    createdAt: 1000,
    updatedAt,
  }
}

function resetStore() {
  dbMock.sessionsToReturn = []
  dbMock.saved = []
  restoreMock.sessions = []
  restoreMock.calls = 0
  restoreMock.shouldThrow = false
  tombstonesMock.list = []
  useChatStore.setState({
    sessions: [],
    activeSessionId: null,
    isTyping: false,
    pendingToolCall: null,
    currentSession: null,
    hydrated: false,
    checkpoints: {},
  })
}

describe('initFromDb restore-on-empty', () => {
  beforeEach(resetStore)

  it('hydrates from the server mirror when IndexedDB is empty and re-mirrors', async () => {
    restoreMock.sessions = [dbSession('a', 'What can you do?'), dbSession('b', 'Pitchdeck')]
    await useChatStore.getState().initFromDb()
    const s = useChatStore.getState()
    expect(s.sessions.map((x) => x.id)).toEqual(['a', 'b'])
    expect(s.activeSessionId).toBe('a')
    expect(dbMock.saved.map((d) => (d as { id: string }).id)).toEqual(['a', 'b'])
  })

  it('P1-10: hydrated startet false und wird nach initFromDb true (Erfolg)', async () => {
    expect(useChatStore.getState().hydrated).toBe(false)
    restoreMock.sessions = [dbSession('a', 'x')]
    await useChatStore.getState().initFromDb()
    expect(useChatStore.getState().hydrated).toBe(true)
  })

  it('P1-10: hydrated wird auch true, wenn alles leer/offline ist (kein Skeleton-Loch)', async () => {
    restoreMock.shouldThrow = true
    await useChatStore.getState().initFromDb()
    expect(useChatStore.getState().hydrated).toBe(true)
  })

  it('merges only missing mirror sessions into a non-empty local store', async () => {
    dbMock.sessionsToReturn = [dbSession('local', 'Lokal')]
    restoreMock.sessions = [
      dbSession('local', 'Lokal bleibt'),
      dbSession('server1', 'Vom Server', 3000),
    ]
    await useChatStore.getState().initFromDb()
    const s = useChatStore.getState()
    expect(s.sessions.map((x) => x.id)).toEqual(['server1', 'local']) // sorted by updatedAt
    expect(s.sessions.find((x) => x.id === 'local')!.title).toBe('Lokal') // not overwritten
    expect(dbMock.saved.map((d) => (d as { id: string }).id)).toEqual(['server1']) // only the missing ones re-mirrored
  })

  it('stays silent when the server restore fails (offline)', async () => {
    restoreMock.shouldThrow = true
    await useChatStore.getState().initFromDb()
    const s = useChatStore.getState()
    expect(s.sessions).toHaveLength(0)
    expect(s.currentSession).toBeNull()
  })

  it('does not resurrect a tombstoned (locally deleted) session from the mirror', async () => {
    // R-fix bug 1: the session was deleted locally (tombstone set) and the mirror
    // delete is not confirmed yet. The mirror still holds it — it must NOT come
    // back.
    tombstonesMock.list = ['gone']
    dbMock.sessionsToReturn = [dbSession('keep', 'Lokal')]
    restoreMock.sessions = [dbSession('keep', 'Lokal'), dbSession('gone', 'Geloescht', 3000)]
    await useChatStore.getState().initFromDb()
    const s = useChatStore.getState()
    expect(s.sessions.map((x) => x.id)).toEqual(['keep'])
    expect(s.sessions.find((x) => x.id === 'gone')).toBeUndefined()
    // only the non-tombstoned missing ones get re-mirrored
    expect(dbMock.saved.map((d) => (d as { id: string }).id)).not.toContain('gone')
  })
})
