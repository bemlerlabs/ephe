import { describe, it, expect, vi, beforeEach } from 'vitest'

type SyncCallPayload = {
  sessions: { id: string; messages: { role: string }[] }[]
  deleted: string[]
}

function firstCallPayload(): SyncCallPayload {
  const [call] = syncMock.mock.calls
  if (!call) throw new Error('expected one sync call')
  return call[0] as SyncCallPayload
}

function allCallPayloads(): SyncCallPayload[] {
  return syncMock.mock.calls.map((c) => c[0] as SyncCallPayload)
}
import type { DbSession } from '@/types'

// The sync client is the only network boundary — mock it wholesale.
const syncMock = vi.hoisted(() => vi.fn())
vi.mock('@/lib/api', () => ({ syncSessions: syncMock }))

// W4: the drop path reports itself through toast and i18n — both mocked as counters here.
const toastInfo = vi.hoisted(() => vi.fn())
vi.mock('@/lib/toast', () => ({ toastBus: { info: toastInfo, success: vi.fn(), error: vi.fn() } }))
vi.mock('@/i18n', () => ({
  default: {
    t: (key: string, options?: Record<string, unknown>) =>
      options?.count === undefined ? key : `${key}:${String(options.count)}`,
  },
}))

import {
  MAX_SESSIONS_PER_CALL,
  flushSessionSync,
  isSessionSyncEnabled,
  isTombstoned,
  queueSessionDeleted,
  queueSessionSync,
} from '@/lib/sessionSync'

function session(id: string, content = 'hallo welt'): DbSession {
  return {
    id,
    title: `S ${id}`,
    createdAt: 1,
    updatedAt: 2,
    messages: [
      { id: 'm1', role: 'user', content, timestamp: 1 },
      { id: 'm2', role: 'assistant', content: 'antwort', timestamp: 2 },
      { id: 'm3', role: 'bogus', content: 'must be filtered out' } as never,
    ],
  } as DbSession
}

beforeEach(() => {
  syncMock.mockReset()
  syncMock.mockResolvedValue({ stored_sessions: 1, dropped_sessions: 0 })
  localStorage.clear()
  // drain any queue left over from a previous case
  return flushSessionSync().then(() => flushSessionSync())
})

describe('sessionSync (R30)', () => {
  it('syncs a saved session to the server with filtered roles', async () => {
    queueSessionSync(session('s1'))
    await flushSessionSync()
    expect(syncMock).toHaveBeenCalledTimes(1)
    const payload = firstCallPayload()
    expect(payload.sessions[0]?.id).toBe('s1')
    expect(payload.sessions[0]?.messages.map((m) => m.role)).toEqual(['user', 'assistant'])
  })

  it('syncs deletions', async () => {
    queueSessionDeleted('gone')
    await flushSessionSync()
    expect(syncMock).toHaveBeenCalledTimes(1)
    expect(firstCallPayload().deleted).toEqual(['gone'])
  })

  it('does nothing when opted out', async () => {
    localStorage.setItem('ephe.sessions.sync', '0')
    expect(isSessionSyncEnabled()).toBe(false)
    queueSessionSync(session('s2'))
    await flushSessionSync()
    expect(syncMock).not.toHaveBeenCalled()
  })

  it('keeps the queue when the backend is offline (retried later)', async () => {
    syncMock.mockRejectedValueOnce(new Error('offline'))
    queueSessionSync(session('s3'))
    await flushSessionSync() // first flush consumes the rejection, item stays queued
    await flushSessionSync() // second delivers it
    const payloads = allCallPayloads()
    expect(payloads[0]?.sessions[0]?.id).toBe('s3')
    expect(payloads[1]?.sessions[0]?.id).toBe('s3')
    // after the successful flush the queue is drained: a bare flush sends nothing
    await flushSessionSync()
    expect(syncMock).toHaveBeenCalledTimes(2)
  })

  it('does not resync an unchanged session after success', async () => {
    queueSessionSync(session('s4'))
    await flushSessionSync()
    await flushSessionSync()
    expect(syncMock).toHaveBeenCalledTimes(1)
  })

  it('writes a tombstone synchronously on delete and clears it after the flush', async () => {
    // R-Fix Bug 1: the tombstone is there IMMEDIATELY (synchronously), before the
    // debounced flush runs — that is how it survives a hard reload before the 5s.
    queueSessionDeleted('d1')
    expect(isTombstoned('d1')).toBe(true)
    // After a successful flush the mirror delete is confirmed → tombstone gone.
    await flushSessionSync()
    expect(isTombstoned('d1')).toBe(false)
  })

  it('keeps the tombstone when the delete flush is offline (retried later)', async () => {
    syncMock.mockRejectedValueOnce(new Error('offline'))
    queueSessionDeleted('d2')
    await flushSessionSync() // the first flush fails, the tombstone stays
    expect(isTombstoned('d2')).toBe(true)
    await flushSessionSync() // the second delivers — confirmed now
    expect(isTombstoned('d2')).toBe(false)
  })
})

