/**
 * I6 P2b — stop/reload must not destroy a partial answer.
 *
 * Root cause (deep test 2026-09-08): debouncedSaveSession re-arms on every chunk
 * and never fires when the stream stops just before a reload — the IndexedDB then
 * keeps the ensure snapshot (content empty, streaming=true) and the reload shows a
 * zombie bubble instead of the partial state. Remedy: an explicit flush point
 * (flushPendingSave) that takes over at turn end (finishTurn/markStreamError) and
 * when the tab changes.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const sync = vi.hoisted(() => ({ queued: [] as unknown[], deleted: [] as string[] }))

// IEDBdb.ts first calls the server sync inside dbSaveSession (fire-and-forget) —
// through this mock we observe HERE when a persist really writes.
const flushMirror = vi.hoisted(() => vi.fn())

vi.mock('@/lib/sessionSync', () => ({
  queueSessionSync: (session: unknown) => sync.queued.push(session),
  queueSessionDeleted: (id: string) => sync.deleted.push(id),
  flushSessionSyncNow: flushMirror,
}))

import { debouncedSaveSession, flushPendingSave } from './db'
import type { DbSession } from '@/types'

const session = (id: string): DbSession => ({
  id,
  title: id,
  messages: [],
  createdAt: 1,
  updatedAt: 2,
})

describe('db.flushPendingSave (I6 P2b)', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    sync.queued.length = 0
    sync.deleted.length = 0
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('debouncedSaveSession schreibt erst nach Ablauf der Verzögerung (Baseline)', () => {
    debouncedSaveSession(session('s1'))
    vi.advanceTimersByTime(1000)
    expect(sync.queued).toHaveLength(0)
    vi.advanceTimersByTime(1000)
    expect(sync.queued).toEqual([session('s1')])
  })

  it('flushPendingSave schreibt den ausstehenden Stand sofort und storniert den Timer', () => {
    debouncedSaveSession(session('s2'))
    flushPendingSave()
    expect(sync.queued).toEqual([session('s2')])
    vi.advanceTimersByTime(5000)
    expect(sync.queued).toHaveLength(1)
  })

  it('flushPendingSave ohne ausstehenden Schreib schreibt nichts, flusht aber den Spiegel', () => {
    flushMirror.mockClear()
    flushPendingSave()
    vi.advanceTimersByTime(5000)
    expect(sync.queued).toHaveLength(0)
    // The turn may have saved through dbSaveSession directly; its queued mirror
    // write must not wait for a timer the unload will kill.
    expect(flushMirror).toHaveBeenCalledTimes(1)
  })

  it('Spaeltere flush nach bereits erfolgtem Timer-Lauf schreibt nicht erneut', () => {
    debouncedSaveSession(session('s3'))
    vi.advanceTimersByTime(2000)
    expect(sync.queued).toHaveLength(1)
    flushPendingSave()
    expect(sync.queued).toHaveLength(1)
  })

  it('Spaelterer debouncedSaveSession ersetzt den ausstehenden Stand (latest wins)', () => {
    debouncedSaveSession(session('alt'))
    debouncedSaveSession(session('neu'))
    flushPendingSave()
    expect(sync.queued).toEqual([session('neu')])
  })
})
