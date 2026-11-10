/**
 * Race proof: the asynchronous initFromDb hydrate must not reset a composer mode
 * set by a click JUST NOW back to the older persisted snapshot.
 *
 * Task 3 join: the same hydrate is where the one-time rewrite of stored legacy
 * mode values runs (ask | plan | full-access → canonical key; a stored
 * edit-auto keeps its wire value, see the equivalence test below). The
 * memory-first rule above and the rewrite below share the exact line — mem wins,
 * then the winner is mapped onto its canonical mode, so neither path can leave
 * a migratable legacy value in the store.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const dbMock = vi.hoisted(() => ({
  sessionsToReturn: [] as unknown[],
  saved: [] as Array<Record<string, unknown>>,
}))

vi.mock('@/lib/db', () => ({
  dbGetAllSessions: async () => dbMock.sessionsToReturn,
  dbDeleteSession: async () => {},
  dbSaveSession: async () => {},
  debouncedSaveSession: (d: Record<string, unknown>) => {
    dbMock.saved.push(d)
  },
  flushPendingSave: () => {},
  dbGetCheckpoints: async () => [],
  dbSaveCheckpoints: async () => {},
}))
vi.mock('@/lib/restore', () => ({
  restoreFromServer: async () => [],
  restoreServerStore: async () => [],
}))
vi.mock('@/lib/sessionSync', () => ({
  queueSessionSync: () => {},
  queueSessionDeleted: () => {},
  isTombstoned: () => false,
  isSessionSyncEnabled: () => false,
}))
// The approval profile is a device-global security setting. The hydrate reads
// the session list on every boot, so the mock records every call to its
// endpoints and the tests below refuse one: loading a list must not change the
// pairing of the sessions that are in no list.
const apiMock = vi.hoisted(() => ({
  getSecuritySettings: vi.fn(async () => ({ approval_profile: 'full', sandbox_enabled: false })),
  saveSecuritySettings: vi.fn(async () => ({
    approval_profile: 'session',
    sandbox_enabled: false,
  })),
}))
vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  getSecuritySettings: apiMock.getSecuritySettings,
  saveSecuritySettings: apiMock.saveSecuritySettings,
}))

import { useChatStore } from './chatStore'

beforeEach(() => {
  dbMock.sessionsToReturn = []
  dbMock.saved = []
  apiMock.getSecuritySettings.mockClear()
  apiMock.saveSecuritySettings.mockClear()
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
  it('In-Memory operator bleibt nach spaeter eintreffender Hydrate (DB=analyst)', async () => {
    // Persist snapshot: mode 'analyst' (already canonical).
    dbMock.sessionsToReturn = [
      { id: 's', title: 'S', messages: [], createdAt: 1000, updatedAt: 1000, mode: 'analyst' },
    ]
    // In memory already active with a freshly chosen operator (click before the hydrate finished).
    useChatStore.setState({
      sessions: [{ id: 's', title: 'S', messages: [], createdAt: 1000, mode: 'operator' }],
      activeSessionId: 's',
      currentSession: { id: 's', title: 'S', messages: [], createdAt: 1000, mode: 'operator' },
    } as never)
    await useChatStore.getState().initFromDb()
    const s = useChatStore.getState()
    expect(s.sessions.find((x) => x.id === 's')?.mode).toBe('operator')
    expect(s.currentSession?.mode).toBe('operator')
    expect(s.activeSessionId).toBe('s')
  })

  it('ohne in-memory Modus gilt der Persist-Snapshot — auf dem kanonischen Schluessel', async () => {
    dbMock.sessionsToReturn = [
      { id: 's', title: 'S', messages: [], createdAt: 1000, updatedAt: 1000, mode: 'ask' },
    ]
    await useChatStore.getState().initFromDb()
    // The stored legacy value is rewritten once to its canonical key…
    expect(useChatStore.getState().sessions.find((x) => x.id === 's')?.mode).toBe('analyst')
    // …and the rewrite is persisted, so it happens on this load only.
    expect(dbMock.saved.find((d) => d.id === 's')?.mode).toBe('analyst')
  })

  it('stored full-access becomes operator; a stored agent stays untouched', async () => {
    dbMock.sessionsToReturn = [
      { id: 'a', title: 'A', messages: [], createdAt: 1000, updatedAt: 1000, mode: 'full-access' },
      // 'agent' is the legacy all-factors wire value: tools available, manual
      // approvals. Analyst runs no tools — rewriting it would strip the session.
      { id: 'b', title: 'B', messages: [], createdAt: 1000, updatedAt: 1000, mode: 'agent' },
    ]
    await useChatStore.getState().initFromDb()
    const st = useChatStore.getState()
    expect(st.sessions.find((x) => x.id === 'a')?.mode).toBe('operator')
    expect(st.sessions.find((x) => x.id === 'b')?.mode).toBe('agent')
    expect(dbMock.saved.find((d) => d.id === 'b')).toBeUndefined()
  })

  it('a stored edit-auto stays stored and goes back to the wire unchanged', async () => {
    // Per-profile equivalence, client half (server half:
    // tests/test_composer_mode_rename.py). The retired mode ran the edit family
    // silently and asked for the rest; the server alias table still gives the
    // stored value that behaviour, so the hydrate leaves it exactly as stored —
    // under strict, session, plan or full alike. A rewrite onto the Operator
    // tile would auto-approve every tool where the session used to be asked.
    dbMock.sessionsToReturn = [
      { id: 'e', title: 'E', messages: [], createdAt: 1000, updatedAt: 1000, mode: 'edit-auto' },
    ]
    await useChatStore.getState().initFromDb()
    expect(useChatStore.getState().sessions.find((x) => x.id === 'e')?.mode).toBe('edit-auto')
    // Nothing was rewritten, so nothing was saved back.
    expect(dbMock.saved.find((d) => d.id === 'e')).toBeUndefined()
    // And the hydrate never touches the device-global approval profile.
    await new Promise((r) => setTimeout(r, 0))
    expect(apiMock.getSecuritySettings).not.toHaveBeenCalled()
    expect(apiMock.saveSecuritySettings).not.toHaveBeenCalled()
  })

  it('the migratable rewrite leaves the profile alone too', async () => {
    dbMock.sessionsToReturn = [
      { id: 's', title: 'S', messages: [], createdAt: 1000, updatedAt: 1000, mode: 'full-access' },
    ]
    await useChatStore.getState().initFromDb()
    await new Promise((r) => setTimeout(r, 0))
    expect(apiMock.getSecuritySettings).not.toHaveBeenCalled()
    expect(apiMock.saveSecuritySettings).not.toHaveBeenCalled()
  })
})