describe('W4 — a dropped sync reaches the user', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('ephe.sessions.sync', '1')
    toastInfo.mockReset()
    syncMock.mockReset()
  })

  it('names a server that drops tasks', async () => {
    syncMock.mockResolvedValue({ stored_sessions: 1, dropped_sessions: 2 })
    queueSessionSync(session('a'))
    await flushSessionSync()
    expect(toastInfo).toHaveBeenCalledTimes(1)
    expect(toastInfo.mock.calls[0]?.[0]).toBe('sync.droppedTitle')
    expect(toastInfo.mock.calls[0]?.[1]).toBe('sync.droppedBody:2')
  })

  it('stays silent on a complete transfer', async () => {
    syncMock.mockResolvedValue({ stored_sessions: 1, dropped_sessions: 0 })
    queueSessionSync(session('b'))
    await flushSessionSync()
    expect(toastInfo).not.toHaveBeenCalled()
  })
})

// R6/S1: the mirror was a text transcript. Per message the sender carried only
// role/content/timestamp/blocks/thinkingPhases — tool calls, activities,
// artifact links and the turn anchor stayed home. After a cache clear, or on a
// second device, the session was mute: no cards, no way back into the
// workbench. The server has accepted those fields since 2026-10-01 (F-N) — it
// only never asked anyone to send them.
describe('flushSessionSync — the history travels along', () => {
  it('sends tool calls, activities, artifacts and the turn anchor', async () => {
    const reich = session('s-reich')
    reich.messages = [
      { id: 'm1', role: 'user', content: 'bau', timestamp: 1 },
      {
        id: 'm2',
        role: 'assistant',
        content: 'fertig',
        timestamp: 2,
        turnId: 't-1',
        tool_calls: [{ id: 'c1', name: 'run_shell', args: { command: 'ls' }, status: 'ok' }],
        activities: [{ id: 'a1', label: 'ls', status: 'done' }],
        artifacts: [{ id: 'k1', name: 'x.pdf' }],
        durationMs: 900,
      },
    ] as never
    queueSessionSync(reich)
    await flushSessionSync()
    const nachricht = firstCallPayload().sessions[0]!.messages[1] as Record<string, unknown>
    expect(nachricht.turnId).toBe('t-1')
    expect(nachricht.tool_calls).toHaveLength(1)
    expect(nachricht.activities).toHaveLength(1)
    expect(nachricht.artifacts).toHaveLength(1)
    expect(nachricht.durationMs).toBe(900)
  })

  it('sends the session birth alongside its rows', async () => {
    queueSessionSync(session('s-zeit'))
    await flushSessionSync()
    const kopf = firstCallPayload().sessions[0] as Record<string, unknown>
    expect(kopf.created_at).toBe(1)
  })
})

describe('flushSessionSync — no empty shells into the mirror (R6/S3)', () => {
  it('never sends a session without messages', async () => {
    queueSessionSync({ ...session('s-leer'), messages: [] } as DbSession)
    await flushSessionSync()
    expect(syncMock).not.toHaveBeenCalled()
  })
})

// Visibility wave: helper sessions are numerous (one task delegates twenty times
// over) and their durable home is the helper ledger
// (~/.ephe/subagent_history.json), not the session mirror. Sent along they would
// crowd real tasks out of the 50-item restore window, and the restore path would
// pull back half of its own history.
describe('flushSessionSync — helper sessions stay with the ledger', () => {
  it('does not send a helper session into the mirror', async () => {
    queueSessionSync(session('helper-9e8d7c6b', 'Bericht: 30 Sekunden'))
    await flushSessionSync()
    expect(syncMock).not.toHaveBeenCalled()
  })

  it('mixes: a real task goes, the helper stays out', async () => {
    queueSessionSync(session('helper-9e8d7c6b'))
    queueSessionSync(session('s-echt'))
    await flushSessionSync()
    expect(firstCallPayload().sessions.map((s) => s.id)).toEqual(['s-echt'])
  })

  it('a helper delete still clears the mirror', async () => {
    // Deleting is tidying: an old mirror row of the helper (mirrored before this
    // wave) must not come back as a hallucination.
    queueSessionDeleted('helper-9e8d7c6b')
    await flushSessionSync()
    expect(firstCallPayload().deleted).toEqual(['helper-9e8d7c6b'])
  })
})

