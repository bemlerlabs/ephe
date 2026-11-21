/**
 * Chat trash at the store layer — one click on delete is not the last word.
 *
 * Pins:
 * 1. `deleteSession` moves the durable copy aside with POST …/trash (the `pwa-`
 *    mirror file the sync owns) and answers with a toast whose action undoes it;
 *    the local half — store removal, IndexedDB, the active-session switch — is
 *    untouched by the new call.
 * 2. The undo drains the pending mirror delete BEFORE the restore: a flush
 *    after the restore would name the file the restore just brought back and
 *    unlink it.
 * 3. A refusing restore surfaces its reason in an error toast, and the session
 *    is not resurrected behind it.
 * 4. A session the store never held answers 404: no toast, the local delete
 *    still stands — same end state as before this path existed.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'

const apiMock = vi.hoisted(() => {
  class ApiError extends Error {
    status: number
    reasonCode: string
    payload: unknown
    constructor(message: string, status = 0, reasonCode = '', payload: unknown = null) {
      super(message)
      this.name = 'ApiError'
      this.status = status
      this.reasonCode = reasonCode
      this.payload = payload
    }
  }
  return {
    ApiError,
    trash: vi.fn(),
    restore: vi.fn(),
    order: [] as string[],
  }
})
const dbMock = vi.hoisted(() => ({
  deleted: [] as string[],
  saved: [] as unknown[],
}))
const syncMock = vi.hoisted(() => ({
  flushes: 0,
}))
const toastMock = vi.hoisted(() => ({
  calls: [] as Array<{
    kind: string
    title: string
    description?: string
    action?: { label: string; onClick: () => void }
  }>,
}))

vi.mock('@/lib/api', () => ({
  ApiError: apiMock.ApiError,
  trashSession: (id: string) => {
    apiMock.order.push('trash')
    return apiMock.trash(id)
  },
  restoreTrashedSession: (id: string) => {
    apiMock.order.push('restore')
    return apiMock.restore(id)
  },
}))
vi.mock('@/lib/db', () => ({
  dbGetAllSessions: async () => [],
  dbDeleteSession: async (id: string) => {
    dbMock.deleted.push(id)
  },
  dbSaveSession: async (d: unknown) => {
    dbMock.saved.push(d)
  },
  debouncedSaveSession: () => {},
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
  isSessionSyncEnabled: () => true,
  isTombstoned: () => false,
  flushSessionSync: async () => {
    syncMock.flushes += 1
    apiMock.order.push('flush')
  },
}))
vi.mock('@/lib/toast', () => ({
  toastBus: {
    info: () => {},
    success: (
      title: string,
      description?: string,
      action?: { label: string; onClick: () => void },
    ) => toastMock.calls.push({ kind: 'success', title, description, action }),
    error: (title: string, description?: string, action?: { label: string; onClick: () => void }) =>
      toastMock.calls.push({ kind: 'error', title, description, action }),
    subscribe: () => () => {},
  },
}))

import { useChatStore } from './chatStore'
import type { Session } from '@/types'

function session(id: string, title = 'Recherche'): Session {
  return {
    id,
    title,
    messages: [{ id: 'm1', role: 'user', content: `msg-${id}`, timestamp: 1 }],
    createdAt: 1000,
  }
}

function seed(...sessions: Session[]) {
  const first = sessions[0] ?? null
  useChatStore.setState({
    sessions,
    activeSessionId: first?.id ?? null,
    currentSession: first,
    checkpoints: {},
    hydrated: true,
  })
}

beforeEach(() => {
  apiMock.trash.mockReset()
  apiMock.restore.mockReset()
  apiMock.order.length = 0
  dbMock.deleted.length = 0
  dbMock.saved.length = 0
  syncMock.flushes = 0
  toastMock.calls.length = 0
  apiMock.trash.mockResolvedValue({
    trashed: 'pwa-a',
    run: '20261114T120000Z',
    trashed_at: '2026-11-14T12:00:00+00:00',
    bytes_moved: 1024,
  })
  apiMock.restore.mockResolvedValue({ restored: 'pwa-a', run: '20261114T120000Z' })
  seed(session('a'))
})

describe('deleteSession → trash → undo', () => {
  it('moves the durable copy to the trash and keeps the working local half', async () => {
    useChatStore.getState().deleteSession('a')

    // The local half is synchronous and unchanged: out of the list, out of the cache.
    const s = useChatStore.getState()
    expect(s.sessions).toHaveLength(0)
    expect(s.activeSessionId).toBeNull()
    expect(s.currentSession).toBeNull()
    expect(dbMock.deleted).toEqual(['a'])

    await vi.waitFor(() => expect(apiMock.trash).toHaveBeenCalledWith('pwa-a'))

    // The success toast carries the way back.
    const toast = toastMock.calls.find((c) => c.kind === 'success')
    expect(toast).toBeTruthy()
    expect(toast!.action?.label).toBeTruthy()
    expect(toast!.description).toBeUndefined()
  })

  it('the undo drains the pending mirror delete first, then restores and re-adds', async () => {
    useChatStore.getState().deleteSession('a')
    await vi.waitFor(() => expect(apiMock.trash).toHaveBeenCalledWith('pwa-a'))

    const toast = toastMock.calls.find((c) => c.kind === 'success')!
    toast.action!.onClick()

    await vi.waitFor(() => expect(apiMock.restore).toHaveBeenCalledWith('pwa-a'))
    // flush → restore, never restore → flush: the flush names the file the
    // restore brings back, so it has to run while that file still lies in the trash.
    expect(apiMock.order).toEqual(['trash', 'flush', 'restore'])
    expect(syncMock.flushes).toBe(1)

    await vi.waitFor(() => expect(useChatStore.getState().sessions.map((x) => x.id)).toEqual(['a']))
    expect(useChatStore.getState().sessions[0]!.title).toBe('Recherche')
    // And back into the cache, so a reload finds it even before the mirror does.
    expect(dbMock.saved.map((d) => (d as { id: string }).id)).toEqual(['a'])
  })

  it('a refusing restore names its reason and leaves the session deleted', async () => {
    useChatStore.getState().deleteSession('a')
    await vi.waitFor(() => expect(apiMock.trash).toHaveBeenCalled())

    apiMock.restore.mockRejectedValue(
      new apiMock.ApiError('A live session already carries the id', 409, 'session_exists'),
    )
    const toast = toastMock.calls.find((c) => c.kind === 'success')!
    toast.action!.onClick()

    await vi.waitFor(() => expect(toastMock.calls.some((c) => c.kind === 'error')).toBe(true))
    const errToast = toastMock.calls.find((c) => c.kind === 'error')!
    // The reason text itself, not a generic failure.
    expect(errToast.description).toContain('A live session already carries the id')
    expect(useChatStore.getState().sessions).toHaveLength(0)
    expect(dbMock.saved).toHaveLength(0)
  })

  it('a session the store never held: 404, no toast, the local delete still stands', async () => {
    apiMock.trash.mockRejectedValue(new apiMock.ApiError('no such file', 404, 'session_not_found'))
    useChatStore.getState().deleteSession('a')
    await vi.waitFor(() => expect(apiMock.trash).toHaveBeenCalledWith('pwa-a'))

    await vi.waitFor(() => expect(useChatStore.getState().sessions).toHaveLength(0))
    expect(toastMock.calls).toHaveLength(0)
    expect(dbMock.deleted).toEqual(['a'])
  })
})
