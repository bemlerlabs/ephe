/**
 * W10-8 — the two boot surfaces the 2026-10-12 walkthrough caught (FINDINGS.md,
 * "Confirmed — high").
 *
 * 1. A message sent during boot was LOST. Three fresh contexts typed and sent the
 *    moment the composer existed; in all three the view ended on an owner session
 *    and the text was nowhere — verdict `message_lost_no_task_carries_the_sent_text`,
 *    the mirror never received it. `handleSend` wrote the bubble into the still-empty
 *    store, then the asynchronous `initFromDb()` settled and replaced
 *    `sessions`/`activeSessionId`/`currentSession`. The send now waits for the
 *    hydrate, says so out loud and replays into the task it was typed in.
 *
 * 2. A cold open settles on another task's restored transcript (~50 rows) and no
 *    surface said so. Both halves of that moment are disclosed now.
 *
 * The real store runs here (only persistence is mocked), so the clobber in
 * `store/chat/session.ts::initFromDb` is genuinely exercised instead of described.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'

const dbMock = vi.hoisted(() => ({
  restored: [] as unknown[],
  /** true = the boot read hangs until the test releases it (the real race). */
  block: false,
  waiting: [] as Array<() => void>,
  saved: [] as unknown[],
}))
const restoreMock = vi.hoisted(() => ({ sessions: [] as unknown[] }))
const streamMock = vi.hoisted(() => ({ calls: [] as Array<Record<string, unknown>> }))

vi.mock('@/lib/db', () => ({
  dbGetAllSessions: async () =>
    dbMock.block
      ? await new Promise((resolve) => dbMock.waiting.push(() => resolve(dbMock.restored)))
      : dbMock.restored,
  dbDeleteSession: async () => {},
  dbSaveSession: async (d: unknown) => {
    dbMock.saved.push(d)
  },
  debouncedSaveSession: async () => {},
  flushPendingSave: async () => {},
  dbGetCheckpoints: async () => [],
  dbSaveCheckpoints: async () => {},
}))

vi.mock('@/lib/restore', () => ({
  restoreFromServer: async () => restoreMock.sessions,
}))

// The mirror is not under test here; the store only needs the guards it imports.
vi.mock('@/lib/sessionSync', () => ({
  isSessionSyncEnabled: () => true,
  isTombstoned: () => false,
  queueSessionSync: () => {},
  queueSessionDeleted: () => {},
  flushSessionSync: async () => {},
  MAX_SESSIONS_PER_CALL: 50,
}))

const apiMock = vi.hoisted(() => ({
  healthCheck: vi.fn(async () => ({
    engine_online: true,
    active_provider: 'openai_compatible',
    ollama: true,
  })),
  listSchedules: vi.fn(async () => []),
}))

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  ...apiMock,
}))

// The turn itself is out of scope: the requests are recorded, nothing streams.
vi.mock('@/lib/stream', () => ({
  streamChat: async (req: Record<string, unknown>) => {
    streamMock.calls.push(req)
  },
}))

// The keys stay readable in the assertion instead of resolving to prose.
vi.mock('react-i18next', async (importOriginal) => ({
  ...(await importOriginal<typeof import('react-i18next')>()),
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) =>
      opts ? `${key}·${JSON.stringify(opts)}` : key,
    i18n: { language: 'en', changeLanguage: vi.fn() },
  }),
}))

import { toastBus } from '@/lib/toast'
import { useChatStore } from '@/store/chatStore'
import { useChatLayoutModel } from './model'
import type { MockInstance } from 'vitest'

function dbSession(id: string, title: string, rows: number, updatedAt = 2000) {
  return {
    id,
    title,
    messages: Array.from({ length: rows }, (_, i) => ({
      role: 'user',
      content: `${id}-row-${i}`,
      timestamp: 1,
    })),
    mode: 'ask',
    createdAt: 1000,
    updatedAt,
  }
}

/** Drain the microtask (and one macrotask) queue between two steps of the boot. */
async function settle() {
  for (let i = 0; i < 8; i += 1) {
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
  }
}

function releaseBootRead() {
  dbMock.block = false
  const waiting = dbMock.waiting.splice(0)
  waiting.forEach((release) => release())
}

const info: MockInstance = vi.fn()

/** Every info toast as `title` (plus the options the caller passed, if any). */
function infoCalls(): string[] {
  return info.mock.calls.map((call) => call.filter(Boolean).join(' | '))
}

beforeEach(() => {
  vi.spyOn(toastBus, 'info').mockImplementation(info as unknown as typeof toastBus.info)
  info.mockClear()
  dbMock.restored = []
  dbMock.block = false
  dbMock.waiting = []
  dbMock.saved = []
  restoreMock.sessions = []
  streamMock.calls = []
  apiMock.healthCheck.mockClear()
  apiMock.listSchedules.mockClear()
  localStorage.clear()
  useChatStore.setState({
    sessions: [],
    activeSessionId: null,
    isTyping: false,
    pendingToolCall: null,
    currentSession: null,
    hydrated: false,
    checkpoints: {},
  })
})

afterEach(() => {
  vi.restoreAllMocks()
})

/**
 * The walkthrough's boot race in one line: the composer exists, the restore is
 * still in flight, the user sends.
 */
async function sendDuringBlockedBoot(text: string) {
  dbMock.block = true
  dbMock.restored = [dbSession('owner-task', 'Owner transcript', 50)]
  const hook = renderHook(() => useChatLayoutModel())
  await settle()
  await act(async () => {
    await hook.result.current.handleSend(text)
  })
  return hook
}

