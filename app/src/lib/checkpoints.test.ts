import { describe, it, expect, vi } from 'vitest'
import {
  createCheckpoint,
  rollbackToCheckpoint,
  listCheckpoints,
  deleteCheckpoint,
} from '@/lib/checkpoints'
import type { ChatMessage } from '@/types'

function makeMsgs(n: number): ChatMessage[] {
  return Array.from({ length: n }, (_, i) => ({
    id: `m-${i}`,
    role: 'user',
    content: `msg ${i}`,
    timestamp: Date.now() + i,
  }))
}

describe('checkpoints', () => {
  it('creates a snapshot of the messages', () => {
    const msgs = makeMsgs(3)
    const cp = createCheckpoint(msgs, 'vor Refactor')
    expect(cp.messages).toEqual(msgs)
    expect(cp.label).toBe('vor Refactor')
    expect(cp.id).toBeTruthy()
    expect(cp.createdAt).toBeGreaterThan(0)
  })

  it('deep-copies so later mutations do not affect the snapshot', () => {
    const msgs = makeMsgs(2)
    const cp = createCheckpoint(msgs, 'snapshot')
    msgs[0]!.content = 'mutiert'
    expect(cp.messages[0]!.content).toBe('msg 0')
  })

  it('rolls back to a checkpoint by id', () => {
    const msgs = makeMsgs(5)
    const cp = createCheckpoint(msgs, 'punkt 2')
    const rolled = rollbackToCheckpoint(cp.id, [cp])
    expect(rolled).toEqual(cp.messages)
    expect(rolled![0]!.content).toBe('msg 0')
  })

  it('returns null when the checkpoint id is unknown', () => {
    const rolled = rollbackToCheckpoint('nope', [])
    expect(rolled).toBeNull()
  })

  it('lists checkpoints newest-first', () => {
    const msgs = makeMsgs(1)
    const a = createCheckpoint(msgs, 'a')
    const b = createCheckpoint(msgs, 'b')
    const list = listCheckpoints([b, a])
    expect(list[0]!.label).toBe('b')
    expect(list).toHaveLength(2)
  })

  it('deletes a checkpoint by id', () => {
    const msgs = makeMsgs(1)
    const cp = createCheckpoint(msgs, 'weg')
    const rest = deleteCheckpoint([cp], cp.id)
    expect(rest).toHaveLength(0)
  })
})

/* ------------------------------------------------------------------ *
 * Store slice: the sequence a user actually performs.
 *
 * createCheckpoint / rollbackToCheckpoint / deleteCheckpoint in
 * app/src/store/chat/checkpoints.ts are what the checkpoint control row
 * calls. A restore that is only applied to the in-memory transcript while the
 * persisted session keeps the newer messages is invisible until the next
 * reload — and then the rollback is silently undone. These tests drive the
 * slice directly against a recording fake of @/lib/db.
 * ------------------------------------------------------------------ */

const db = vi.hoisted(() => ({
  savedCheckpoints: [] as Array<{ sid: string; items: unknown[] }>,
  savedSessions: [] as Array<{ id: string; messages: unknown[] }>,
}))

vi.mock('@/lib/db', () => ({
  dbSaveCheckpoints: async (sid: string, items: unknown[]) => {
    db.savedCheckpoints.push({ sid, items })
  },
  debouncedSaveSession: (session: { id: string; messages: unknown[] }) => {
    db.savedSessions.push(session)
  },
}))

import { makeCheckpointActions } from '@/store/chat/checkpoints'
import type { ChatState, SetFn, StoreCtx } from '@/store/chat/types'

const SID = 'session-under-test'

/** A session with two settled messages — the state the user snapshots. */
function settledMessages(): ChatMessage[] {
  return [
    { id: 'u-1', role: 'user', content: 'rename the module', timestamp: 1 },
    { id: 'a-1', role: 'assistant', content: 'done, tests green', timestamp: 2 },
  ]
}

/** Minimal stand-in for the zustand store: set(patch | fn) then get(). */
function makeCtx() {
  const messages = settledMessages()
  let state = {
    sessions: [{ id: SID, title: 'T', messages, createdAt: 1, updatedAt: 1 }],
    activeSessionId: SID,
    currentSession: { id: SID, title: 'T', messages, createdAt: 1, updatedAt: 1 },
    checkpoints: {},
  } as unknown as ChatState

  const set: SetFn = (update) => {
    const patch = typeof update === 'function' ? update(state) : update
    state = { ...state, ...patch }
  }
  const ctx: StoreCtx = {
    set,
    get: () => state,
    persistActive: () => {},
    setTransientMeta: () => {},
    markSandboxStatus: () => {},
  }
  return { ctx, read: () => state }
}

/** What the agent leaves behind: a user turn plus an assistant message whose
 * tool call edited a file on disk. */
function agentEditsAFile(state: ChatState): ChatMessage[] {
  const next: ChatMessage[] = [
    ...state.currentSession!.messages,
    { id: 'u-2', role: 'user', content: 'now fix the typo too', timestamp: 3 },
    {
      id: 'a-2',
      role: 'assistant',
      content: 'edited src/app.py',
      timestamp: 4,
      tool_calls: [
        {
          id: 'tc-1',
          name: 'edit_file',
          args: { path: 'src/app.py' },
          status: 'completed' as const,
          approval_diff: '@@ -1 +1 @@\n-typo\n-fixed',
        },
      ],
    },
  ]
  return next
}

