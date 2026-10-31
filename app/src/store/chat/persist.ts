import { dbDeleteSession, dbSaveSession, debouncedSaveSession } from '@/lib/db'
import type { GetFn, SetFn, StoreCtx } from './types'
import type { ToolCall } from '@/types'
import { toDbSession, updateActiveMessage } from './helpers'

/** Persist the active session (debounced). */
export function makePersistActive(get: GetFn) {
  return () => {
    const state = get()
    // The answer is written where the question was asked: a reader who moved on
    // mid-stream must not send the rest of it into the session they opened.
    const id = state.streamSessionId ?? state.activeSessionId
    if (!id) return
    const updated = state.sessions.find((s) => s.id === id)
    if (updated) debouncedSaveSession(toDbSession(updated))
  }
}

/** Set the transient streamMeta flag (reflecting/revising/qualityCheck). */
export function makeSetTransientMeta(set: SetFn) {
  return (key: 'reflecting' | 'revising' | 'qualityCheck', on: boolean) => {
    set((s) =>
      updateActiveMessage(s, (m) => ({
        ...m,
        streamMeta: { ...(m.streamMeta ?? {}), [key]: on },
      })),
    )
  }
}

/**
 * Set the last waiting tool call to approved/denied.
 *
 * IMPORTANT: it searches AFTER the done event (streaming=false) —
 * updateActiveMessage only reaches streaming=true messages, while the
 * asynchronous sandbox approval can still happen AFTER the stream ended
 * (a late click). Target: the last assistant message that has a
 * waiting call, streaming-agnostic.
 */
export function makeMarkSandboxStatus(ctx: StoreCtx) {
  return (status: ToolCall['status']) => {
    ctx.set((s) => {
      if (!s.activeSessionId) return s
      const sessions = s.sessions.map((sess) => {
        if (sess.id !== s.activeSessionId) return sess
        // the last assistant message with a waiting call (streaming-agnostic)
        let targetIdx = -1
        for (let i = sess.messages.length - 1; i >= 0; i--) {
          const m = sess.messages[i]!
          if (m.role === 'assistant' && m.tool_calls?.some((c) => c.status === 'waiting')) {
            targetIdx = i
            break
          }
        }
        if (targetIdx === -1) return sess
        const target = sess.messages[targetIdx]!
        const calls = target.tool_calls ?? []
        let lastWaiting = -1
        for (let i = calls.length - 1; i >= 0; i--) {
          if (calls[i]!.status === 'waiting') {
            lastWaiting = i
            break
          }
        }
        if (lastWaiting === -1) return sess
        const nextCalls = [...calls]
        nextCalls[lastWaiting] = { ...nextCalls[lastWaiting]!, status }
        const nextMsgs = [...sess.messages]
        nextMsgs[targetIdx] = { ...target, tool_calls: nextCalls }
        return { ...sess, messages: nextMsgs }
      })
      return {
        sessions,
        currentSession: sessions.find((x) => x.id === s.activeSessionId) ?? null,
      }
    })
    ctx.persistActive()
  }
}

/** Deletes a session from IndexedDB (re-export under the original import names). */
export { dbDeleteSession, dbSaveSession }