describe('W10-8 — a send during the boot restore', () => {
  it('loses nothing: the text survives the restore that replaces the session list', async () => {
    await sendDuringBlockedBoot('BOOT-TEXT-42')

    // The boot read settles: the restore puts the owner's 50-row history on screen.
    releaseBootRead()
    await settle()

    const store = useChatStore.getState()
    expect(store.hydrated).toBe(true)
    // The clobber really happened — that is the defect this test is about: the
    // restore replaced the session list the send had been typed into.
    const restoredOwner = store.sessions.find((s) => s.id === 'owner-task')
    expect(restoredOwner).toBeDefined()
    expect(restoredOwner!.messages).toHaveLength(50)

    // `message_lost_no_task_carries_the_sent_text` — the walkthrough's verdict —
    // must not be reachable: the text is carried, exactly once, and by its own task
    // rather than by the restored transcript of somebody else's task.
    const carriers = store.sessions.filter((s) =>
      s.messages.some((m) => m.content.includes('BOOT-TEXT-42')),
    )
    expect(carriers).toHaveLength(1)
    expect(carriers[0]!.id).not.toBe('owner-task')
    expect(store.currentSession?.id).toBe(carriers[0]!.id)
    expect(store.activeSessionId).toBe(carriers[0]!.id)
    // …and the turn ran against that task, so the mirror can carry it too.
    expect(streamMock.calls).toHaveLength(1)
    expect(streamMock.calls[0]!.session_id).toBe(carriers[0]!.id)
    expect(streamMock.calls[0]!.message).toContain('BOOT-TEXT-42')
  })

  it('holds the text out of the doomed store and says the wait out loud', async () => {
    await sendDuringBlockedBoot('BOOT-TEXT-42')

    // Nothing was written into the store the restore is about to replace, no turn
    // was started against it — and the wait is not silent.
    expect(useChatStore.getState().sessions).toHaveLength(0)
    expect(useChatStore.getState().isTyping).toBe(false)
    expect(infoCalls()).toEqual([
      'chat.restoringHistory',
      'chat.restoringHistory | chat.sendHeldUntilRestore',
    ])
    expect(streamMock.calls).toHaveLength(0)

    releaseBootRead()
    await settle()
  })

  it('keeps the id of the task the text was typed in when the restore drops it', async () => {
    dbMock.block = true
    dbMock.restored = [dbSession('owner-task', 'Owner transcript', 50)]

    const { result } = renderHook(() => useChatLayoutModel())
    await settle()

    // The user opened a new task during boot — an in-memory session the restore
    // knows nothing about.
    act(() => {
      useChatStore.getState().createSession()
    })
    const typedIn = useChatStore.getState().activeSessionId!
    expect(typedIn).toBeTruthy()

    await act(async () => {
      await result.current.handleSend('BOOT-TEXT-7')
    })

    releaseBootRead()
    await settle()

    const store = useChatStore.getState()
    expect(store.sessions.some((s) => s.id === 'owner-task')).toBe(true)
    // The task the text was typed in exists again under its own id, carries the
    // text, and is the task the user is looking at.
    const typedTask = store.sessions.find((s) => s.id === typedIn)
    expect(typedTask?.messages.some((m) => m.content.includes('BOOT-TEXT-7'))).toBe(true)
    expect(store.currentSession?.id).toBe(typedIn)
    expect(streamMock.calls[0]!.session_id).toBe(typedIn)
  })

  it('sends straight through once the store is hydrated (no deferral in normal use)', async () => {
    dbMock.restored = [dbSession('owner-task', 'Owner transcript', 3)]

    const { result } = renderHook(() => useChatLayoutModel())
    await settle()

    const store = useChatStore.getState()
    expect(store.hydrated).toBe(true)

    await act(async () => {
      await result.current.handleSend('AFTER-BOOT')
    })

    const after = useChatStore.getState()
    expect(after.currentSession?.messages.some((m) => m.content.includes('AFTER-BOOT'))).toBe(true)
    expect(streamMock.calls).toHaveLength(1)
    expect(streamMock.calls[0]!.session_id).toBe(after.activeSessionId)
    expect(infoCalls()).toEqual(['chat.restoringHistory', 'chat.historyRestored·{"count":3}'])
  })
})

describe('W10-8 — the cold open that restores history', () => {
  it('discloses the restore that happened, with the number of rows it brought', async () => {
    dbMock.restored = [dbSession('owner-task', 'Owner transcript', 50)]

    renderHook(() => useChatLayoutModel())
    await settle()

    expect(useChatStore.getState().sessions).toHaveLength(1)
    expect(infoCalls()).toEqual(['chat.restoringHistory', 'chat.historyRestored·{"count":50}'])
  })

  it('uses the singular form for a single restored row', async () => {
    dbMock.restored = [dbSession('owner-task', 'Owner transcript', 1)]

    renderHook(() => useChatLayoutModel())
    await settle()

    expect(infoCalls()).toContain('chat.historyRestored·{"count":1}')
  })

  it('announces nothing restored when the cold open finds an empty store', async () => {
    renderHook(() => useChatLayoutModel())
    await settle()

    expect(useChatStore.getState().sessions).toHaveLength(0)
    expect(infoCalls()).toEqual(['chat.restoringHistory'])
  })

  it('never fires the running notice again after the first hydrate', async () => {
    dbMock.restored = [dbSession('owner-task', 'Owner transcript', 2)]

    const first = renderHook(() => useChatLayoutModel())
    await settle()
    first.unmount()
    info.mockClear()

    // A remount of the chat shell: the store is already hydrated.
    renderHook(() => useChatLayoutModel())
    await settle()

    expect(infoCalls()).toEqual([])
  })
})