describe('checkpoint restore sequence (store slice)', () => {
  it('records the checkpoint under the active session and persists it', () => {
    db.savedCheckpoints.length = 0
    const { ctx, read } = makeCtx()
    const actions = makeCheckpointActions(ctx)

    actions.createCheckpoint!('before typo fix')

    expect(read().checkpoints[SID]).toHaveLength(1)
    expect(read().checkpoints[SID]![0]!.label).toBe('before typo fix')
    expect(db.savedCheckpoints).toHaveLength(1)
    expect(db.savedCheckpoints[0]!.sid).toBe(SID)
  })

  it('restores the transcript to the checkpoint after the agent changed a file', () => {
    const { ctx, read } = makeCtx()
    const actions = makeCheckpointActions(ctx)
    actions.createCheckpoint!('before typo fix')
    const cpId = read().checkpoints[SID]![0]!.id

    // The agent works: two more messages, one of them an edit_file tool call.
    const after = agentEditsAFile(read())
    ctx.set((s) => ({
      sessions: s.sessions.map((sess) => (sess.id === SID ? { ...sess, messages: after } : sess)),
      currentSession: { ...s.currentSession!, messages: after },
    }))
    expect(read().currentSession!.messages).toHaveLength(4)

    actions.rollbackToCheckpoint!(cpId)

    expect(read().currentSession!.messages.map((m) => m.id)).toEqual(['u-1', 'a-1'])
    expect(read().sessions.find((s) => s.id === SID)!.messages).toHaveLength(2)
  })

  it('persists the RESTORED messages, not the pre-rollback transcript', async () => {
    db.savedSessions.length = 0
    const { ctx, read } = makeCtx()
    const actions = makeCheckpointActions(ctx)
    actions.createCheckpoint!('before typo fix')
    const cpId = read().checkpoints[SID]![0]!.id

    const after = agentEditsAFile(read())
    ctx.set((s) => ({
      sessions: s.sessions.map((sess) => (sess.id === SID ? { ...sess, messages: after } : sess)),
      currentSession: { ...s.currentSession!, messages: after },
    }))

    actions.rollbackToCheckpoint!(cpId)

    // The write the next reload reads back has to carry the restored list.
    await vi.waitFor(() => expect(db.savedSessions).toHaveLength(1))
    expect(db.savedSessions[0]!.messages.map((m) => (m as ChatMessage).id)).toEqual(['u-1', 'a-1'])
  })

  it('keeps the checkpoint available after a restore', () => {
    const { ctx, read } = makeCtx()
    const actions = makeCheckpointActions(ctx)
    actions.createCheckpoint!('before typo fix')
    const cpId = read().checkpoints[SID]![0]!.id

    actions.rollbackToCheckpoint!(cpId)

    expect(read().checkpoints[SID]).toHaveLength(1)
    expect(read().checkpoints[SID]![0]!.id).toBe(cpId)
  })

  it('leaves the transcript untouched when the checkpoint id is unknown', () => {
    db.savedSessions.length = 0
    const { ctx, read } = makeCtx()
    const actions = makeCheckpointActions(ctx)
    actions.createCheckpoint!('before typo fix')
    const before = read().currentSession!.messages

    actions.rollbackToCheckpoint!('never-recorded')

    expect(read().currentSession!.messages).toBe(before)
    expect(db.savedSessions).toHaveLength(0)
  })

  it('does not restore a message that still claims to be streaming', () => {
    const { ctx, read } = makeCtx()
    const actions = makeCheckpointActions(ctx)
    // The user hits the camera while the answer is still arriving.
    const live: ChatMessage[] = [
      ...settledMessages().slice(0, 1),
      {
        id: 'a-live',
        role: 'assistant' as const,
        content: 'partial…',
        timestamp: 2,
        streaming: true,
      },
    ]
    ctx.set((s) => ({
      sessions: s.sessions.map((sess) => (sess.id === SID ? { ...sess, messages: live } : sess)),
      currentSession: { ...s.currentSession!, messages: live },
    }))
    actions.createCheckpoint!('mid-stream')
    const cpId = read().checkpoints[SID]![0]!.id

    const after = agentEditsAFile(read())
    ctx.set((s) => ({
      sessions: s.sessions.map((sess) => (sess.id === SID ? { ...sess, messages: after } : sess)),
      currentSession: { ...s.currentSession!, messages: after },
    }))

    actions.rollbackToCheckpoint!(cpId)

    // A restored turn is history: nothing may keep appending into it, and the
    // UI must not show a reply that never finishes.
    const restored = read().currentSession!.messages
    expect(restored.map((m) => m.id)).toEqual(['u-1', 'a-live'])
    expect(restored.every((m) => !m.streaming)).toBe(true)
  })

  it('drops a checkpoint from the list and from storage on delete', () => {
    db.savedCheckpoints.length = 0
    const { ctx, read } = makeCtx()
    const actions = makeCheckpointActions(ctx)
    actions.createCheckpoint!('one')
    const cpId = read().checkpoints[SID]![0]!.id

    actions.deleteCheckpoint!(cpId)

    expect(read().checkpoints[SID]).toHaveLength(0)
    expect(db.savedCheckpoints[db.savedCheckpoints.length - 1]!.items).toHaveLength(0)
  })
})
