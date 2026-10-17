/**
 * Ephe — restore-on-empty (PWA ← server mirror).
 *
 * Sessions live in IndexedDB; the server mirror (POST /api/sessions/sync)
 * only feeds the FTS index. When the browser cache is lost (storage
 * eviction, fresh browser, cleared site data) the sidebar came up empty
 * even though every session was still on disk in ~/.ephe/sessions/.
 * This module closes that loop: hydrate DbSessions from the server mirror.
 * Callers re-mirror what they accept, so the next start needs no round-trip.
 */
import { restoreSessions } from '@/lib/api'
import type { ChatMessage, DbSession } from '@/types'

export const RESTORE_LIMIT = 50

/**
 * Rows mirrored before the writer carried an id still have none (measured 2026-10-13:
 * 298 of 298 rows over the non-empty pwa-*.json files under ~/.ephe/sessions), so every
 * restored row keyed the virtual list `key={msg.id}` with `undefined` and React warned
 * about a missing key on the first paint of every restored chat. The writer now emits
 * that id at the source (server/routes/session_mirror.py); this fallback still covers the
 * mirror files it wrote before.
 *
 * The derived id is deterministic — session, row index and timestamp fix it — so a
 * re-hydrate keeps the keys the first hydrate used and does not remount rows that did
 * not change. A row that already carries an id keeps it.
 */
function withMessageId(
  msg: { role: string; content: string } & Partial<ChatMessage>,
  sessionId: string,
  index: number,
): ChatMessage {
  if (typeof msg.id === 'string' && msg.id.length > 0) return msg as ChatMessage
  const stamp =
    typeof msg.timestamp === 'number' && Number.isFinite(msg.timestamp) ? msg.timestamp : 0
  return { ...msg, id: `restored:${sessionId}:${index}:${stamp}` } as ChatMessage
}

/** The last real timestamp among the rows — the "last active" time of a restored
 *  session. The mirror file's mtime would be the moment of the sync, so every
 *  restored session would read as "just now" (measured 2026-10-07: four-day-old
 *  sessions as „gerade eben"/„2 Minuten"). // language-gate: ignore — both quotes are the German date-fns labels the sidebar renders */
function zuletztAktiv(messages: Array<{ timestamp?: number }>): number | null {
  const jetzt = Date.now()
  let best: number | null = null
  for (const m of messages) {
    const t = m?.timestamp
    if (typeof t !== 'number' || !Number.isFinite(t)) continue
    if (t < 946_684_800_000 || t > jetzt + 3_600_000) continue // seconds-based epoch or a skewed clock
    if (best === null || t > best) best = t
  }
  return best
}

export async function restoreFromServer(limit: number = RESTORE_LIMIT): Promise<DbSession[]> {
  const { sessions } = await restoreSessions(limit)
  return (
    sessions
      // R6/S3: older mirrors still carry empty shells („New task", 0 messages) —
      // that is no history, just weight in the sidebar.
      .filter((s) => s.id && Array.isArray(s.messages) && s.messages.length > 0)
      .map((s) => ({
        id: s.id,
        title: s.title || 'New task',
        messages: s.messages.map((m, i) => withMessageId(m, s.id, i)),
        // R6/S1: the mirrored birth beats the mirror mtime; without it every
        // restored session would read as „gerade eben". // language-gate: ignore — the German date-fns label the sidebar renders
        createdAt: s.created_at ?? s.updated_at,
        updatedAt: zuletztAktiv(s.messages) ?? s.updated_at,
        ...(s.mode ? { mode: s.mode } : {}),
        ...(s.parent_id ? { parentId: s.parent_id } : {}),
      }))
  )
}
