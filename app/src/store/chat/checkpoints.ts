import { dbSaveCheckpoints, debouncedSaveSession } from '@/lib/db'
import { createCheckpoint, rollbackToCheckpoint, deleteCheckpoint } from '@/lib/checkpoints'
import type { ChatState, StoreCtx } from './types'
import { toDbSession } from './helpers'
import { settleRestoredMessage } from './settleRestored'

/** Checkpoints & Rollback (P2-7) — 1:1 from chatStore.ts (938–972).
 *  Not 1:1 anymore: rollback now settles restored bubbles and persists the
 *  restored transcript (see rollbackToCheckpoint below). */
export function makeCheckpointActions(ctx: StoreCtx): Partial<ChatState> {
  const { set, get } = ctx
  return {
    createCheckpoint: (label?: string) => {
      const state = get()
      const sid = state.activeSessionId
      const session = state.currentSession
      if (!sid || !session) return
      const cp = createCheckpoint(session.messages, label)
      const updated = [...(state.checkpoints[sid] ?? []), cp]
      set((s) => ({ checkpoints: { ...s.checkpoints, [sid]: updated } }))
      dbSaveCheckpoints(sid, updated)
    },
    rollbackToCheckpoint: (id: string) => {
      const state = get()
      const sid = state.activeSessionId
      if (!sid) return
      const cps = state.checkpoints[sid] ?? []
      const rolled = rollbackToCheckpoint(id, cps)
      if (!rolled) return
      // A snapshot taken mid-answer holds a bubble with streaming: true. It is
      // history now, and nothing may still append into it.
      const restored = rolled.map(settleRestoredMessage)
      set((s) => {
        const sessions = s.sessions.map((sess) =>
          sess.id === sid ? { ...sess, messages: restored } : sess,
        )
        const currentSession = sessions.find((sess) => sess.id === sid)
        return { sessions, currentSession: currentSession ?? null }
      })
      // Read AFTER the set: `state` is the pre-rollback snapshot, and writing
      // it back persisted the messages the user just discarded — the transcript
      // looked restored until the next reload brought the deleted turn back.
      const updated = get().sessions.find((s) => s.id === sid)
      if (updated) debouncedSaveSession(toDbSession(updated))
    },
    deleteCheckpoint: (id: string) => {
      const state = get()
      const sid = state.activeSessionId
      if (!sid) return
      const updated = deleteCheckpoint(state.checkpoints[sid] ?? [], id)
      set((s) => ({ checkpoints: { ...s.checkpoints, [sid]: updated } }))
      dbSaveCheckpoints(sid, updated)
    },
  }
}
