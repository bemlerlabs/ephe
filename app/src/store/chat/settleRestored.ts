import { closeThinkingPhases } from './helpers'
import type { ChatMessage } from '@/types'

/**
 * Settles a message that a restore brings back while it still claims to be
 * live.
 *
 * A checkpoint taken during a streaming answer snapshots the assistant bubble
 * with `streaming: true`. Rolled back verbatim, that message is history shown
 * as present: the UI keeps a live cursor on a reply that will never finish,
 * and `updateActiveMessage` (helpers.ts) treats it as the append target — so
 * the next chunk of a turn that is still running lands inside restored
 * history. Settling on the way in is what makes a restore safe to trust.
 *
 * `session.ts` carries the same rule as `healOrphan` for a tab that died
 * mid-stream; this is the restore-side twin. Collapse them onto one function
 * when `healOrphan` is next touched — two copies of an invariant are two
 * truths.
 */
export function settleRestoredMessage(m: ChatMessage): ChatMessage {
  if (!m.streaming) return m
  return {
    ...m,
    streaming: false,
    thinking: m.thinking ? { ...m.thinking, end: m.thinking.end ?? Date.now() } : null,
    thinkingPhases: closeThinkingPhases(m),
    streamMeta: {
      ...(m.streamMeta ?? {}),
      reflecting: false,
      revising: false,
      qualityCheck: false,
    },
    activities: m.activities?.map((a) =>
      a.status === 'running' ? { ...a, status: 'done' as const } : a,
    ),
  }
}
