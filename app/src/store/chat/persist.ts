import { dbDeleteSession, dbSaveSession, debouncedSaveSession } from '@/lib/db'
import type { ChatState, GetFn, SetFn, StoreCtx } from './types'
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

/** The session a gate write belongs to — the one `persistActive` writes, so the
 *  click lands in the transcript it answers even after the reader moved on. */
function gateSessionId(s: ChatState): string | null {
  return s.streamSessionId ?? s.activeSessionId
}

/** A call answers to the token the gate carries. `description` is the older home of
 *  the same token (transcripts written before `approval` existed) and still matches. */
export function callCarriesToken(call: ToolCall, token: string): boolean {
  return call.approval?.token === token || call.description === token
}

/**
 * Close the gate a token names — the one writer of a gate's state.
 *
 * The token, never a position: with two gates open in one turn, the position rule
 * closed the card the reader did not click (audit finding 40).
 *
 * IMPORTANT: it searches AFTER the done event (streaming=false) —
 * updateActiveMessage only reaches streaming=true messages, while the
 * asynchronous sandbox approval can still happen AFTER the stream ended
 * (a late click). Target: the assistant message that carries the token,
 * streaming-agnostic.
 */
export function makeMarkSandboxGate(ctx: StoreCtx) {
  return (token: string, decide: (call: ToolCall) => ToolCall) => {
    ctx.set((s) => {
      const id = gateSessionId(s)
      if (!id) return s
      const sessions = s.sessions.map((sess) => {
        if (sess.id !== id) return sess
        let targetIdx = -1
        for (let i = sess.messages.length - 1; i >= 0; i--) {
          const m = sess.messages[i]!
          if (m.role === 'assistant' && m.tool_calls?.some((c) => callCarriesToken(c, token))) {
            targetIdx = i
            break
          }
        }
        if (targetIdx === -1) return sess
        const target = sess.messages[targetIdx]!
        const calls = target.tool_calls ?? []
        const at = calls.findIndex((c) => callCarriesToken(c, token))
        if (at === -1) return sess
        const nextCalls = [...calls]
        nextCalls[at] = decide(calls[at]!)
        const nextMsgs = [...sess.messages]
        nextMsgs[targetIdx] = { ...target, tool_calls: nextCalls }
        return { ...sess, messages: nextMsgs }
      })
      return {
        sessions,
        currentSession: sessions.find((x) => x.id === id) ?? null,
      }
    })
    ctx.persistActive()
  }
}

/** Deletes a session from IndexedDB (re-export under the original import names). */
export { dbDeleteSession, dbSaveSession }
