/**
 * IndexedDB schema live test (finding 2026-10-02).
 *
 * jsdom brings no real IndexedDB, which is why the upgrade path of
 * openDb() never ran through a test before — that is exactly where the defect sat: a
 * separate db.transaction() inside onupgradeneeded aborts the versionchange tx,
 * the 'sessions' store never came into existence and every dbSaveSession failed
 * (silently, in the try/catch). fake-indexeddb enforces the same spec and catches
 * this error-class case.
 */
import 'fake-indexeddb/auto'
import { IDBFactory } from 'fake-indexeddb'
import { describe, it, expect, beforeEach, vi } from 'vitest'

// sessionSync -> @/lib/api (syncSessions) keeps the test network-free.
vi.mock('@/lib/api', () => ({
  syncSessions: vi.fn(async () => ({ stored_sessions: 0, dropped_sessions: 0 })),
}))

import { dbSaveSession, dbGetSession, dbGetAllSessions, dbDeleteSession } from '@/lib/db'
import type { DbSession } from '@/types'

function session(id: string, extra: Partial<DbSession> = {}): DbSession {
  return {
    id,
    title: `T-${id}`,
    messages: [{ id: 'm1', role: 'user', content: 'hi', timestamp: 1 } as never],
    createdAt: 1,
    updatedAt: 2,
    ...extra,
  }
}

describe('IndexedDB openDb + CRUD (Schema-Regression)', () => {
  beforeEach(() => {
    // Fresh factory state per case -> onupgradeneeded runs again every time.
    globalThis.indexedDB = new IDBFactory()
  })

  it('legt den sessions-Store an und speichert/liest eine Session zurueck', async () => {
    await dbSaveSession(session('a1'))
    const back = await dbGetSession('a1')
    // Before the fix: the save was swallowed, get returns null -> store missing.
    expect(back).not.toBeNull()
    expect(back?.id).toBe('a1')
    expect(back?.title).toBe('T-a1')
  })

  it('erhaelt parentId durch den IndexedDB-Roundtrip (Sitzungs-Baum)', async () => {
    await dbSaveSession(session('child', { parentId: 'parent' }))
    const back = await dbGetSession('child')
    expect(back?.parentId).toBe('parent')
  })

  it('getAll liefert alle gespeicherten Sessions', async () => {
    await dbSaveSession(session('x'))
    await dbSaveSession(session('y'))
    const all = await dbGetAllSessions()
    expect(all.map((s) => s.id).sort()).toEqual(['x', 'y'])
  })

  it('Delete entfernt die Session', async () => {
    await dbSaveSession(session('z'))
    await dbDeleteSession('z')
    expect(await dbGetSession('z')).toBeNull()
  })
})