// W10 blocker: the route caps a single call at MAX_SESSIONS_PER_CALL (50) and
// answers 413 above it, while the flush put the whole pending queue into one
// call. A store of more than 50 pending sessions therefore never drained: every
// flush sent the same oversized batch, the 413 was swallowed, and the queue
// stayed full — new tasks never reached the mirror. The flush now batches to the
// cap, so a store of any size drains.
describe('W10 — a store of more than 50 sessions drains', () => {
  beforeEach(() => {
    localStorage.clear()
    localStorage.setItem('ephe.sessions.sync', '1')
    toastInfo.mockReset()
    syncMock.mockReset()
  })

  /** The route's contract: at most MAX_SESSIONS_PER_CALL sessions, else 413. */
  function enforceServerCap(payload: SyncCallPayload): Promise<{
    stored_sessions: number
    dropped_sessions: number
  }> {
    if (payload.sessions.length > MAX_SESSIONS_PER_CALL) {
      const err = new Error('413 too many sessions per call (max 50)')
      ;(err as Error & { status?: number }).status = 413
      return Promise.reject(err)
    }
    return Promise.resolve({ stored_sessions: payload.sessions.length, dropped_sessions: 0 })
  }

  it('mirrors every pending session in calls that stay within the cap', async () => {
    syncMock.mockImplementation(enforceServerCap)

    const N = 120
    for (let i = 0; i < N; i += 1) queueSessionSync(session(`bulk-${i}`))
    await flushSessionSync()

    const payloads = allCallPayloads()
    expect(payloads.length).toBe(Math.ceil(N / MAX_SESSIONS_PER_CALL))
    expect(payloads.every((p) => p.sessions.length <= MAX_SESSIONS_PER_CALL)).toBe(true)
    const mirrored = payloads.flatMap((p) => p.sessions.map((s) => s.id))
    expect(mirrored).toHaveLength(N)
    expect(new Set(mirrored).size).toBe(N)

    // drained: a second flush has nothing left to send
    syncMock.mockClear()
    await flushSessionSync()
    expect(syncMock).not.toHaveBeenCalled()
  })

  it('keeps the unconfirmed tail queued after a mid-drain failure, then finishes it', async () => {
    // batch 1 lands, the next call is offline: the drain is left partway —
    // the remainder is retried on the next flush and the store finally drains.
    let call = 0
    syncMock.mockImplementation((payload: SyncCallPayload) => {
      if (payload.sessions.length > MAX_SESSIONS_PER_CALL) {
        return Promise.reject(new Error('413 too many sessions per call (max 50)'))
      }
      call += 1
      if (call === 2) return Promise.reject(new Error('offline'))
      return Promise.resolve({ stored_sessions: payload.sessions.length, dropped_sessions: 0 })
    })

    const N = 120
    for (let i = 0; i < N; i += 1) queueSessionSync(session(`tail-${i}`))
    await flushSessionSync()
    const firstAttempts = allCallPayloads()
    // batch 1 (confirmed) + the batch that hit the offline error — both bounded by the cap
    expect(firstAttempts).toHaveLength(2)
    expect(firstAttempts.every((p) => p.sessions.length <= MAX_SESSIONS_PER_CALL)).toBe(true)

    // the unconfirmed tail is retried and the store finally drains
    syncMock.mockClear()
    syncMock.mockImplementation(enforceServerCap)
    await flushSessionSync()
    const afterSecond = allCallPayloads().flatMap((p) => p.sessions.map((s) => s.id))
    expect(afterSecond).toHaveLength(N - MAX_SESSIONS_PER_CALL)
    const everything = new Set([
      ...firstAttempts.flatMap((p) => p.sessions.map((s) => s.id)),
      ...afterSecond,
    ])
    expect(everything.size).toBe(N)

    syncMock.mockClear()
    await flushSessionSync()
    expect(syncMock).not.toHaveBeenCalled()
  })
})
