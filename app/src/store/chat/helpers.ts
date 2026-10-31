import i18n from '@/i18n'
import type { CompactStats } from '@/lib/compact'
import type { ChatMessage, DbSession, Session, ThinkingPhase } from '@/types'

/** Indicator message after compaction (AI-client style: a compaction note in the log). */
export function indicatorMessage(stats: CompactStats): ChatMessage {
  return {
    id: crypto.randomUUID(),
    role: 'system',
    content: i18n.t('chat.compactIndicator', {
      count: stats.compactedCount,
      after: stats.after,
      before: stats.before,
    }),
    timestamp: Date.now(),
  }
}

/** Default title (G2: the auto title only ever applies to this one) — English,
 * the product's default language since round 14; the auto title replaces it anyway. */
export const DEFAULT_SESSION_TITLE = 'New task'

/**
 * G2: auto title from the first user message — ~48 characters, cut at a word
 * boundary, whitespace collapsed (AI-client parity).
 */
export function deriveSessionTitle(text: string): string {
  const clean = text.replace(/\s+/g, ' ').trim()
  if (clean.length <= 48) return clean
  const cut = clean.slice(0, 48)
  const lastSpace = cut.lastIndexOf(' ')
  return (lastSpace > 20 ? cut.slice(0, lastSpace) : cut).trimEnd() + '…'
}

// The shared default mode of a fresh session: a mode that may use tools, so that
// "just start writing" works without looking tools up first (parity with leading
// agent frameworks). Every mode fallback uses this one.
export const DEFAULT_COMPOSER_MODE = 'full-access'

export function toDbSession(s: Session): DbSession {
  return {
    id: s.id,
    title: s.title,
    messages: s.messages,
    createdAt: s.createdAt,
    updatedAt: Date.now(),
    ...(s.pinned ? { pinned: true } : {}),
    ...(s.titleCustom ? { titleCustom: true } : {}),
    ...(s.archived ? { archived: true } : {}),
    // Z53: the three stored ideas beside the archive flag. Each is omitted when
    // empty, so a row with no tags carries no `tags` key at all.
    ...(s.tags && s.tags.length > 0 ? { tags: s.tags } : {}),
    ...(s.folderId ? { folderId: s.folderId } : {}),
    ...(s.deletedAt ? { deletedAt: s.deletedAt } : {}),
    ...(s.unread ? { unread: true } : {}),
    ...(s.parentId ? { parentId: s.parentId } : {}),
    ...(s.mode ? { mode: s.mode } : {}),
    // Wave 3: measured session totals survive the reload (cost monitor).
    ...(s.usageTotals ? { usageTotals: s.usageTotals } : {}),
  }
}

export function fromDbSession(d: DbSession): Session {
  return {
    id: d.id,
    title: d.title,
    messages: d.messages as ChatMessage[],
    createdAt: d.createdAt,
    ...(d.pinned ? { pinned: true } : {}),
    ...(d.titleCustom ? { titleCustom: true } : {}),
    ...(d.archived ? { archived: true } : {}),
    ...(d.tags && d.tags.length > 0 ? { tags: d.tags } : {}),
    ...(d.folderId ? { folderId: d.folderId } : {}),
    ...(d.deletedAt ? { deletedAt: d.deletedAt } : {}),
    ...(d.unread ? { unread: true } : {}),
    ...(d.parentId ? { parentId: d.parentId } : {}),
    ...(d.mode ? { mode: d.mode } : {}),
    ...(d.usageTotals ? { usageTotals: d.usageTotals } : {}),
  }
}

/**
 * Update the ACTIVE assistant message (streaming=true) of the session the turn
 * belongs to, in place. Pure state transformation (Zustand `set` updater).
 *
 * The turn's own session wins over whatever is displayed: a chunk that arrives
 * after the reader moved to another task belongs to the question that was asked
 * where they came from. `currentSession` only follows while the two are the same
 * session — otherwise the answer would repaint the screen the user left.
 */
export function updateActiveMessage(
  s: {
    sessions: Session[]
    activeSessionId: string | null
    streamSessionId?: string | null
    currentSession?: Session | null
  },
  fn: (m: ChatMessage) => ChatMessage,
): { sessions: Session[]; currentSession: Session | null } {
  const target = s.streamSessionId ?? s.activeSessionId
  if (!target) return { sessions: s.sessions, currentSession: null }
  const sessions = s.sessions.map((sess) => {
    if (sess.id !== target) return sess
    const msgs = sess.messages
    let last = -1
    for (let i = msgs.length - 1; i >= 0; i--) {
      if (msgs[i]!.role === 'assistant' && msgs[i]!.streaming) {
        last = i
        break
      }
    }
    if (last === -1) return sess
    const next = [...msgs]
    next[last] = fn(msgs[last]!)
    return { ...sess, messages: next }
  })
  const shown = sessions.find((sess) => sess.id === s.activeSessionId) ?? null
  return {
    sessions,
    currentSession: target === s.activeSessionId ? shown : (s.currentSession ?? null),
  }
}

/** Close all open reasoning phases (turn end, error, healing). */
export function closeThinkingPhases(m: ChatMessage): ThinkingPhase[] | undefined {
  if (!m.thinkingPhases) return undefined
  const now = Date.now()
  return m.thinkingPhases.map((p) => (p.end === null ? { ...p, end: now } : p))
}
